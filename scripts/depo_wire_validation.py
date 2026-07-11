"""Validates that PlaneGeometry selects the geometrically correct wires for a real depo.

Summary: Where `scripts/geometry_validation.py` exercises
`utils.wires.PlaneGeometry` mechanics with a synthetic example point,
this script checks the actual question that matters for the true-blob
design: for a real depo's (y, z) position, does `pitch_of` /
`wire_index_range` / `strip_polygon` on each of the three wire planes
select a pitch range whose 3-plane strip intersection actually contains
(or sits right on top of) that depo? For a handful of sample depos from
the `test_single_trk` sample, this prints each plane's selected pitch
range and wire-index range, checks whether the resulting polygon contains
the depo point (or how far its centroid is from it if not), and plots one
example overlay for visual confirmation. This does not compare against
reconstructed blobs -- see `scripts/pdhd_true_blob_check.py` for that.

Usage:
    source ../wire-cell-python/venv/bin/activate
    export PYTHONPATH="/home/yujin/projects/WireCell"
    python scripts/depo_wire_validation.py
"""

import sys
sys.path.insert(0, "scripts")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches
from shapely.geometry import Point

from utils.load import load_generation_data
from utils.wires import build_plane_geometries
from utils.true_blob import true_blob_polygon
from utils.vis.plot_utils import save_and_show

DEPO_FILE = "data/pdhd/test_point_depo/depos-drifted-1.zip"
WIRE_STORE = "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2"
ANODE_INDEX = 1
FACE_INDEX = 1
PLANE_NAMES = ["U", "V", "W"]
NSIGMA = 3.0
OUTPUT_DIR = "results/pdhd/depo_wire_validation"


def section(title):
    """Prints a banner so each step's output is visually separated."""
    print(f"\n{'=' * 78}\n[INFO] {title}\n{'=' * 78}")


def check_one_depo(plane_geoms, depos, index):
    """Runs pitch_of/wire_index_range/strip_polygon for one real depo.

    Returns:
        dict: {"polygon", "contains", "centroid_distance"} for this depo.
    """
    y, z = depos["y"][index], depos["z"][index]
    extent_tran = depos["T"][index]

    print(f"[INFO] depo #{index}: y={y:.2f}mm z={z:.2f}mm extent_tran={extent_tran:.3f}mm")
    for i, pg in enumerate(plane_geoms):
        center = pg.pitch_of(y, z)
        pitch_min, pitch_max = center - NSIGMA * extent_tran, center + NSIGMA * extent_tran
        imin, imax = pg.wire_index_range(pitch_min, pitch_max)
        print(f"[INFO]   plane {i} ({PLANE_NAMES[i]}): selected pitch=[{pitch_min:.2f}, {pitch_max:.2f}]mm "
              f"-> wire_index_range=({imin},{imax})")

    polygon = true_blob_polygon(plane_geoms, y, z, extent_tran, nsigma=NSIGMA)
    depo_point = Point(y, z)

    if polygon is None:
        print(f"[WARN] depo #{index}: 3-plane strip intersection is empty -- wire selection failed")
        return {"polygon": None, "contains": False, "centroid_distance": float("nan")}

    contains = polygon.contains(depo_point)
    centroid_distance = polygon.centroid.distance(depo_point)
    status = "PASS" if contains else "CHECK"
    print(f"[INFO] [{status}] depo #{index}: polygon.contains(depo point)={contains} "
          f"centroid_distance={centroid_distance:.4f}mm")
    return {"polygon": polygon, "contains": contains, "centroid_distance": centroid_distance}


def plot_example(depos, index, result):
    """Plots the selected 3-plane intersection polygon against the depo point."""
    section(f"Plotting depo #{index}'s selected wire region")

    polygon = result["polygon"]
    if polygon is None:
        print(f"[WARN] Skipping plot for depo #{index}: no polygon to draw")
        return

    y, z = depos["y"][index], depos["z"][index]

    fig, ax = plt.subplots(figsize=(6, 6))
    poly_yz = np.array(polygon.exterior.coords)[:, [1, 0]]
    ax.add_patch(patches.Polygon(
        poly_yz, closed=True, fill=True, facecolor="#FF00FF", alpha=0.4,
        edgecolor="#FF00FF", linewidth=1.5, label="Selected wire region (true blob polygon)",
    ))
    ax.plot(z, y, "o", color="yellow", markeredgecolor="black",
            markersize=8, label=f"depo #{index} position", zorder=5)

    margin = 5.0
    z_min, z_max = poly_yz[:, 0].min() - margin, poly_yz[:, 0].max() + margin
    y_min, y_max = poly_yz[:, 1].min() - margin, poly_yz[:, 1].max() + margin
    ax.set_xlim(z_min, z_max)
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Z [mm]")
    ax.set_ylabel("Y [mm]")
    ax.set_title(f"Wire selection for depo #{index}: contains={result['contains']}")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_aspect("equal")

    save_and_show(fig, OUTPUT_DIR, f"depo_wire_selection_depo{index}", show=False)


def main():
    section("Loading depos and building plane geometries")
    depos = load_generation_data(DEPO_FILE, 0)
    plane_geoms = build_plane_geometries(WIRE_STORE, anode_index=ANODE_INDEX, face_index=FACE_INDEX)
    print(f"[INFO] ndepos={len(depos['t'])}")

    section("Checking wire selection for a sample of depos")
    sample_indices = [0, len(depos["t"]) // 4, len(depos["t"]) // 2, len(depos["t"]) - 1]
    results = [check_one_depo(plane_geoms, depos, i) for i in sample_indices]

    ncontained = sum(1 for r in results if r["contains"])
    print(f"\n[INFO] Summary: {ncontained}/{len(results)} sample depos are contained in their own "
          "selected wire region polygon")

    plot_example(depos, sample_indices[0], results[0])


if __name__ == "__main__":
    main()
