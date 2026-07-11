"""Educational walkthrough of wire geometry structure and PlaneGeometry mechanics.

Summary: Demonstrates, step by step with printed intermediate values, how
wire geometry is represented (the raw `wirecell.util.wires.schema`
hierarchy: Store -> Anode -> Face -> Plane -> Wire -> Point), how WCT packs
plane/face/apa into a single `WirePlaneId` integer, and how
`utils.wires.PlaneGeometry` turns that raw geometry into a pitch axis,
a pitch coordinate for an arbitrary (y, z) point, and a strip polygon for
a pitch range. The (y, z) point used to exercise `PlaneGeometry` here is a
synthetic example (each plane's own geometric center), not a real depo
position -- this script only validates the wire-geometry mechanics in
isolation. Validating whether these mechanics pick the geometrically
correct wires for a real depo is a separate concern; see
`scripts/depo_wire_validation.py` for that. See also
`docs/wirecell_wires_reference.md` and `docs/true_blob_prototype.md` for
the full written explanation this script complements.

Usage:
    source ../wire-cell-python/venv/bin/activate
    export PYTHONPATH="/home/yujin/projects/WireCell"
    python scripts/geometry_validation.py
"""

import sys
sys.path.insert(0, "scripts")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches
from wirecell.util.wires import persist as wire_persist
from wirecell.util.wires.schema import plane_face_apa, wire_plane_id

from utils.wires import build_plane_geometries
from utils.vis.plot_utils import save_and_show

WIRE_STORE = "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2"
ANODE_INDEX = 1
FACE_INDEX = 1
PLANE_NAMES = ["U", "V", "W"]
NSIGMA = 3.0
EXAMPLE_EXTENT_TRAN = 2.0  # mm, illustrative width -- not a real depo's extent_tran
OUTPUT_DIR = "results/pdhd/geometry_validation"


def section(title):
    """Prints a banner so each step's output is visually separated."""
    print(f"\n{'=' * 78}\n[INFO] {title}\n{'=' * 78}")


def walk_raw_schema():
    """Step 1: walk the raw Store hierarchy directly, with no true_blob helpers.

    This is the part `utils.wires.build_plane_geometries` does
    internally; walking it by hand here shows exactly what each schema
    type holds and how the tail/head indirection works.
    """
    section("1. Raw wire-store hierarchy (wirecell.util.wires.schema)")

    store = wire_persist.load(WIRE_STORE)
    print(f"[INFO] {store}")  # Store.__repr__ prints counts of every collection

    anode = store.anodes[ANODE_INDEX]
    print(f"[INFO] anode index={ANODE_INDEX} ident={anode.ident} nfaces={len(anode.faces)}")

    face_id = anode.faces[FACE_INDEX]
    face = store.faces[face_id]
    print(f"[INFO] face index={FACE_INDEX} ident={face.ident} nplanes={len(face.planes)}")
    print("[INFO] face.planes is already ordered U, V, W (see schema.py docstring)")

    for plane_index, plane_id in enumerate(face.planes):
        plane = store.planes[plane_id]
        name = PLANE_NAMES[plane_index]
        print(f"[INFO] plane {plane_index} ({name}): ident={plane.ident} nwires={len(plane.wires)}")

        # plane.wires is already sorted by increasing pitch (schema.py
        # docstring guarantee) -- look at the first wire to see the
        # tail/head indirection into store.points.
        first_wire = store.wires[plane.wires[0]]
        tail_point = store.points[first_wire.tail]
        head_point = store.points[first_wire.head]
        print(f"[INFO]   wire[0]: ident={first_wire.ident} channel={first_wire.channel} "
              f"segment={first_wire.segment} tail_idx={first_wire.tail} head_idx={first_wire.head}")
        print(f"[INFO]   wire[0] tail/head are indices; resolved points: "
              f"tail={tail_point} head={head_point}")

        last_wire = store.wires[plane.wires[-1]]
        last_tail = store.points[last_wire.tail]
        print(f"[INFO]   wire[-1] (ident={last_wire.ident}) tail point: {last_tail}")


def demo_wpid_bit_packing():
    """Step 2: show that WirePlaneId packs plane as a bitmask, not 0/1/2."""
    section("2. WirePlaneId bit-packing (wire_plane_id / plane_face_apa)")

    for plane_bit, name in zip([1, 2, 4], PLANE_NAMES):
        wpid = wire_plane_id(plane_bit, FACE_INDEX, ANODE_INDEX)
        decoded_plane_bit, decoded_face, decoded_apa = plane_face_apa(wpid)
        print(f"[INFO] plane {name} (bit={plane_bit}): "
              f"wire_plane_id(plane={plane_bit}, face={FACE_INDEX}, apa={ANODE_INDEX}) = {wpid} "
              f"-> plane_face_apa({wpid}) = (plane_bit={decoded_plane_bit}, face={decoded_face}, apa={decoded_apa})")
    print("[INFO] Note: the decoded plane component is a single-bit mask (1, 2, 4),")
    print("[INFO] not a sequential index -- see docs/wirecell_wires_reference.md section 2.4")


