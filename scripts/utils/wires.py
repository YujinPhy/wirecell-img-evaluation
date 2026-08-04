"""Wire-Cell wire data file structure and Conventions 

Summary: Loads WCT wire-store geometry (via `wirecell.util.wires.persist`/ `schema`) and exposes `PlaneGeometry`, which projects an arbitrary (y, z)
point onto a wire plane's pitch axis and builds a long "strip" polygon for
a pitch range. This is the wire-geometry building block that
`utils.true_blob` combines across three planes to form a true-blob
polygon.

 Also exposes `face_sensitive_bounds`, an approximate sensitive-
volume (y, z) bounding box used to clip that polygon, analogous to the two
synthetic ray-grid "bounds" layers WCT's own tiling intersects against (see
`docs/true_blob_prototype.md` section 5.4). See
`docs/wirecell_wires_reference.md` for the full wire-geometry data-model
reference (Store/Anode/Face/Plane/Wire/Point) and
`docs/true_blob_prototype.md` for how this module is used end to end.

Usage:
    import sys
    sys.path.insert(0, "scripts")
    from utils.wires import build_plane_geometries, face_sensitive_bounds

    plane_geoms = build_plane_geometries(
        "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2",
        anode_index=1, face_index=1,
    )
    pitch = plane_geoms[0].pitch_of(y=3000.0, z=1350.0)
    strip = plane_geoms[0].strip_polygon(pitch - 5.0, pitch + 5.0)

    sensitive_bounds = face_sensitive_bounds(
        "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2",
        anode_index=1, face_index=1,
    )
"""

import numpy as np
from shapely.geometry import Polygon, box
from wirecell.util.wires import persist as wire_persist


