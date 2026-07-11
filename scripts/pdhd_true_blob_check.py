"""Sanity-check driver for the depo-based "true blob" prototype.

Summary: Loads the drifted depos and reconstructed cluster graph for the
`test_single_trk` sample, builds one true blob per depo via
`utils.true_blob`, compares each to its time-overlapping reco blob, prints
IoU/centroid-distance/time-overlap/charge-error statistics, and saves an
overlay plot for visual inspection. This is the Phase 1 validation step of
the depo-based true-blob design plan.

Usage:
    source ../wire-cell-python/venv/bin/activate
    export PYTHONPATH="/home/yujin/projects/WireCell"
    python pdhd_true_blob_check.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import numpy as np
from wirecell import units

from utils.load import load_cluster_data, load_generation_data, load_graph_nodes
from utils.wires import build_plane_geometries, face_sensitive_bounds
from utils.true_blob import build_true_blobs
from utils.eval.position_shape import compare_true_to_reco
from utils.vis.true_blob_plots import plot_true_vs_reco_check, nearest_reco_blob

DATA_DIR = "data/pdhd/test_point_depo"
WIRE_STORE = "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2"
ANODE_INDEX = 1
FACE_INDEX = 1
DRIFT_SPEED = 1.6 * units.mm / units.us
NSIGMA = 3.0
OUTPUT_DIR = "results/pdhd/true_blob_check"

# Calibrated depo-time -> blob-time offset (analytic baseline + measured
# residual); see docs/time_offset_calibration.md and
# scripts/pdhd_time_offset_check.py for the derivation.
TIME_OFFSET = 313.9 * units.us


def main():
    # Data loading
    depos = load_generation_data(os.path.join(DATA_DIR, "depos-drifted-1.zip"), 0)
    cgraph = load_cluster_data(os.path.join(DATA_DIR, "clusters-apa-1.tar.gz"))
    reco_blobs = load_graph_nodes(cgraph, "b")

    plane_geoms = build_plane_geometries(WIRE_STORE, anode_index=ANODE_INDEX, face_index=FACE_INDEX)
    sensitive_bounds = face_sensitive_bounds(WIRE_STORE, anode_index=ANODE_INDEX, face_index=FACE_INDEX)

    # Generate True blob, shifting depo time by the calibrated offset so
    # true-blob time slices land in the same absolute clock as reco blobs.
    depos["t"] = depos["t"] + TIME_OFFSET
    true_blobs = build_true_blobs(
        plane_geoms, depos, speed=DRIFT_SPEED, nsigma=NSIGMA, sensitive_bounds=sensitive_bounds,
    )

    print(f"[INFO] ndepos={len(true_blobs)} nreco_blobs={len(reco_blobs)}")
    none_count = sum(1 for b in true_blobs if b["polygon"] is None)
    print(f"[INFO] true blobs with empty polygon: {none_count}/{len(true_blobs)}")

    ious, centroid_dists, time_overlaps, charge_errs = [], [], [], []
    for tb in true_blobs:
        rb = nearest_reco_blob(tb, reco_blobs)
        if rb is None:
            continue
        cmp = compare_true_to_reco(tb, rb)
        ious.append(cmp["iou"])
        centroid_dists.append(cmp["centroid_distance"])
        time_overlaps.append(cmp["time_overlap_frac"])
        charge_errs.append(cmp["charge_rel_error"])

    print(f"[INFO] IoU: mean={np.nanmean(ious):.3f} median={np.nanmedian(ious):.3f}")
    print(f"[INFO] Centroid distance [mm]: mean={np.nanmean(centroid_dists):.2f}")
    print(f"[INFO] Depo time shifted by calibrated TIME_OFFSET={TIME_OFFSET / units.us:.3f}us"
          f" before building true blobs (see docs/time_offset_calibration.md).")
    print(f"[INFO] Time-slice overlap frac: mean={np.nanmean(time_overlaps):.3f}")
    print(f"[INFO] Charge relative error: mean={np.nanmean(charge_errs):.3f}")

    sample_indices = [0, len(true_blobs) // 4, len(true_blobs) // 2, len(true_blobs) - 1]
    plot_true_vs_reco_check(
        true_blobs, reco_blobs, sample_indices,
        output_dir=OUTPUT_DIR, filename="single_point_depo_overlay",
        depos=depos,
    )


if __name__ == "__main__":
    main()
