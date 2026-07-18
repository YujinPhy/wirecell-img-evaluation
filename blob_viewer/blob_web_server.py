"""Serves reco blobs from any Wire-Cell cluster file as a live, browser-connected 3D view.

Summary: this starts a `trame` web server on this machine that renders the
scene live and streams it to whatever browser connects to it -- the workflow
implied by "connect via the server's CLI, get a link". Over Remote-SSH,
VSCode auto-forwards the port and pops up an "Open in Browser" notification;
otherwise forward the port manually (`ssh -L PORT:localhost:PORT`).

Not detector-specific: `--blob-file`/`--depo-file` accept any
`clusters-apa-<N>.tar.gz` / `depos-drifted-<N>.zip` pair (PDHD, PDVD, or
otherwise). `--v-drift`/`--t-offset`/`--response-plane-x` default to generic
values (matching `wirecell.img.converter.undrift_blobs`'s own defaults) so an
uncalibrated dataset still renders -- only the absolute drift/x position is
off until the real detector constants are passed (PDHD's calibrated values
are documented in docs/time_offset_calibration.md).

See blob_viewer/blob_web_server_reference.md for a from-scratch walkthrough
of how the trame/pyvista/VTK rendering stack and the browser connection work.

Usage:
    source ../wire-cell-python/venv/bin/activate
    export PYTHONPATH="/home/yujin/projects/WireCell"
    python blob_viewer/blob_web_server.py --blob-file <clusters-apa-N.tar.gz> [--depo-file <depos-drifted-N.zip>] [--port 8080]
"""

import argparse
import os
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import psutil
import pyvista as pv
import vtk
from pyvista.trame.ui import plotter_ui
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3
from vtk.util import numpy_support as vtk_np
from wirecell import units
from wirecell.img import converter

from utils.load import load_cluster_data, load_generation_data

pv.OFF_SCREEN = True

# Generic fallback constants -- match `wirecell.img.converter.undrift_blobs`'s
# own defaults, not any particular detector's calibration. Pass
# --v-drift/--t-offset/--response-plane-x explicitly for a calibrated detector
# (e.g. PDHD: 1.6, 314.5, 3430.47 -- see docs/time_offset_calibration.md).
V_DRIFT = 1.6           # [mm/us]
T_OFFSET = 0.0          # [us]
RESPONSE_PLANE_X = 0.0  # [mm]

WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
MULTI_SAMPLES = 8

_RESERVED_BLOB_KEYS = {"code", "corners", "bounds"}

# ==== Server PID file management ====
def _pid_file(port):
    return os.path.join(tempfile.gettempdir(), f"blob_web_server_port{port}.pid")