class PlaneGeometry:
    """Pitch-axis projection for one wire plane, built from its full wire list.

    `wire_axis`/`pitch_axis` are derived from the wires' own shared
    direction (each wire's tail->head unit vector, averaged), not from a
    PCA/SVD fit on wire midpoints. A midpoint PCA was tried first and
    measured to be wrong by ~39 degrees on this project's U plane: induction
    planes are trapezoidal, so wire length (and therefore how far a wire's
    midpoint sits from the plane's overall center, along the WIRE direction)
    varies a lot with position across the plane -- enough that "direction of
    maximum midpoint variance" stops tracking the true pitch direction at
    all and instead partly reflects that trapezoidal length gradient. Wire
    direction itself has no such bias (a wire's direction doesn't depend on
    where it sits in the trapezoid), so it is the robust quantity to average.

    This assumes `wire_endpoints` already has a consistent tail/head
    orientation across all wires (`build_plane_geometries` guarantees this
    via `_apply_wirecell_corrections`/`_order_fix`) -- otherwise, per-wire
    direction vectors pointing opposite ways would partially cancel in the
    average instead of reinforcing.
    """

    #: Half-length used to extend a strip polygon along the wire direction,
    #: far beyond any real detector's extent, so a strip behaves like an
    #: infinite band bounded only in the pitch direction.
    _STRIP_HALF_LENGTH = 1.0e5

    def __init__(self, wire_endpoints):
        tails3 = np.array([tail for tail, _head in wire_endpoints])
        heads3 = np.array([head for _tail, head in wire_endpoints])
        mids_yz = 0.5 * (tails3[:, 1:3] + heads3[:, 1:3])

        self.origin = mids_yz.mean(axis=0)

        wire_units = (heads3 - tails3)
        wire_units = wire_units / np.linalg.norm(wire_units, axis=1, keepdims=True)
        mean_dir = wire_units.mean(axis=0)
        mean_dir[0] = 0.0  # project into the Y-Z plane
        mean_dir = mean_dir[1:3] / np.linalg.norm(mean_dir)
        self.wire_axis = mean_dir

        # pitch_axis = X-hat cross wire_axis, WCT's own convention so that
        # increasing wire index means increasing pitch (`WireSchema.h:179-181`,
        # `docs/geometry/wirecell_wires_reference.md` section 4.2).
        self.pitch_axis = np.array([-self.wire_axis[1], self.wire_axis[0]])

        self.pitch_vals = (mids_yz - self.origin) @ self.pitch_axis

        self.nwires = len(wire_endpoints)

    def pitch_of(self, y, z):
        """Projects a (y, z) point onto this plane's pitch axis."""
        return np.dot(np.array([y, z]) - self.origin, self.pitch_axis)

    def nearest_wire_index(self, pitch):
        """Returns the index of the single wire closest to a pitch coordinate.

        `np.searchsorted` gives the insertion index `idx` such that
        `pitch_vals[idx - 1] <= pitch < pitch_vals[idx]`; the two candidate
        wires bounding `pitch` are therefore `idx - 1` and `idx` (clipped to
        the plane's valid range when `pitch` falls outside all wires), and
        whichever of the two has the smaller `abs(pitch_vals[i] - pitch)` is
        returned.
        """
        idx = int(np.searchsorted(self.pitch_vals, pitch))
        if idx <= 0:
            return 0
        if idx >= self.nwires:
            return self.nwires - 1
        lo, hi = idx - 1, idx
        if abs(pitch - self.pitch_vals[lo]) <= abs(self.pitch_vals[hi] - pitch):
            return lo
        return hi

    def wire_index_range(self, pitch_min, pitch_max):
        """Returns the [imin, imax] wire indices closest to a pitch-coordinate range.

        `imin`/`imax` are each the single nearest wire (see
        `nearest_wire_index`) to `pitch_min`/`pitch_max` independently, not
        wires guaranteed to fully contain the input range: for a given
        boundary point, the wire on the far side is only picked if it is
        actually closer to that point than the wire on the near side, and
        the near-side wire is picked otherwise (which can happen, e.g. when
        `pitch_min`/`pitch_max` sit deep inside a wire's pitch cell). Used by
        `utils.true_blob.true_blob_polygon` to snap a strip's pitch bounds
        to real wire positions (via `self.pitch_vals[imin]`/`[imax]`),
        matching how a real blob's edges always sit exactly on a wire ray
        line rather than at an arbitrary continuous coordinate.
        """
        imin = self.nearest_wire_index(pitch_min)
        imax = self.nearest_wire_index(pitch_max)
        return imin, imax

    def strip_polygon(self, pitch_min, 
    pitch_max):
        """Returns a long band spanning [pitch_min, pitch_max] in the pitch direction.

        The band extends `_STRIP_HALF_LENGTH` in both directions along the
        wire axis, standing in for an unbounded wire-region strip.
        """
        half = self._STRIP_HALF_LENGTH
        corners = [
            self.origin + pitch_min * self.pitch_axis - half * self.wire_axis,
            self.origin + pitch_min * self.pitch_axis + half * self.wire_axis,
            self.origin + pitch_max * self.pitch_axis + half * self.wire_axis,
            self.origin + pitch_max * self.pitch_axis - half * self.wire_axis,
        ]
        return Polygon(corners)


def _order_fix(tails, heads):
    """Replicates WCT's `plane_fixer_order` (`WireSchema.cxx:154-256`).

    Sorts wires by their center's projected position along the plane's
    dominant transverse axis (`wire_order_axis`: Y if the first wire runs
    near-vertically i.e. along Z, else Z), then enforces a consistent
    tail/head endpoint direction convention (so `direction`'s vector sum,
    below, doesn't have wires partially cancel by pointing opposite ways).

    Args:
        tails, heads (np.ndarray): `(n, 3)` wire tail/head (x, y, z), in
            on-disk `plane.wires` order.

    Returns:
        tuple[np.ndarray, np.ndarray]: reordered, endpoint-direction-fixed
            `(tails, heads)`.
    """
    ycen = 0.5 * (tails[:, 1] + heads[:, 1])
    zcen = 0.5 * (tails[:, 2] + heads[:, 2])

    wdir0 = heads[0] - tails[0]
    wdir0 = wdir0 / np.linalg.norm(wdir0)
    axis_is_y = abs(wdir0[2]) > 0.9999  # near-Z wire -> sort/order by Y

    if axis_is_y:
        imin, imax = np.argmin(ycen), np.argmax(ycen)
    else:
        imin, imax = np.argmin(zcen), np.argmax(zcen)
    origin_y = 0.5 * (ycen[imin] + ycen[imax])
    origin_z = 0.5 * (zcen[imin] + zcen[imax])
    dy, dz = ycen[imax] - ycen[imin], zcen[imax] - zcen[imin]
    norm = np.hypot(dy, dz)
    dy, dz = dy / norm, dz / norm

    pos = (ycen - origin_y) * dy + (zcen - origin_z) * dz
    order = np.argsort(pos, kind="stable")
    tails, heads = tails[order], heads[order]

    if axis_is_y:
        swap = heads[:, 2] > tails[:, 2]
    else:
        swap = heads[:, 1] < tails[:, 1]
    new_tails = np.where(swap[:, None], heads, tails)
    new_heads = np.where(swap[:, None], tails, heads)
    return new_tails, new_heads


