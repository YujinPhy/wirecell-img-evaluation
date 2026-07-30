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

from position_center_comparison import classify_blob, convert_time2x, depo_center
from utils.load import load_cluster_data, load_generation_data, load_graph_nodes

pv.OFF_SCREEN = True
pv.global_theme.allow_empty_mesh = True  # blob/weighted-center point actors may end up with zero points

# Generic fallback constants -- match `wirecell.img.converter.undrift_blobs`'s
# own defaults, not any particular detector's calibration. Pass
# --v-drift/--t-offset/--response-plane-x explicitly for a calibrated detector
# (e.g. PDHD: 1.6, 314.5, 3430.47 -- see docs/time_offset_calibration.md).
V_DRIFT = 1.56           # [mm/us]
T_OFFSET = 0.0          # [us]
RESPONSE_PLANE_X = 0.0  # [mm]

WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
MULTI_SAMPLES = 8
DEPO_NSIGMA = 3.0  # depo ellipsoid boundary, in sigma (matches the report's 3-sigma convention)
BLOB_CLIM_LOW_PCT = 5.0   # percentile of `--scalars` used as the color range's low end
BLOB_CLIM_HIGH_PCT = 95.0  # percentile of `--scalars` used as the color range's high end

# ==== Depo/blob center-point matching (mirrors scripts/depo_blob_center.ipynb) ====
VAL_THR = 0.0             # minimum blob charge [e-]; blobs below this are unmatched
NSIGMA_TRANS_RANGE = 5.0  # unmatched transverse-distance threshold, in the depo's sigma_T
DEPO_RANGE_NSIGMA = 3.0   # depo's valid time boundary, in the depo's sigma_t
CENTER_POINT_SIZE = 18

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

    Also returns each blob's own centroid (mean of its extruded solid's actual
    vertices, both faces), keyed by `ident`. This must come from `pts` here --
    not re-derived later from `start + span/2` via `convert_time2x`.
    `x = response_plane_x - v_drift*t` decreases as t increases, so a blob's
    corner (at x(start), the slice's earliest/largest-x tick) must be
    extruded in the *negative* x direction by `span` to cover the slice's
    actual physical footprint [x(start)-span_mm, x(start)] -- hence
    `converter.extrude(pts, -ndata["span"])` below. Extruding with a plain
    `+span` (the upstream default direction) put the mesh, and this
    centroid, a full span-width past the correct position.
    """
    all_points = []
    faces = []
    cell_scalars = defaultdict(list)
    blob_centers = {}
    offset = 0
    for _, ndata in cgraph.nodes(data=True):
        if ndata.get("code") != "b":
            continue
        pts = converter.orderpoints(list(ndata["corners"]))
        pts, cells = converter.extrude(pts, -ndata["span"])
        blob_centers[ndata["ident"]] = np.asarray(pts, dtype=float).mean(axis=0)
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
        return None, {}

    poly = pv.PolyData(np.asarray(all_points, dtype=float), faces=np.asarray(faces, dtype=np.int64))
    for name, values in cell_scalars.items():
        poly.cell_data[name] = np.asarray(values, dtype=float)
    return poly, blob_centers


def _depo_ellipsoids(depo_file, v_drift, t_offset, response_plane_x, n_sigma=3.0, theta_res=16, phi_res=10):
    """Builds one n-sigma ellipsoid surface per depo, centered on the depo's own center.

    Each depo's charge spreads as an anisotropic 3D Gaussian: sigma=`L`
    along the drift/longitudinal (x) axis, sigma=`T` isotropically in the
    transverse (y, z) plane. `L`/`T` are taken from Gen0 (post-drift), the
    diffused-at-readout values -- Gen1 (pre-drift) always has `L`=`T`=0
    since no diffusion has happened yet at creation. The drawn ellipsoid's
    semi-axes are `(n_sigma*L, n_sigma*T, n_sigma*T)` -- i.e. a single
    n-sigma boundary surface (matching the report's "3-sigma boundary"
    convention, see docs/evaluation/position_center_center_comparison_report.md's
    "Depo & Blob 구분" section), not the earlier multi-shell density
    gradient this replaced.

    Position (x, y, z): recovered from Gen0's own drift time (`t`) plus
    `t_offset` via `convert_time2x`, the same formula
    `position_center_comparison.py`'s `depo_center()` uses -- this is the
    one place in this file `t_offset` is actually used, since (unlike
    depos) a blob's own `start`/`span` are already on the reco clock and
    need no such shift (see `_load_and_undrift`'s docstring). y/z are
    taken from Gen0 (post-drift) to match `depo_center()`'s convention
    exactly. (An earlier version took (x, y, z) straight from Gen1, the
    true pre-drift generation location -- that doesn't line up with the
    blobs' reco-clock x, off by ~503mm = `v_drift*t_offset` for PDHD's
    calibrated constants, which was why depos and blobs never visually
    overlapped no matter how the camera was framed.)

    One `vtkGlyph3D` call places a unit-sphere copy at every depo's
    position, scaled per-axis via `SetScaleModeToScaleByVectorComponents`
    -- i.e. every depo's ellipsoid in a single vectorized filter call,
    instead of building `n_depos` individual meshes in a Python loop (the
    latter took ~215s for 5000 depos; this takes well under a second).

    Args:
        depo_file (str): Path to a `depos-drifted-<N>.zip` file.
        v_drift, t_offset, response_plane_x: same undrift constants used
            elsewhere in this file (`_load_and_undrift`, `serve_blobs`),
            needed here to place depos on the same reco-clock x as the
            blobs (see above).
        n_sigma (float): sigma multiple the ellipsoid boundary is drawn at.
        theta_res, phi_res (int): unit-sphere template resolution.

    Returns:
        pyvista.PolyData or None: Merged ellipsoids with a point-data array
            `charge` (`|q|`, for coloring), or None if the depo file has no
            data.
    """
    gen0 = load_generation_data(depo_file, 0)
    if gen0 is None:
        return None

    L, T, q = gen0["L"], gen0["T"], np.abs(gen0["q"])
    valid = (L > 0) & (T > 0)
    if not np.any(valid):
        return None
    t_us = np.asarray(gen0["t"])[valid] / 1000.0 + t_offset
    x = convert_time2x(t_us, v_drift, response_plane_x)
    y, z = gen0["y"][valid], gen0["z"][valid]
    L, T, q = L[valid], T[valid], q[valid]

    points = vtk.vtkPoints()
    points.SetData(vtk_np.numpy_to_vtk(np.column_stack([x, y, z]).copy(), deep=True))

    pdata = vtk.vtkPolyData()
    pdata.SetPoints(points)
    scale_vec = vtk_np.numpy_to_vtk(np.column_stack([n_sigma * L, n_sigma * T, n_sigma * T]).copy(), deep=True)
    scale_vec.SetName("scale_vec")
    pdata.GetPointData().SetVectors(scale_vec)
    charge = vtk_np.numpy_to_vtk(q.copy(), deep=True)
    charge.SetName("charge")
    pdata.GetPointData().SetScalars(charge)

    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(1.0)
    sphere.SetThetaResolution(theta_res)
    sphere.SetPhiResolution(phi_res)

    glyph = vtk.vtkGlyph3D()
    glyph.SetSourceConnection(sphere.GetOutputPort())
    glyph.SetInputData(pdata)
    glyph.SetVectorModeToUseVector()
    glyph.SetScaleModeToScaleByVectorComponents()
    glyph.OrientOff()
    glyph.Update()
    return pv.wrap(glyph.GetOutput())


def _select_blobs_for_depo(blobs, depos, depo_idx, v_drift, t_offset, response_plane_x,
                            val_thr=VAL_THR, nsigma_trans=NSIGMA_TRANS_RANGE,
                            depo_range_nsigma=DEPO_RANGE_NSIGMA):
    """Classifies every blob in `blobs` against depo_idx via classify_blob (time-window +
    charge + transverse-distance check), collapsing its "ghost"/"out_of_range" categories
    into a single "unmatched" bucket. Mirrors scripts/depo_blob_center.ipynb's
    select_blobs_for_depo, except the time-window check is kept here (that notebook cell
    dropped it, which let far-off-in-time blobs match too).

    Returns:
        dict: {"matched": list[dict], "unmatched": list[tuple[dict, str, str]]}
    """
    matched, unmatched = [], []
    for b in blobs:
        category, reason = classify_blob(b, depos, depo_idx, v_drift, t_offset, response_plane_x,
                                          val_thr, nsigma_trans, depo_range_nsigma)
        if category == "matched":
            matched.append(b)
        else:
            unmatched.append((b, category, reason))
    return {"matched": matched, "unmatched": unmatched}


def _points_polydata(xyz_rows):
    """Builds a pyvista.PolyData point cloud from a list of (x, y, z) rows [mm]."""
    if not xyz_rows:
        return pv.PolyData(np.empty((0, 3)))
    return pv.PolyData(np.asarray(xyz_rows, dtype=float))


def _blob_color_clim(blob_mesh, scalars, low_pct=BLOB_CLIM_LOW_PCT, high_pct=BLOB_CLIM_HIGH_PCT):
    """Picks a percentile-based [vmin, vmax] color range for `scalars`, instead of
    letting pyvista default to the field's raw [min, max].

    A single track's blobs mostly carry similar dE/dx charge, with only a
    handful of edge/partial blobs sitting well below the rest (e.g.
    `test_single_trk`'s 113 blobs: ~108 of them fall in [16000, 20200], but
    5 sit at [0, 15700]) -- the raw min/max range stretches from that few
    outliers' low end all the way to the bulk's high end, so under a linear
    colormap the entire bulk collapses into one nearly-uniform color at the
    top of the scale (verified: rendering `test_single_trk` with the raw
    [0, 20162] range makes essentially every blob along the track look the
    same yellow, which is what looked like "charge isn't reflected").
    Clipping to the [5th, 95th] percentile instead spans the color range
    across the bulk's own spread, so blob-to-blob charge differences within
    a track become visible; the few outliers below/above just saturate to
    the colormap's endpoint colors, same as they would with any clim.

    Returns:
        list[float, float] or None: `[vmin, vmax]`, or None if `scalars` has
        no data or is constant (degenerate range; let pyvista use its default).
    """
    if scalars not in blob_mesh.cell_data:
        return None
    values = blob_mesh.cell_data[scalars]
    if values.size == 0:
        return None
    vmin, vmax = np.percentile(values, [low_pct, high_pct])
    if vmin == vmax:
        return None
    return [float(vmin), float(vmax)]


def serve(blob_file, depo_file=None, port=8080, scalars="val",
                 v_drift=V_DRIFT, t_offset=T_OFFSET, response_plane_x=RESPONSE_PLANE_X,
                 window_width=WINDOW_WIDTH, window_height=WINDOW_HEIGHT, multi_samples=MULTI_SAMPLES,
                 depo_nsigma=DEPO_NSIGMA, depo_theta_res=16, depo_phi_res=10,
                 blob_clim_low_pct=BLOB_CLIM_LOW_PCT, blob_clim_high_pct=BLOB_CLIM_HIGH_PCT):
    _stop_previous_server(port)
    _register_current_server(port)

    cgraph = load_cluster_data(blob_file)
    if cgraph is None:
        sys.exit(1)
    blob_mesh, blob_mesh_centers = _blobs_to_polydata(cgraph)
    if blob_mesh is None:
        print(f"[ERROR] No reco blobs found in {blob_file}")
        sys.exit(1)

    depo_mesh = None
    depos = None
    center_blobs = []
    if depo_file:
        print(f"[INFO] Building depo {depo_nsigma:.1f}-sigma ellipsoids...")
        depo_mesh = _depo_ellipsoids(depo_file, v_drift, t_offset, response_plane_x, n_sigma=depo_nsigma, theta_res=depo_theta_res, phi_res=depo_phi_res)
        if depo_mesh is None:
            print(f"[WARNING] Failed to load depo file: {depo_file}")
        depos = load_generation_data(depo_file, 0)
        # A second, non-undrifted load of blob_file -- classify_blob (matching, i.e.
        # *which* blobs count as this depo's) needs each blob's raw (ns) start/span and
        # its own y/z corner-mean to compare against the depo's time window and
        # transverse distance; that part is unaffected by _blobs_to_polydata's x-bug fix
        # since it never compares against the rendered mesh, only against other
        # independently-raw-computed positions. The actual point *positions* drawn below
        # come from blob_mesh_centers (mesh-consistent), not from this raw data's own x.
        raw_cgraph = load_cluster_data(blob_file)
        center_blobs = load_graph_nodes(raw_cgraph, "b") if raw_cgraph is not None else []

    pv.global_theme.multi_samples = multi_samples
    plotter = pv.Plotter(
        window_size=(window_width, window_height),
        line_smoothing=True,
        point_smoothing=True,
        polygon_smoothing=True,
    )
    blob_clim = _blob_color_clim(blob_mesh, scalars, blob_clim_low_pct, blob_clim_high_pct)
    blob_actor = plotter.add_mesh(blob_mesh, scalars=scalars, show_edges=True, clim=blob_clim, name="blobs")
    depo_actor = None
    if depo_mesh is not None:
        # Fixed opacity (not a scalar-driven range like the old density
        # shells) -- with widely varying charge across depos, an
        # opacity=[min,max] range mapped to "charge" would map most depos'
        # points near-transparent whenever even one depo has much more
        # charge than the rest, making the overlay effectively invisible.
        # A flat 0.35 is always visible regardless of the file's charge
        # spread; "charge" still drives *color* (cmap) for a visual cue.
        depo_actor = plotter.add_mesh(
            depo_mesh, scalars="charge", cmap="plasma", opacity=0.35, show_edges=True,
            show_scalar_bar=False, name="depos",
        )

    # Every depo's own center (red), its matched blobs' individual centers (cyan),
    # and each depo's charge-weighted center (lime), computed once up front for every
    # depo in the file and always shown (no per-depo selection step). Different sizes
    # (not just colors) since a depo's matched blobs are often nearly coincident with
    # each other (sub-mm apart), and same-size same-depth points z-fight into an
    # indistinct dark blob when stacked on top of each other.
    depo_center_actor = None
    blob_center_actor = None
    weighted_center_actor = None
    if depos is not None and len(depos["t"]) > 0:
        dc_pts, bc_pts, wc_pts = [], [], []
        n_matched_total = 0
        for depo_idx in range(len(depos["t"])):
            dc_pts.append(depo_center(depos, depo_idx, v_drift, t_offset, response_plane_x)[1:4])

            groups = _select_blobs_for_depo(center_blobs, depos, depo_idx, v_drift, t_offset, response_plane_x)
            matched = groups["matched"]
            n_matched_total += len(matched)
            matched_xyz = [blob_mesh_centers[b["ident"]] for b in matched]
            bc_pts.extend(matched_xyz)
            weights = np.array([b["val"] for b in matched])
            if matched_xyz and weights.sum() > 0:
                wc_pts.append(np.average(np.asarray(matched_xyz), axis=0, weights=weights))
            elif matched_xyz:
                wc_pts.append(np.asarray(matched_xyz).mean(axis=0))
        print(f"[INFO] Center points: {len(dc_pts)} depo centers, {n_matched_total} matched blob centers "
              f"across {len(depos['t'])} depos, {len(wc_pts)} charge-weighted centers")

        depo_center_actor = plotter.add_mesh(
            _points_polydata(dc_pts), style="points", render_points_as_spheres=True,
            point_size=CENTER_POINT_SIZE, color="red", name="depo_center_point",
        )
        blob_center_actor = plotter.add_mesh(
            _points_polydata(bc_pts), style="points", render_points_as_spheres=True,
            point_size=CENTER_POINT_SIZE * 0.6, color="cyan", name="blob_center_points",
        )
        weighted_center_actor = plotter.add_mesh(
            _points_polydata(wc_pts), style="points", render_points_as_spheres=True,
            point_size=CENTER_POINT_SIZE * 1.4, color="lime", name="weighted_center_point",
        )

    # pyvista's add_mesh(reset_camera=None) only resets the camera when
    # `not plotter._first_time and not plotter.camera_set` -- i.e. never on
    # the very first add_mesh call (that flag is exactly what a later
    # plotter.show() would normally clear). Without a depo overlay, blobs
    # is the *only* add_mesh call, so the camera is left at pyvista's
    # trivial (0,0,1)-looking-at-(0,0,0) default -- unrelated to where the
    # actual geometry sits -- which is why blobs/depos rendered tiny (or
    # invisible) and scrolling to zoom did nothing useful (it was dollying
    # toward the wrong point in space). One explicit reset here, after every
    # actor is in the scene, makes the initial framing correct regardless of
    # how many add_mesh calls happened above.
    plotter.reset_camera()

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

    def _reset_view(**kwargs):
        """"Reset View" toolbar button: refits the camera to whatever is
        currently displayed (full scene, or the current blob selection if
        one is active) -- a manual escape hatch for whenever
        scrolling to zoom isn't converging fast enough, since one dolly
        step only changes distance by a fixed ratio and can take many
        clicks to cross a large scale gap (e.g. a detector-spanning depo
        scan down to one 5mm blob)."""
        plotter.reset_camera(bounds=getattr(blob_actor, "_filtered_dataset", blob_mesh).bounds)
        if view is not None:
            view.update()

    @state.change("blob_index_filter")
    def _apply_filters(blob_index_filter, **kwargs):
        """Blob-index filter: restricts the rendered blob mesh to one blob (by its
        `ident`), or shows all of them again once cleared. Also re-frames the camera
        on the selected blob (`reset_camera(bounds=...)`) rather than leaving it fit
        to the *whole* scene -- with many widely-scattered blobs, the whole-scene view
        can make one selected blob too small to see, and scrolling alone takes a long
        time to zoom in that far (see `_reset_view`).
        """
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
        blob_dataset = blob_mesh if idx is None else blob_mesh.extract_cells(np.where(blob_idents == idx)[0])
        blob_actor._filtered_dataset = blob_dataset  # keep a strong ref alongside the mapper's VTK-side one
        blob_actor.mapper.SetInputData(blob_dataset)
        blob_actor.mapper.Modified()

        fit_bounds = list(blob_dataset.bounds) if idx is not None and blob_dataset.n_cells > 0 else None
        plotter.reset_camera(bounds=fit_bounds)
        if view is not None:
            view.update()

    @state.change("show_depo_center")
    def _toggle_depo_center(show_depo_center, **kwargs):
        if depo_center_actor is not None:
            depo_center_actor.visibility = show_depo_center
            if view is not None:
                view.update()

    @state.change("show_blob_centers")
    def _toggle_blob_centers(show_blob_centers, **kwargs):
        if blob_center_actor is not None:
            blob_center_actor.visibility = show_blob_centers
            if view is not None:
                view.update()

    @state.change("show_weighted_center")
    def _toggle_weighted_center(show_weighted_center, **kwargs):
        if weighted_center_actor is not None:
            weighted_center_actor.visibility = show_weighted_center
            if view is not None:
                view.update()

    with SinglePageLayout(server) as layout:
        layout.title.set_text(f"Reco blobs: {os.path.basename(blob_file)}")
        with layout.content:
            with vuetify3.VContainer(fluid=True, classes="pa-0 fill-height"):
                view = plotter_ui(plotter)
        with layout.toolbar:
            vuetify3.VSpacer()
            # pyvista's own built-in menu (the small "..." icon at the
            # scene's top-left) already has a "Reset Camera" button, but
            # it's collapsed/easy to miss; this one is always visible in the
            # toolbar as a more discoverable way to re-fit the view (see
            # _reset_view -- fits to whatever's currently shown, i.e. the
            # active blob/depo-slice selection if any, else the full scene).
            vuetify3.VBtn(
                "Reset View", variant="text", density="compact",
                click=_reset_view, classes="mx-1",
            )
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
                if blob_center_actor is not None:
                    vuetify3.VDivider(classes="my-2")
                    vuetify3.VCheckbox(v_model=("show_depo_center", True), label="Depo center",
                                        hide_details=True, density="compact", classes="mx-2")
                    vuetify3.VCheckbox(v_model=("show_blob_centers", True), label="Matched blob centers",
                                        hide_details=True, density="compact", classes="mx-2")
                    vuetify3.VCheckbox(v_model=("show_weighted_center", True), label="Charge-weighted center",
                                        hide_details=True, density="compact", classes="mx-2")
                    vuetify3.VCardText(
                        f"{len(dc_pts)} depo centers, {n_matched_total} matched blob centers, "
                        f"{len(wc_pts)} charge-weighted centers, across {len(depos['t'])} depos",
                        style="font-size: 12px;",
                    )

    print(f"[INFO] {blob_mesh.n_cells} blob faces loaded from {blob_file}"
          + (f", depo ellipsoids ({depo_mesh.n_cells} cells) from {depo_file}"
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
    parser.add_argument("--blob-clim-low-pct", type=float, default=BLOB_CLIM_LOW_PCT,
                        help="low-end percentile of --scalars used for the blob color range, so a few low-charge "
                             "outlier blobs don't wash out the color contrast across the rest (default: %.1f)" % BLOB_CLIM_LOW_PCT)
    parser.add_argument("--blob-clim-high-pct", type=float, default=BLOB_CLIM_HIGH_PCT,
                        help="high-end percentile of --scalars used for the blob color range (default: %.1f)" % BLOB_CLIM_HIGH_PCT)

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
    parser.add_argument("--depo-nsigma", type=float, default=DEPO_NSIGMA,
                        help="depo ellipsoid boundary, in sigma (default: %.1f)" % DEPO_NSIGMA)
    parser.add_argument("--depo-theta-res", type=int, default=16,
                        help="depo ellipsoid longitude tessellation (default: 16, one ellipsoid per depo now, so this can be higher than the old multi-shell default)")
    parser.add_argument("--depo-phi-res", type=int, default=10,
                        help="depo ellipsoid latitude tessellation (default: 10)")

    args = parser.parse_args()
    serve(
        args.blob_file, depo_file=args.depo_file, port=args.port, scalars=args.scalars,
        v_drift=args.v_drift, t_offset=args.t_offset, response_plane_x=args.response_plane_x,
        window_width=args.width, window_height=args.height, multi_samples=args.multi_samples,
        depo_nsigma=args.depo_nsigma, depo_theta_res=args.depo_theta_res, depo_phi_res=args.depo_phi_res,
        blob_clim_low_pct=args.blob_clim_low_pct, blob_clim_high_pct=args.blob_clim_high_pct,
    )