def demo_plane_geometry():
    """Step 3: build PlaneGeometry objects and exercise each of their methods.

    Uses a synthetic example point (the W-plane's own geometric origin)
    purely to illustrate the mechanics of pitch_of/wire_index_range/
    strip_polygon -- this is not a real depo position.
    """
    section("3. PlaneGeometry construction and methods")

    plane_geoms = build_plane_geometries(WIRE_STORE, anode_index=ANODE_INDEX, face_index=FACE_INDEX)

    for i, pg in enumerate(plane_geoms):
        print(f"[INFO] plane {i} ({PLANE_NAMES[i]}): nwires={pg.nwires} origin={pg.origin} "
              f"pitch_axis={pg.pitch_axis} wire_axis={pg.wire_axis}")
        print(f"[INFO]   pitch_vals range: [{pg.pitch_vals.min():.1f}, {pg.pitch_vals.max():.1f}] mm")

    example_y, example_z = plane_geoms[2].origin
    print(f"\n[INFO] Example point (plane 2's own geometric origin, illustrative only): "
          f"y={example_y:.2f}mm z={example_z:.2f}mm extent_tran={EXAMPLE_EXTENT_TRAN:.1f}mm")

    strips = []
    for i, pg in enumerate(plane_geoms):
        center = pg.pitch_of(example_y, example_z)
        pitch_min = center - NSIGMA * EXAMPLE_EXTENT_TRAN
        pitch_max = center + NSIGMA * EXAMPLE_EXTENT_TRAN
        imin, imax = pg.wire_index_range(pitch_min, pitch_max)
        strip = pg.strip_polygon(pitch_min, pitch_max)
        strips.append(strip)
        print(f"[INFO] plane {i} ({PLANE_NAMES[i]}): pitch_of(y,z)={center:.3f}mm "
              f"wire_index_range=({imin},{imax}) strip_area={strip.area:.1f}mm^2")

    intersection = strips[0].intersection(strips[1]).intersection(strips[2])
    centroid = tuple(round(c, 2) for c in intersection.centroid.coords[0])
    print(f"[INFO] intersection of all 3 strips: area={intersection.area:.2f}mm^2 centroid(y,z)={centroid}")
    print(f"[INFO] (example point was y={example_y:.2f} z={example_z:.2f} -- centroid should match closely)")

    return strips, intersection, example_y, example_z


def plot_strips(strips, intersection, example_y, example_z):
    """Step 4: visualize the 3 plane strips and their intersection."""
    section("4. Plotting the 3 plane strips and their intersection")

    fig, ax = plt.subplots(figsize=(6, 6))
    colors = ["#E63946", "#457B9D", "#2A9D8F"]

    for i, (strip, color) in enumerate(zip(strips, colors)):
        yz = np.array(strip.exterior.coords)[:, [1, 0]]
        ax.add_patch(patches.Polygon(
            yz, closed=True, fill=False, edgecolor=color, linewidth=1.5,
            label=f"Plane {i} ({PLANE_NAMES[i]}) strip",
        ))

    inter_yz = np.array(intersection.exterior.coords)[:, [1, 0]]
    ax.add_patch(patches.Polygon(
        inter_yz, closed=True, fill=True, facecolor="black", alpha=0.6,
        edgecolor="black", label="3-plane strip intersection",
    ))
    ax.plot(example_z, example_y, "o", color="yellow", markeredgecolor="black",
            markersize=8, label="example point", zorder=5)

    margin = 10.0
    z_min, z_max = inter_yz[:, 0].min() - margin, inter_yz[:, 0].max() + margin
    y_min, y_max = inter_yz[:, 1].min() - margin, inter_yz[:, 1].max() + margin
    ax.set_xlim(z_min, z_max)
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Z [mm]")
    ax.set_ylabel("Y [mm]")
    ax.set_title("PlaneGeometry.strip_polygon() intersection (synthetic example)")
    ax.legend(loc="upper right", fontsize=7)
    ax.set_aspect("equal")

    save_and_show(fig, OUTPUT_DIR, "strip_intersection_demo", show=False)


def main():
    walk_raw_schema()
    demo_wpid_bit_packing()
    strips, intersection, example_y, example_z = demo_plane_geometry()
    plot_strips(strips, intersection, example_y, example_z)


if __name__ == "__main__":
    main()
