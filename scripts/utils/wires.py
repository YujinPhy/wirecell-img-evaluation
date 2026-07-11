"""Wire-plane geometry: pitch-axis projection and per-plane strip polygons.

Summary: Loads WCT wire-store geometry (via `wirecell.util.wires.persist`/
`schema`) and exposes `PlaneGeometry`, which projects an arbitrary (y, z)
point onto a wire plane's pitch axis and builds a long "strip" polygon for
a pitch range. This is the wire-geometry building block that
`utils.true_blob` combines across three planes to form a true-blob
polygon. Also exposes `face_sensitive_bounds`, an approximate sensitive-
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

    The pitch axis is the direction of maximum variance across all wire
    midpoints (found via PCA), not simply the vector between the first and
    last wire: individual wires near a plane's trapezoidal edges are
    shorter than interior wires, so their midpoints are offset along the
    wire direction as well as the pitch direction, which would bias a
    two-point estimate. A strip covering a pitch range is built directly
    from this axis as a long band, not from any specific wire's own
    (possibly short) endpoints, so short edge wires cannot truncate it.
    """

    #: Half-length used to extend a strip polygon along the wire direction,
    #: far beyond any real detector's extent, so a strip behaves like an
    #: infinite band bounded only in the pitch direction.
    _STRIP_HALF_LENGTH = 1.0e5

    def __init__(self, wire_endpoints):
        tails = np.array([tail for tail, _head in wire_endpoints])[:, 1:3]
        heads = np.array([head for _tail, head in wire_endpoints])[:, 1:3]
        mids_yz = 0.5 * (tails + heads)

        self.origin = mids_yz.mean(axis=0)
        centered = mids_yz - self.origin
        _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
        self.pitch_axis = vt[0]
        self.wire_axis = np.array([-self.pitch_axis[1], self.pitch_axis[0]])

        self.pitch_vals = centered @ self.pitch_axis
        
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
