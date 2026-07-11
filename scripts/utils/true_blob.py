"""Ground-truth ("true") blob construction from depo data.

Summary: Builds an independent, geometry-based ground-truth blob for a single
depo, directly comparable to a reconstructed blob node (as returned by
`utils.load.load_graph_nodes(cgraph, 'b')`). This module derives the blob's 2D
(y, z) polygon and time-slice extent independently from a depo's own
position and diffusion sigmas (`extent_long`, `extent_tran`), so it can be
used to evaluate reconstructed-blob position/shape accuracy, not just
charge accuracy.

The per-plane wire geometry used to build the polygon (pitch axis, pitch
projection, strip polygons) lives in `utils.wires` (`PlaneGeometry`,
`build_plane_geometries`), not in this module: this module only combines
already-built `PlaneGeometry` objects across three planes to form a
true-blob polygon and its time slice/charge. See `utils/wires.py` for why
wire geometry is loaded from the full wire-store JSON rather than from the
reconstructed cluster graph's own 'w' nodes.

The three plane strips alone extend unbounded along each wire's own
direction (see `PlaneGeometry.strip_polygon`), so `true_blob_polygon` also
accepts an optional `sensitive_bounds` polygon (from `utils.wires.
face_sensitive_bounds`) to clip the result to the anode face's physical
extent, matching the two synthetic "bounds" ray-grid layers WCT's own
tiling always intersects against (see `docs/true_blob_prototype.md`
section 5.4).

Usage:
    import sys
    sys.path.insert(0, "scripts")
    from utils.load import load_generation_data
    from utils.wires import build_plane_geometries, face_sensitive_bounds
    from utils.true_blob import build_true_blob

    depos = load_generation_data("data/pdhd/test_single_trk/depos-drifted-1.zip", 0)

    wire_store = "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2"
    plane_geoms = build_plane_geometries(wire_store, anode_index=1, face_index=1)
    sensitive_bounds = face_sensitive_bounds(wire_store, anode_index=1, face_index=1)

    blob = build_true_blob(
        plane_geoms,
        t=depos["t"][0], y=depos["y"][0], z=depos["z"][0],
        charge=depos["q"][0], extent_long=depos["L"][0], extent_tran=depos["T"][0],
        speed=1.6 * units.mm / units.us,
        sensitive_bounds=sensitive_bounds,
    )
    # blob == {"polygon": shapely.Polygon or None, "start": ..., "span": ..., "charge": ...}
"""

from utils.slicer import gbounds


def true_blob_polygon(plane_geoms, y, z, extent_tran, nsigma=3.0, sensitive_bounds=None):
    """Builds the true-blob (y, z) polygon for one depo.

    Each plane's pitch range is computed independently from the depo's own
    pitch projection on that plane, out to `nsigma * extent_tran`, then
    snapped to the nearest bounding wire indices via `pg.wire_index_range`
    before being converted to a strip polygon and intersected across all
    planes. This mirrors how a real blob's edges are always exact wire ray
    lines in WCT's RayGrid tiling (`Strip.bounds` in
    `wire-cell-toolkit/util/inc/WireCellUtil/RayGrid.h` is a pair of
    wire-ray indices, not a continuous coordinate), rather than the depo's
    own continuous nsigma cutoff -- a reco blob edge can never fall between
    two wires, since a wire is the smallest unit a real detector can
    resolve a boundary at. Each boundary (`center - nsigma*extent_tran` and
    `center + nsigma*extent_tran`) is independently snapped to whichever of
    its two bracketing wires is actually closer in pitch distance (see
    `PlaneGeometry.nearest_wire_index`), so the true-blob polygon can come
    out either larger or smaller than the raw nsigma cutoff, unlike a
    strategy that always rounds outward.

    If `sensitive_bounds` is given, the polygon is additionally intersected
    with it after the three plane strips, mirroring the two synthetic
    "bounds" ray-grid layers WCT's own `RayGrid::make_blobs()` intersects
    against alongside the wire-plane layers (see `utils.wires.
    face_sensitive_bounds` and `docs/true_blob_prototype.md` section 5.4).
    Intersection is commutative, so intersecting it last here yields the
    same final polygon as intersecting it first, as WCT does.

    Args:
        plane_geoms (list[PlaneGeometry]): Geometries for planes 0, 1, 2.
        y (float), z (float): Depo position.
        extent_tran (float): Depo transverse diffusion sigma.
        nsigma (float): Number of sigma to extend the pitch range.
        sensitive_bounds (shapely.Geometry or None): Optional anode-face
            sensitive-volume (y, z) box, as returned by
            `utils.wires.face_sensitive_bounds`.

    Returns:
        shapely.Geometry or None: The intersection polygon, or None if the
            planes' strips (and, if given, `sensitive_bounds`) do not
            overlap.
    """
    polygon = None
    for pg in plane_geoms:
        center = pg.pitch_of(y, z)
        imin, imax = pg.wire_index_range(center - nsigma * extent_tran, center + nsigma * extent_tran)
        strip = pg.strip_polygon(pg.pitch_vals[imin], pg.pitch_vals[imax])
        polygon = strip if polygon is None else polygon.intersection(strip)
        if polygon.is_empty:
            return None
    if sensitive_bounds is not None:
        polygon = polygon.intersection(sensitive_bounds)
        if polygon.is_empty:
            return None
    return polygon