def _stop_previous_server(port):
    """Kills whatever instance of this script is still bound to `port`, if any.

    Lets `python blob_web_server.py <file> --port N` just work every time,
    instead of failing with "address already in use" when a previous
    invocation on the same port is still running.
    """
    pid_file = _pid_file(port)
    if not os.path.exists(pid_file):
        return
    old_pid = int(open(pid_file).read().strip())
    if psutil.pid_exists(old_pid):
        proc = psutil.Process(old_pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            proc.kill()
        print(f"[INFO] Stopped previous server on port {port} (pid={old_pid})")
    os.remove(pid_file)


def _register_current_server(port):
    with open(_pid_file(port), "w") as f:
        f.write(str(os.getpid()))


def _load_and_undrift(blob_file, v_drift=V_DRIFT, t_offset=T_OFFSET, response_plane_x=RESPONSE_PLANE_X):
    """Loads a cluster graph and converts every blob's time coordinate to an x position.

    Thin wrapper around the upstream `wirecell.img.converter.undrift_blobs`
    (the same transform used across this repo, e.g.
    `scripts/position_center_comparison.py`'s `blob_center()`):
    `x = response_plane_x - v_drift * (t_us - t_offset)`. Reused here instead
    of reimplemented so the physics stays in one place.
    """
    cgraph = load_cluster_data(blob_file)
    if cgraph is None:
        return None
    return converter.undrift_blobs(
        cgraph,
        speed=v_drift * units.mm / units.us,
        time=t_offset * units.us,
        x0=response_plane_x * units.mm,
    )


def _blobs_to_polydata(cgraph):
    """Builds one closed 3D surface per reco blob from its (undrifted) `corners` polygon.

    Each blob's `corners` is a 2D polygon at one drift-time/x slice; extruding
    it along x by the blob's `span` (its slice thickness, already rescaled to
    mm by `undrift_blobs`) gives the blob's 3D solid. Uses the upstream
    `wirecell.img.converter.orderpoints`/`extrude` (angle-sort + ring
    extrusion) for the geometry -- the same routines
    `wirecell.img.converter.clusters2blobs` uses to build a `tvtk` mesh for
    `wirecell-img paraview-blobs`, except `tvtk`/`mayavi` isn't installed
    here, so this assembles a `pyvista.PolyData` surface instead.

    Every blob's non-geometric scalar fields (`val`, etc.) are attached as
    per-cell arrays, one value repeated across that blob's faces, so any of
    them can be picked via `--scalars` for coloring.
    """
    all_points = []
    faces = []
    cell_scalars = defaultdict(list)
    offset = 0
    for _, ndata in cgraph.nodes(data=True):
        if ndata.get("code") != "b":
            continue
        pts = converter.orderpoints(list(ndata["corners"]))
        pts, cells = converter.extrude(pts, ndata["span"])
        scalar_values = {
            key: val for key, val in ndata.items()
            if key not in _RESERVED_BLOB_KEYS and isinstance(val, (int, float))
        }
        for cell in cells:
            faces.append(len(cell))
            faces.extend(offset + i for i in cell)
            for name, value in scalar_values.items():
                cell_scalars[name].append(value)
        all_points.extend(pts)
        offset += len(pts)

    if not all_points:
        return None

    poly = pv.PolyData(np.asarray(all_points, dtype=float), faces=np.asarray(faces, dtype=np.int64))
    for name, values in cell_scalars.items():
        poly.cell_data[name] = np.asarray(values, dtype=float)
    return poly


def _depo_density_shells(depo_file, ks=(1.0, 2.0, 3.0), theta_res=10, phi_res=6):
    """Builds nested per-depo ellipsoid shells spanning the depo's center-to-3-sigma cloud.

    Each depo's charge spreads as an anisotropic 3D Gaussian: sigma=`L`
    along the drift/x axis, sigma=`T` isotropically in (y, z). `L`/`T` are
    taken from Gen0 (post-drift), the diffused-at-readout values -- Gen1
    (pre-drift) always has `L`=`T`=0 since no diffusion has happened yet at
    creation. Position (x, y, z) is taken from Gen1, the true pre-drift
    location (Gen0's `x` is just the anode-plane x, not usable directly;
    see `_load_and_undrift` / `position_center_comparison.py`'s
    `depo_center()` for why).

    For each `k` in `ks`, one `vtkGlyph3D` call places a unit-sphere copy at
    every depo's position, scaled per-axis to `(k*L, k*T, k*T)` via
    `SetScaleModeToScaleByVectorComponents` -- i.e. every depo's k-sigma
    ellipsoid in a single vectorized filter call, instead of building
    `n_depos` individual meshes in a Python loop (the latter took ~215s for
    5000 depos; this takes ~0.2s). Charge density is constant on every
    k-sigma isosurface by construction (that's what defines it): with peak
    density `rho_peak = |q| / ((2*pi)**1.5 * L * T**2)`, the density on the
    k-sigma shell is `rho_peak * exp(-k**2/2)`. Stacking shells at
    increasing k (all sharing the same center) is what gives the
    center-to-edge gradient once colored by this density.

    Args:
        depo_file (str): Path to a `depos-drifted-<N>.zip` file.
        ks (tuple[float]): Sigma multiples to draw shells at.
        theta_res, phi_res (int): Unit-sphere template resolution -- kept
            low since total polygon count scales with `len(ks) * n_depos`.
            Raise for smoother ellipsoids on small depo counts.

    Returns:
        pyvista.PolyData or None: Merged shells with a point-data array
            `charge_density`, or None if the depo file has no data.
    """
    gen0 = load_generation_data(depo_file, 0)
    gen1 = load_generation_data(depo_file, 1)
    if gen0 is None or gen1 is None:
        return None

    L, T, q = gen0["L"], gen0["T"], np.abs(gen0["q"])
    valid = (L > 0) & (T > 0)
    if not np.any(valid):
        return None
    x, y, z = gen1["x"][valid], gen1["y"][valid], gen1["z"][valid]
    L, T, q = L[valid], T[valid], q[valid]
    peak_density = q / ((2 * np.pi) ** 1.5 * L * T ** 2)

    points = vtk.vtkPoints()
    points.SetData(vtk_np.numpy_to_vtk(np.column_stack([x, y, z]).copy(), deep=True))

    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(1.0)
    sphere.SetThetaResolution(theta_res)
    sphere.SetPhiResolution(phi_res)

    shells = []
    for k in ks:
        pdata = vtk.vtkPolyData()
        pdata.SetPoints(points)
        scale_vec = vtk_np.numpy_to_vtk(np.column_stack([k * L, k * T, k * T]).copy(), deep=True)
        scale_vec.SetName("scale_vec")
        pdata.GetPointData().SetVectors(scale_vec)
        density = vtk_np.numpy_to_vtk((peak_density * np.exp(-0.5 * k * k)).copy(), deep=True)
        density.SetName("charge_density")
        pdata.GetPointData().SetScalars(density)

        glyph = vtk.vtkGlyph3D()
        glyph.SetSourceConnection(sphere.GetOutputPort())
        glyph.SetInputData(pdata)
        glyph.SetVectorModeToUseVector()
        glyph.SetScaleModeToScaleByVectorComponents()
        glyph.OrientOff()
        glyph.Update()
        shells.append(pv.wrap(glyph.GetOutput()))

    return shells[0].merge(shells[1:])


def serve_blobs(blob_file, depo_file=None, port=8080, scalars="val",
                 v_drift=V_DRIFT, t_offset=T_OFFSET, response_plane_x=RESPONSE_PLANE_X,
                 window_width=WINDOW_WIDTH, window_height=WINDOW_HEIGHT, multi_samples=MULTI_SAMPLES,
                 depo_theta_res=10, depo_phi_res=6):
    _stop_previous_server(port)
    _register_current_server(port)

    cgraph = _load_and_undrift(blob_file, v_drift, t_offset, response_plane_x)
    if cgraph is None:
        sys.exit(1)
    blob_mesh = _blobs_to_polydata(cgraph)
    if blob_mesh is None:
        print(f"[ERROR] No reco blobs found in {blob_file}")
        sys.exit(1)

    depo_mesh = None
    if depo_file:
        print(f"[INFO] Building depo center-to-3-sigma density shells...")
        depo_mesh = _depo_density_shells(depo_file, theta_res=depo_theta_res, phi_res=depo_phi_res)
        if depo_mesh is None:
            print(f"[WARNING] Failed to load depo file: {depo_file}")

    pv.global_theme.multi_samples = multi_samples
    plotter = pv.Plotter(
        window_size=(window_width, window_height),
        line_smoothing=True,
        point_smoothing=True,
        polygon_smoothing=True,
    )
    blob_actor = plotter.add_mesh(blob_mesh, scalars=scalars, show_edges=True, name="blobs")
    depo_actor = None
    if depo_mesh is not None:
        depo_actor = plotter.add_mesh(
            depo_mesh, scalars="charge_density", cmap="plasma", opacity=[0.0, 0.7],
            show_scalar_bar=False, name="depos",
        )

    server = get_server()
    state = server.state
    view = None

    @state.change("show_blobs")
    def _toggle_blobs(show_blobs, **kwargs):
        blob_actor.visibility = show_blobs
        if view is not None:
            view.update()

    @state.change("show_depos")
    def _toggle_depos(show_depos, **kwargs):
        if depo_actor is not None:
            depo_actor.visibility = show_depos
            if view is not None:
                view.update()

    @state.change("blob_opacity")
    def _set_blob_opacity(blob_opacity, **kwargs):
        blob_actor.prop.opacity = blob_opacity
        if view is not None:
            view.update()

    @state.change("depo_opacity")
    def _set_depo_opacity(depo_opacity, **kwargs):
        if depo_actor is not None:
            depo_actor.prop.opacity = depo_opacity
            if view is not None:
                view.update()

    blob_idents = blob_mesh.cell_data["ident"]

    @state.change("blob_index_filter")
    def _filter_blob_index(blob_index_filter, **kwargs):
        idx = None
        if blob_index_filter not in (None, ""):
            try:
                idx = int(blob_index_filter)
            except (TypeError, ValueError):
                idx = None
        # `blob_actor.mapper.dataset = ...` (pyvista's property setter) is a
        # no-op here -- verified the actor's bounds never change through it,
        # likely because add_mesh(scalars=...) wires the mapper through an
        # internal "active scalars" pass-through algorithm that the setter's
        # reconnect logic doesn't actually re-trigger for this pyvista
        # version. Calling the underlying vtkDataSetMapper.SetInputData
        # directly bypasses that and reliably swaps the rendered geometry.
        dataset = blob_mesh if idx is None else blob_mesh.extract_cells(np.where(blob_idents == idx)[0])
        blob_actor._filtered_dataset = dataset  # keep a strong ref alongside the mapper's VTK-side one
        blob_actor.mapper.SetInputData(dataset)
        blob_actor.mapper.Modified()
        if view is not None:
            view.update()

    with SinglePageLayout(server) as layout:
        layout.title.set_text(f"Reco blobs: {os.path.basename(blob_file)}")
        with layout.content:
            with vuetify3.VContainer(fluid=True, classes="pa-0 fill-height"):
                view = plotter_ui(plotter)
        with layout.toolbar:
            vuetify3.VSpacer()
            vuetify3.VCheckbox(v_model=("show_blobs", True), label="Blobs",
                                hide_details=True, density="compact")
            vuetify3.VSlider(
                v_model=("blob_opacity", 1.0), min=0, max=1, step=0.05,
                label="Blob opacity", thumb_label=True, hide_details=True,
                density="compact", style="max-width: 200px;", classes="mx-2",
            )
            if depo_actor is not None:
                vuetify3.VCheckbox(v_model=("show_depos", True), label="Depos",
                                    hide_details=True, density="compact")
                vuetify3.VSlider(
                    v_model=("depo_opacity", 1.0), min=0, max=1, step=0.05,
                    label="Depo opacity", thumb_label=True, hide_details=True,
                    density="compact", style="max-width: 200px;", classes="mx-2",
                )
        with layout:
            with vuetify3.VNavigationDrawer(location="right", permanent=True, width=260):
                vuetify3.VCardText(f"Blob index (0-{int(blob_idents.max())})")
                vuetify3.VTextField(
                    v_model=("blob_index_filter", ""), label="Show only blob #",
                    type="number", clearable=True, hide_details=True,
                    density="compact", classes="mx-2",
                )

    print(f"[INFO] {blob_mesh.n_cells} blob faces loaded from {blob_file}"
          + (f", depo density shells ({depo_mesh.n_cells} cells) from {depo_file}"
             if depo_mesh is not None else ""))
    print(f"[INFO] Starting web server on port {port} -- open http://localhost:{port} "
          f"(over Remote-SSH, VSCode should offer to forward this port automatically)")
    server.start(port=port, host="0.0.0.0", open_browser=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--blob-file", required=True,
                         help="Path to a clusters-apa-<N>.tar.gz reco blob file (any detector)")
    parser.add_argument("--depo-file", default=None,
                         help="Path to a depos-drifted-<N>.zip file to overlay as points "
                              "(omit to render blobs only)")
    parser.add_argument("--port", type=int, default=8080, help="port to run the web server on (default: 8080)")
    parser.add_argument("--scalars", default="val", help="Cell scalar field to color blobs by (default: val)")

    # ==== Detector-specific undrift constants (generic fallback defaults; see docs/time_offset_calibration.md for PDHD's calibrated values) ====
    parser.add_argument("--v-drift", type=float, default=V_DRIFT,
                        help="drift velocity [mm/us] (default: %.2f)" % V_DRIFT)
    parser.add_argument("--t-offset", type=float, default=T_OFFSET,
                        help="depo-to-reco time offset [us] (default: %.2f)" % T_OFFSET)
    parser.add_argument("--response-plane-x", type=float, default=RESPONSE_PLANE_X,
                        help="x position of the response/anode plane [mm] (default: %.2f)" % RESPONSE_PLANE_X)

    # ==== Render quality ====
    parser.add_argument("--width", type=int, default=WINDOW_WIDTH, help="render window width [px] (default: %d)" % WINDOW_WIDTH)
    parser.add_argument("--height", type=int, default=WINDOW_HEIGHT, help="render window height [px] (default: %d)" % WINDOW_HEIGHT)
    parser.add_argument("--multi-samples", type=int, default=MULTI_SAMPLES,
                        help="MSAA sample count for edge anti-aliasing (default: %d)" % MULTI_SAMPLES)
    parser.add_argument("--depo-theta-res", type=int, default=10,
                        help="depo ellipsoid longitude tessellation (default: 10, raise for smoother shells on small depo counts)")
    parser.add_argument("--depo-phi-res", type=int, default=6,
                        help="depo ellipsoid latitude tessellation (default: 6, raise for smoother shells on small depo counts)")

    args = parser.parse_args()
    serve_blobs(
        args.blob_file, depo_file=args.depo_file, port=args.port, scalars=args.scalars,
        v_drift=args.v_drift, t_offset=args.t_offset, response_plane_x=args.response_plane_x,
        window_width=args.width, window_height=args.height, multi_samples=args.multi_samples,
        depo_theta_res=args.depo_theta_res, depo_phi_res=args.depo_phi_res,
    )
