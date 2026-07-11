"""Calibration check for BlobDepoFill's `time_offset` parameter (PDHD).

Summary: Computes the analytically-derivable part of the depo-time-to-
blob-time offset from PDHD's own simulation params (tick0 convention,
response-plane transit time), then runs a narrow empirical scan around
that baseline against the `test_point_depo` sample to measure the small
residual left over from signal-processing effects the analytic formula
does not capture. Prints a summary and plots the offset-vs-overlap curve.
See `docs/time_offset_calibration.md` for the full derivation and the
review of the prior `scripts/timeoffset/` study this replaces.

Usage:
    source ../wire-cell-python/venv/bin/activate
    export PYTHONPATH="/home/yujin/projects/WireCell"
    python pdhd_time_offset_check.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import matplotlib.pyplot as plt
from wirecell import units

from utils.load import load_cluster_data, load_generation_data, load_graph_nodes
from utils.time_offset import analytic_time_offset, scan_residual
from utils.vis.plot_utils import save_and_show

DATA_DIR = "data/pdhd/test_point_depo"
IMG_JSONNET = "wire-cell-cfg/pdhd/img.jsonnet"
OUTPUT_DIR = "results/pdhd/time_offset_check"

DRIFT_SPEED = 1.6 * units.mm / units.us

# PDHD sim params, mirrored from wire-cell-toolkit's
# cfg/pgrapher/experiment/pdhd/params.jsonnet (`sim.tick0_time`,
# `det.response_plane`) and cfg/pgrapher/common/params.jsonnet
# (`lar.drift_speed`). Not auto-read from jsonnet since that requires a
# jsonnet evaluator; keep these in sync if those files change.
TICK0_TIME = -250.0 * units.us
RESPONSE_PLANE = 100.0 * units.mm


def current_configured_offset(jsonnet_path):
    """Extracts the currently-configured `time_offset` value from `img.jsonnet`.

    Returns:
        float or None: The value in this codebase's system-of-units
            convention (i.e. already multiplied by `units.us`), or None if
            not found.
    """
    with open(jsonnet_path) as f:
        text = f.read()
    match = re.search(r"time_offset:\s*([0-9.eE+-]+)\s*\*\s*wc\.us", text)
    return float(match.group(1)) * units.us if match else None


def main():
    baseline = analytic_time_offset(TICK0_TIME, RESPONSE_PLANE, DRIFT_SPEED)
    print(f"[INFO] Analytic baseline offset: {baseline / units.us:.3f} us"
          f" (|tick0_time|={abs(TICK0_TIME) / units.us:.3f}us + response_plane/drift_speed="
          f"{RESPONSE_PLANE / DRIFT_SPEED / units.us:.3f}us)")

    depos = load_generation_data(os.path.join(DATA_DIR, "depos-drifted-1.zip"), 0)
    cgraph = load_cluster_data(os.path.join(DATA_DIR, "clusters-apa-1.tar.gz"))
    reco_blobs = load_graph_nodes(cgraph, "b")

    depo_t = depos["t"][0]
    depo_tsigma = depos["L"][0] / DRIFT_SPEED
    print(f"[INFO] depo_t={depo_t / units.us:.3f}us depo_tsigma={depo_tsigma / units.us:.3f}us"
          f" nreco_blobs={len(reco_blobs)}")

    best_offset, curve = scan_residual(depo_t, depo_tsigma, reco_blobs, baseline)
    residual = best_offset - baseline
    print(f"[INFO] Best offset from narrow scan: {best_offset / units.us:.3f} us"
          f" (residual={residual / units.us:+.3f}us on top of analytic baseline)")

    configured = current_configured_offset(IMG_JSONNET)
    if configured is not None:
        print(f"[INFO] Currently configured time_offset in {IMG_JSONNET}: {configured / units.us:.3f} us"
              f" (diff from scan result: {(configured - best_offset) / units.us:+.3f}us)")
    else:
        print(f"[WARN] Could not find time_offset in {IMG_JSONNET}")

    offsets, scores = zip(*curve)
    offsets_us = [o / units.us for o in offsets]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(offsets_us, scores, color="tab:blue")
    ax.axvline(baseline / units.us, color="tab:green", linestyle="--",
               label=f"analytic baseline ({baseline / units.us:.2f}us)")
    ax.axvline(best_offset / units.us, color="tab:red", linestyle="--",
               label=f"best offset ({best_offset / units.us:.2f}us)")
    if configured is not None:
        ax.axvline(configured / units.us, color="tab:orange", linestyle=":",
                   label=f"currently configured ({configured / units.us:.2f}us)")
    ax.set_xlabel("candidate time_offset [us]")
    ax.set_ylabel("overlap coefficient")
    ax.legend()
    ax.set_title("BlobDepoFill time_offset residual scan (test_point_depo)")
    save_and_show(fig, OUTPUT_DIR, "point_depo_offset_scan", show=False)


if __name__ == "__main__":
    main()