def _direction_fix(tails, heads):
    """Replicates WCT's `plane_fixer_direction` (`WireSchema.cxx:259-284`).

    Rotates every wire about its own center so all wires become exactly
    parallel, sharing the average direction (projected into the Y-Z
    plane) of the original wires. Wire centers and lengths are preserved.

    Args:
        tails, heads (np.ndarray): `(n, 3)`, in `_order_fix`'s output order.

    Returns:
        tuple[np.ndarray, np.ndarray]: `(tails, heads)` with a common direction.
    """
    rv = heads - tails
    half = 0.5 * np.linalg.norm(rv, axis=1)
    wdir = rv.sum(axis=0)
    wdir[0] = 0.0  # bring into Y-Z plane
    wdir = wdir / np.linalg.norm(wdir)

    centers = 0.5 * (tails + heads)
    new_heads = centers + half[:, None] * wdir
    new_tails = centers - half[:, None] * wdir
    return new_tails, new_heads


def _pitch_fix(tails, heads):
    """Replicates WCT's `plane_fixer_pitch` (`WireSchema.cxx:287-350`).

    Translates every wire (except the middle one, wire-in-plane index
    `nwires // 2`, which stays fixed) along the common pitch direction so
    wires become uniformly spaced. The common pitch is the mean of the
    perpendicular offset between each consecutive wire pair (`ray_pitch`,
    `util/src/Point.cxx:63-80` reduces to a perpendicular-rejection of the
    center-to-center vector once all wires share one direction, i.e. after
    `_direction_fix`). All wire X's are also set to the mean X of all wire
    centers, matching the C++ side, though `PlaneGeometry` never reads X.

    Args:
        tails, heads (np.ndarray): `(n, 3)`, parallel wires (output of
            `_direction_fix`), in `_order_fix`'s order.

    Returns:
        tuple[np.ndarray, np.ndarray]: `(tails, heads)` with uniform pitch.
    """
    n = len(tails)
    nhalf = n // 2

    tails = tails.copy()
    heads = heads.copy()
    xmean = np.mean(0.5 * (tails[:, 0] + heads[:, 0]))
    tails[:, 0] = xmean
    heads[:, 0] = xmean

    direction = heads[0] - tails[0]
    direction = direction / np.linalg.norm(direction)
    centers = 0.5 * (tails + heads)

    # Mean pitch: average perpendicular offset between consecutive wires.
    deltas = centers[1:] - centers[:-1]
    perp = deltas - (deltas @ direction)[:, None] * direction
    pmean = perp.mean(axis=0)
    pmag = np.linalg.norm(pmean)
    pdir = pmean / pmag

    origin = centers[nhalf].copy()
    for i in range(n):
        if i == nhalf:
            continue
        want_pitch = (i - nhalf) * pmag
        have_pitch = np.dot(pdir, centers[i] - origin)
        diff = (want_pitch - have_pitch) * pdir
        tails[i] += diff
        heads[i] += diff
    return tails, heads