def true_blob_time_slice(t, extent_long, speed, nsigma=3.0):
    """Returns the (start, end) time-slice range for one depo.

    `extent_long` is a distance-domain diffusion sigma; it is converted to
    the time domain via the drift `speed` before applying `nsigma`, matching
    the convention used by `Gen::DepoFluxSplat`/`Img::BlobDepoFill` in WCT.
    """
    tsigma = extent_long / speed
    return t - nsigma * tsigma, t + nsigma * tsigma


def true_blob_charge(charge, t, extent_long, speed, tmin, tmax):
    """Returns the true-blob charge captured within a time-slice range.

    The (y, z) polygon is not charge-weighted further here: by construction
    a true blob covers exactly one depo, so essentially all of its charge
    belongs to it up to the small tail truncated by `nsigma`. Only the
    time-slice truncation fraction (via `gbounds`) is applied, since it is
    the one axis where the slice range is meaningfully clipped independent
    of the polygon's own nsigma cutoff.
    """
    tsigma = extent_long / speed
    frac = gbounds(tmin, tmax, t, tsigma)
    return abs(charge) * frac


def build_true_blob(plane_geoms, t, y, z, charge, extent_long, extent_tran, speed, nsigma=3.0,
                     sensitive_bounds=None):
    """Builds one true-blob candidate (polygon + time slice + charge) from a single depo.

    Args:
        sensitive_bounds (shapely.Geometry or None): Optional anode-face
            sensitive-volume (y, z) box passed through to
            `true_blob_polygon`; see that function for details.

    Returns:
        dict: {"polygon": shapely.Geometry or None, "start": float,
            "span": float, "charge": float}.
    """
    polygon = true_blob_polygon(plane_geoms, y, z, extent_tran, nsigma, sensitive_bounds)
    tmin, tmax = true_blob_time_slice(t, extent_long, speed, nsigma)
    charge_val = true_blob_charge(charge, t, extent_long, speed, tmin, tmax)
    return {"polygon": polygon, "start": tmin, "span": tmax - tmin, "charge": charge_val}


def build_true_blobs(plane_geoms, depos, speed, nsigma=3.0, sensitive_bounds=None):
    """Builds one true blob per depo in a `load_generation_data`-style dict of arrays.

    Args:
        plane_geoms (list[PlaneGeometry]): Geometries for planes 0, 1, 2, as
            returned by `utils.wires.build_plane_geometries`.
        depos (dict): Dict of arrays with keys t, q, x, y, z, L, T, as
            returned by `utils.load.load_generation_data`.
        speed (float): Drift speed used to convert `L` (extent_long) to the
            time domain.
        nsigma (float): Number of sigma to extend both the polygon and the
            time slice.
        sensitive_bounds (shapely.Geometry or None): Optional anode-face
            sensitive-volume (y, z) box, as returned by
            `utils.wires.face_sensitive_bounds`, applied to every depo.

    Returns:
        list[dict]: One true-blob dict (see `build_true_blob`) per depo.
    """
    ndepos = len(depos["t"])
    blobs = []
    for i in range(ndepos):
        blobs.append(build_true_blob(
            plane_geoms,
            t=depos["t"][i], y=depos["y"][i], z=depos["z"][i],
            charge=depos["q"][i], extent_long=depos["L"][i], extent_tran=depos["T"][i],
            speed=speed, nsigma=nsigma, sensitive_bounds=sensitive_bounds,
        ))
    return blobs