def _apply_wirecell_corrections(wire_endpoints):
    """Reproduces WCT's default `Correction::pitch` wire-schema corrections.

    `wirecell.util.wires.persist.load()` returns `plane.wires` exactly as
    stored on disk: original order, original (tail, head) coordinates.
    WCT's C++ side does not use that directly: `WireSchemaFile`'s default
    `correction` config is `Correction::pitch` (`wire-cell-toolkit/gen/src/
    WireSchemaFile.cxx:23-25`, not overridden anywhere in this project's
    jsonnet), which cumulatively applies `_order_fix` + `_direction_fix` +
    `_pitch_fix` (see `docs/geometry/wirecell_wires_reference.md` section
    4) before `AnodePlane`/`Pimpos` ever see the wires. `plane->wires()[i]`
    and `Pimpos::region_binning()`'s bin index `i` (e.g. `wires[pbin]` in
    `DepoFluxSplat.cxx`) refer to THIS corrected order/geometry, not the
    raw on-disk one -- skipping `_direction_fix`/`_pitch_fix` leaves wire
    order right but wire (y, z) positions off by up to ~100mm (confirmed
    empirically on this project's U/V planes).

    Args:
        wire_endpoints (list[tuple]): `[((tail.x,y,z), (head.x,y,z)), ...]`
            in on-disk `plane.wires` order.

    Returns:
        list[tuple]: The corrected `(tail, head)` tuples, in WCT's order.
    """
    tails = np.array([tail for tail, _head in wire_endpoints], dtype=float)
    heads = np.array([head for _tail, head in wire_endpoints], dtype=float)
    tails, heads = _order_fix(tails, heads)
    tails, heads = _direction_fix(tails, heads)
    tails, heads = _pitch_fix(tails, heads)
    return list(zip(map(tuple, tails), map(tuple, heads)))


def build_plane_geometries(wire_store_path, anode_index, face_index):
    """Builds one `PlaneGeometry` per wire plane (U, V, W) for a given anode face.

    Args:
        wire_store_path (str): Path to a WCT wire-geometry JSON (plain or
            `.bz2`), e.g. `wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2`.
        anode_index (int): Index into `store.anodes` (not necessarily the
            anode's `ident`).
        face_index (int): Index into `store.anodes[anode_index].faces`.

    Returns:
        list[PlaneGeometry]: Geometries for planes 0, 1, 2, in that order.
            Each plane's wires are corrected to match WCT's own wire/pitch-bin
            index and geometry convention (see `_apply_wirecell_corrections`),
            not raw on-disk `plane.wires` order/coordinates.
    """
    store = wire_persist.load(wire_store_path)
    anode = store.anodes[anode_index]
    face = store.faces[anode.faces[face_index]]

    geometries = []
    for plane_id in face.planes:
        plane = store.planes[plane_id]
        wire_endpoints = []
        for wire_id in plane.wires:
            wire = store.wires[wire_id]
            tail = store.points[wire.tail]
            head = store.points[wire.head]
            wire_endpoints.append(((tail.x, tail.y, tail.z), (head.x, head.y, head.z)))
        wire_endpoints = _apply_wirecell_corrections(wire_endpoints)
        geometries.append(PlaneGeometry(wire_endpoints))
    return geometries


def face_sensitive_bounds(wire_store_path, anode_index, face_index):
    """Approximates the anode face's sensitive-volume (y, z) bounding box.

    WCT's own blob tiling clips every blob to the anode face's sensitive
    volume via two extra ray-grid layers built from an `IAnodeFace`'s
    `BoundingBox` (`get_raypairs()` in
    `wire-cell-toolkit/gen/src/AnodeFace.cxx`), in addition to the 3
    wire-plane layers. That `BoundingBox` is supplied to the C++ anode-face
    constructor from the detector's Jsonnet geometry config, not from the
    wire-store JSON this module loads, so it is not directly available here.

    This function approximates it as the axis-aligned box spanning every
    wire endpoint across all planes of the face. Wires are laid out to fill
    the sensitive area edge to edge, so this is normally a close
    approximation, not an exact reproduction of the authoritative
    `BoundingBox` used by C++.

    Args:
        wire_store_path (str), anode_index (int), face_index (int): Same as
            `build_plane_geometries`.

    Returns:
        shapely.geometry.Polygon: Axis-aligned (y, z) bounding box.
    """
    store = wire_persist.load(wire_store_path)
    anode = store.anodes[anode_index]
    face = store.faces[anode.faces[face_index]]

    ys, zs = [], []
    for plane_id in face.planes:
        plane = store.planes[plane_id]
        for wire_id in plane.wires:
            wire = store.wires[wire_id]
            for point_id in (wire.tail, wire.head):
                point = store.points[point_id]
                ys.append(point.y)
                zs.append(point.z)
    return box(min(ys), min(zs), max(ys), max(zs))
