"""Compares point-depo centers to reconstructed blob centers.

Recovers each depo's true (x, y, z) center from its post-drift (Gen0) time
and compares it against every matched reco blob (`blob_center - depo_center`,
per axis). Aggregates the differences into histograms, reports each axis's
median and empirical percentile band (configurable via --percentile), and
saves per-axis outlier cases (data + a representative sample of overlay
plots) for visual inspection. See docs/position_eval_center_comparison_Plan.md
for the design and the empirically-verified depo/blob time-to-x conversion
formulas.

Supports two ways of recovering the depo/blob correspondence, via --mode:
  - `per_file` (default): one depo per file, scanned across position
    subdirectories (e.g. one run of wct-sim-nf-sp-img-bdf.jsonnet per
    position). Every blob found in a position's file belongs to that
    position's single depo -- no matching needed.
  - `one`: multiple point-depo positions packed into a single depo/reco file
    pair (e.g. one run of wct-sim-nf-sp-img-bdf-grid.jsonnet). Each depo's
    index carries a distinct expected reco-clock time (its post-drift Gen0
    `t`, shifted by `t_offset`), and each blob is assigned to whichever
    depo's expected time is nearest to the blob's own slice-window center
    (see match_blobs_to_depos). This nearest-center heuristic assumes
    neighboring positions' depo time distributions don't overlap heavily; it
    is not a full Gaussian-overlap assignment.

Usage:
    source ../wire-cell-python/venv/bin/activate
    export PYTHONPATH="/home/yujin/projects/WireCell"
    python scripts/position_center_comparison.py --mode per_file
    python scripts/position_center_comparison.py --mode one \\
        --depo-file <path/to/depos-drifted-1.zip> \\
        --reco-file <path/to/clusters-apa-1.tar.gz>
"""

import csv
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

from utils.load import load_generation_data, load_cluster_data, load_graph_nodes
from utils.slicer import truncated_gaussian_mean, gbounds
from utils.vis.plot_utils import save_and_show
from utils.vis.transverse_plots import plot_depo_gaussian_tran_ax

# ==== Default parameters for the PDHD point-depo scan dataset and analysis ====
DATA_BASE_DIR = "/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_small"
OUTPUT_DIR = "results/pdhd/position_center_comparison_offset_314p5"
TAG = "314p5"
ANODE_INDEX = 1
RESPONSE_PLANE_X = 3430.47   # [mm]

V_DRIFT = 1.6            # [mm/us]
T_OFFSET = 314.5         # [us]
# T_OFFSET = 313.898        # [us]

# ==== Analysis parameters ====
# PERCENTILE = 95.0
PERCENTILE = 68.27
OUTLIER_PERCENTILE = 90.0  # percentile threshold for outlier classification

VAL_THR = 0.0  # minimum blob charge to consider for outlier classification
N_OUTLIER_PLOTS = 50


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare point-depo centers to reco blob centers across a position scan.")

    # ==== Mode ====
    parser.add_argument("--mode", choices=["per_file", "one"], default="per_file",
                        help="depo/blob correspondence source: 'per_file' scans position "
                             "subdirectories with one depo per file (default); 'one' reads a "
                             "single --depo-file/--reco-file pair holding multiple depos, "
                             "matched to blobs by nearest reco-clock time")

    # ==== I/O parameters (--mode per_file) ====
    parser.add_argument("--data-base-dir", default=DATA_BASE_DIR,
                        help="base directory containing position subdirectories (default: %s)" % DATA_BASE_DIR)
    parser.add_argument("--cluster-prefix", default="clusters-apa-",
                        help="prefix for cluster blob files (default: clusters-apa-)")
    parser.add_argument("--cluster-surfix", default=".tar.gz",
                        help="surfix for cluster blob files (default: .tar.gz)")
    parser.add_argument("--depo-prefix", default="depos-drifted-",
                        help="prefix for depo files (default: depos-drifted-)")
    parser.add_argument("--depo-surfix", default=".zip",
                        help="surfix for depo files (default: .zip)")

    # ==== I/O parameters (--mode one) ====
    parser.add_argument("--depo-file", default=None,
                        help="path to a depos-drifted-<N>.zip file holding multiple depos "
                             "(required for --mode one)")
    parser.add_argument("--reco-file", default=None,
                        help="path to the matching clusters-apa-<N>.tar.gz reco file "
                             "(required for --mode one)")

    # ==== Output ====
    parser.add_argument("--output-dir", default=OUTPUT_DIR,
                        help="directory to save results (default: %s)" % OUTPUT_DIR)
    parser.add_argument("--tag" , default=TAG,
                        help="tag to append to output files (default: position_center)")

    # ==== PDHD parameters ====
    parser.add_argument("--anode-index", type=int, default=ANODE_INDEX,
                        help="anode index to use for depo/reco file names (default: %d)" % ANODE_INDEX)
    parser.add_argument("--v-drift", type=float, default=V_DRIFT,
                        help="drift velocity [mm/us] (default: %.2f)" % V_DRIFT)
    parser.add_argument("--t-offset", type=float, default=T_OFFSET,
                        help="depo-to-reco time offset [us] (default: %.2f)" % T_OFFSET)
    parser.add_argument("--anode1-x-pos", type=float, default=RESPONSE_PLANE_X,
                        help="x position of anode 1 [mm] (default: %.2f)" % RESPONSE_PLANE_X)


    # ==== Analysis Parameters ====
    parser.add_argument("--mean-method", choices=["truncated_mean", "slice_midpoint"], default="truncated_mean",
                        help="method to compute depo center within a slice (default: truncated_mean)")
    parser.add_argument("--percentile", type=float, default=PERCENTILE,
                        help="percentile (0-100) of |diff-median| used as the per-axis "
                             "outlier threshold, computed empirically per axis instead of "
                             "assuming a mean+std Gaussian band (default: %.1f)" % PERCENTILE)
    parser.add_argument("--outlier-percentile", type=float, default=OUTLIER_PERCENTILE,
                        help="percentile (0-100) of |diff-median| used to classify outliers, computed empirically per axis instead of assuming a mean+std Gaussian band (default: %.1f)" % OUTLIER_PERCENTILE)
    parser.add_argument("--val-thr", type=float, default=VAL_THR,
                        help="also flag records whose blob charge (val) is below this "
                             "threshold as outliers, regardless of the percentile check "
                             "(default: %.1f)" % VAL_THR)
    parser.add_argument("--n-outlier-plots", type=int, default=N_OUTLIER_PLOTS,
                        help="number of outlier cases to plot (default: %d)" % N_OUTLIER_PLOTS)

    args = parser.parse_args()
    if args.mode == "one" and (args.depo_file is None or args.reco_file is None):
        parser.error("--mode one requires both --depo-file and --reco-file")
    return args


# ==== Scanning ====
def scan_positions(base_dir, anode_index,
                   depo_prefix="depos-drifted-", depo_surfix=".zip",    
                   reco_blob_prefix="clusters-apa-", reco_blob_surfix=".tar.gz"):
    """Lists position subdirectories that have depo + reco files.

    Directory names encode the intended scan position, but are only used
    here to enumerate/iterate; actual ground-truth coordinates always come
    from the loaded depo/blob data.
    """
    positions = []
    for name in sorted(os.listdir(base_dir)):
        pos_dir = os.path.join(base_dir, name)
        if not os.path.isdir(pos_dir):
            continue
        depo_file = os.path.join(pos_dir, f"{depo_prefix}{anode_index}{depo_surfix}")
        reco_file = os.path.join(pos_dir, f"{reco_blob_prefix}{anode_index}{reco_blob_surfix}")
        if not (os.path.exists(depo_file) and os.path.exists(reco_file)):
            print(f"[WARNING] {name}: missing depo/reco file, skipping")
            continue
        positions.append((name, depo_file, reco_file))
    return positions


# ==== Utils ====
def get_slice_info(reco_graph):
    """Lists every slice present in a reco blob cluster file, with its time window.

    Args:
        reco_file (str): Path to a `clusters-apa-<N>.tar.gz` reco blob file.

    Returns:
        list[dict]: One entry per slice node (`code='s'`), each with
            `slice_id`, `start`, `end` (`start + span`), and `span` (all in
            ns, matching the underlying `ISlice` fields).
    """
    cgraph = reco_graph
    if cgraph is None:
        print(f"[WARNING] No cluster graph, skipping")
        return []

    slices = load_graph_nodes(cgraph, "s")
    return [
        {
            "slice_id": s["ident"],
            "start": s["start"],
            "end": s["start"] + s["span"],
            "span": s["span"],
        }
        for s in slices
    ]


def convert_time2x(t_us, v_drift, response_plane_x):
    """Converts a time (us) to a physical x position (mm) using the drift velocity and anode position.

    Args:
        t_us (float): Time in microseconds.
        v_drift (float): Drift velocity in mm/us.
        response_plane_x (float): x position of the response plane in mm.

    Returns:
        float: Physical x position in mm.
    """
    return response_plane_x - v_drift * t_us


# ==== Blob Center Computation ====
def blob_center(blob_node, v_drift, response_plane_x):
    """Computes a reco blob's (x, y, z) center [mm].

    `corners` entries are `[t_ns, y_mm, z_mm]` (not `[x_mm, y_mm, z_mm]`);
    the time component is identical across all corners and equals the
    blob's slice `start`. The blob's `start`/`span` are already on the reco
    clock, so x is derived directly from the slice midpoint
    (`start + span/2`) with no `t_offset` shift -- it's `depo_center`/
    `depo_slice_center` that add `t_offset` to bring the depo's own clock
    onto this same reco clock (see `depo_center`).
    """
    t_us = (blob_node["start"] + blob_node["span"] / 2.0) / 1000.0
    x = convert_time2x(t_us, v_drift, response_plane_x)
    corners = np.array(blob_node["corners"])
    y = corners[:, 1].mean()
    z = corners[:, 2].mean()
    return np.array([t_us, x, y, z])


# ==== Depo Center Computation ====
def depo_center(depos, depo_idx=0, v_drift=V_DRIFT, t_offset=T_OFFSET, response_plane_x=RESPONSE_PLANE_X):
    """Recovers the pre-drift depo (x, y, z) center [mm] from post-drift (Gen0) depo data.

    Althought Gen0's `t` already encodes the pure drift time (no frame offset
    applied) and blobs have some `start` time on the reco clock,
    the time offset is aplied to the depo's `t` here to use same logic of `BlobDepoFill`. 
    
    So `x = anode1_x_pos - v_drift * (t_us + time offset)`
    This aligns the depo's x with the reco clock, not the original Gen0 clock
    """
    t_us = depos["t"][depo_idx] / 1000.0 + t_offset  # [us]
    x = convert_time2x(t_us, v_drift, response_plane_x)
    y = depos["y"][depo_idx]
    z = depos["z"][depo_idx]
    return np.array([t_us, x, y, z])


def depo_slice_center(depos, method, slice_start, slice_end, v_drift, t_offset, response_plane_x, depo_idx=0):
    """Depo (x, y, z) center restricted to one reco slice's time window.

    A single depo's diffusion Gaussian in time typically spans several reco
    slices, each producing its own reco blob; comparing every one of those
    blobs against the depo's global (untruncated) mean is not apples-to-
    apples, since a blob only captures the fraction of the depo's charge
    that falls inside its own slice.

    `method="truncated_mean"` (recommended) uses the truncated-normal mean
    of the depo's time-Gaussian within [slice_start, slice_end]
    (`truncated_gaussian_mean`), left on the reco clock (both
    slice_start/slice_end and the truncated mean already live there) and
    converted to x with the same offset-free formula as `blob_center` --
    this keeps depo_x and blob_x on the same clock so `dx = blob_x - depo_x`
    isn't biased by `t_offset`. Any other `method` value falls back to the
    plain slice midpoint `(slice_start+slice_end)/2` --
    a cruder approximation that only matches the truncated mean near the
    depo's Gaussian peak; it systematically diverges (biased toward the
    slice's far edge) for slices in the tails, which is exactly where this
    analysis's outliers tend to show up, so use it only for side-by-side
    comparison against truncated_mean, not as the default.

    y/z are unaffected by time-slicing and match depo_center.
    """
    if method == "truncated_mean":
        mean_ns = depos["t"][depo_idx] + t_offset * 1000.0
        sigma_ns = (depos["L"][depo_idx] / v_drift) * 1000.0

        mean_us = truncated_gaussian_mean(slice_start, slice_end, mean_ns, sigma_ns) / 1000.0

        x = convert_time2x(mean_us , v_drift, response_plane_x)
    else:
        mean_us = (slice_start + slice_end) / 2.0 / 1000.0
        x = convert_time2x(mean_us, v_drift, response_plane_x)

    y = depos["y"][depo_idx]
    z = depos["z"][depo_idx]
    return np.array([mean_us, x, y, z])


# ==== Depo/blob matching (--mode one) ====
def depo_reco_time_ns(depos, t_offset):
    """Each depo's expected (untruncated) center time on the reco/blob clock (ns): the
    physical-drift-clock `depos['t']` shifted by `t_offset` (us), the same convention
    depo_center/depo_slice_center use. One value per depo, indexed like `depos['t']`.
    """
    return np.asarray(depos["t"], dtype=float) + t_offset * 1000.0


def match_blobs_to_depos(depos, blobs, t_offset):
    """Assigns each blob to the depo whose expected reco-clock time (depo_reco_time_ns) is
    nearest to the blob's own slice-window center (start + span/2). This is what recovers
    the depo/blob correspondence that --mode per_file gets for free (one depo per file).

    Returns dict depo_index -> list of blob node dicts assigned to it (only depos with
    >=1 matched blob are present as keys).
    """
    depo_times_ns = depo_reco_time_ns(depos, t_offset)
    depo_blobs = {}
    for b in blobs:
        center_ns = b["start"] + b["span"] / 2.0
        i = int(np.argmin(np.abs(depo_times_ns - center_ns)))
        depo_blobs.setdefault(i, []).append(b)
    return depo_blobs


# ==== Position/depo group collection ====
def collect_groups_per_file(base_dir, anode_index, depo_prefix, depo_surfix, cluster_prefix, cluster_surfix):
    """--mode per_file: one group per position subdirectory, each holding a single depo
    (depo_idx=0) and every reco blob found in that subdirectory's file pair.

    Returns:
        list[tuple[str, dict, list[dict], int]]: (label, depos, blobs, depo_idx) groups.
    """
    positions = scan_positions(base_dir, anode_index, depo_prefix, depo_surfix, cluster_prefix, cluster_surfix)
    print(f"[INFO] Found {len(positions)} position directories")

    groups = []
    for name, depo_file, reco_file in positions:
        depos = load_generation_data(depo_file, 0)
        if depos is None or len(depos["t"]) == 0:
            print(f"[WARNING] {name}: no Gen0 depo data, skipping")
            continue

        cgraph = load_cluster_data(reco_file)
        if cgraph is None:
            print(f"[WARNING] {name}: no cluster graph, skipping")
            continue

        blobs = load_graph_nodes(cgraph, "b")
        if not blobs:
            print(f"[WARNING] {name}: no reco blobs, skipping")
            continue

        groups.append((name, depos, blobs, 0))
    return groups


def collect_groups_one(depo_file, reco_file, t_offset, v_drift, response_plane_x):
    """--mode one: a single depo/reco file pair holding multiple point-depo positions.
    Recovers the depo/blob correspondence via match_blobs_to_depos, then yields one
    group per depo that matched at least one blob.

    Returns:
        list[tuple[str, dict, list[dict], int]]: (label, depos, blobs, depo_idx) groups.
    """
    depos = load_generation_data(depo_file, 0)
    if depos is None or len(depos["t"]) == 0:
        print(f"[ERROR] {depo_file}: no Gen0 depo data")
        return []

    cgraph = load_cluster_data(reco_file)
    if cgraph is None:
        print(f"[ERROR] {reco_file}: no cluster graph")
        return []

    blobs = load_graph_nodes(cgraph, "b")
    if not blobs:
        print(f"[ERROR] {reco_file}: no reco blobs")
        return []

    n_depos = len(depos["t"])
    print(f"[INFO] {n_depos} depos, {len(blobs)} reco blobs in {os.path.basename(reco_file)}")

    depo_blobs = match_blobs_to_depos(depos, blobs, t_offset)
    unmatched = sorted(set(range(n_depos)) - set(depo_blobs))
    if unmatched:
        print(f"[WARNING] {len(unmatched)}/{n_depos} depos got no matched blob (clipped by "
              f"the readout window, or absorbed into a neighboring depo's group): "
              f"{unmatched[:20]}{' ...' if len(unmatched) > 20 else ''}")

    groups = []
    for depo_idx, depo_blob_list in depo_blobs.items():
        x_nominal = depo_center(depos, depo_idx, v_drift, t_offset, response_plane_x)[1]
        label = f"depo{depo_idx:03d}_x{x_nominal:.0f}mm"
        groups.append((label, depos, depo_blob_list, depo_idx))
    return groups


# ==== Data collection ====
def collect_records(groups, v_drift, t_offset, response_plane_x, mean_method):
    """Builds one record per (group, blob), plus a per-group data cache for later plots.

    Every reco blob in a group is compared individually against the depo center
    restricted to that blob's own slice window (see depo_slice_center), not a
    single group-wide depo center -- see docs/position_eval_center_comparison_Plan.md
    2026-07-13 update for why per-blob comparison is needed, and the per-slice fix
    in this plan.

    Args:
        groups: list of (label, depos, blobs, depo_idx), as produced by
            collect_groups_per_file or collect_groups_one.

    Returns:
        tuple[list[dict], dict[str, tuple]]: (records, data_cache) where
            data_cache[label] = (depos, blobs, depo_idx) for outlier re-plotting.
    """
    records = []
    data_cache = {}

    for label, depos, blobs, depo_idx in groups:
        for i, b in enumerate(blobs):
            bc = blob_center(b, v_drift, response_plane_x)
            dc = depo_slice_center(depos, mean_method, b["start"], b["start"] + b["span"], v_drift, t_offset, response_plane_x, depo_idx)
            diff = bc - dc
            records.append({
                "position": label, "blob_index": i, "val": b["val"],
                "depo_t": dc[0], "depo_x": dc[1], "depo_y": dc[2], "depo_z": dc[3],
                "blob_t": bc[0], "blob_x": bc[1], "blob_y": bc[2], "blob_z": bc[3],
                "dt": diff[0], "dx": diff[1], "dy": diff[2], "dz": diff[3],
            })
        data_cache[label] = (depos, blobs, depo_idx)

    print(f"[INFO] Collected {len(records)} (position, blob) records from {len(data_cache)} usable groups")
    return records, data_cache


# ==== Output ====
def save_csv(records, path):
    if not records:
        print(f"[WARNING] No records to save to {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    print(f"[INFO] Saved {len(records)} records to {path}")


# =====================================================
#  Analysis : Below should be independent on above functions 
# =====================================================

# ==== Percentile Statistics / Outlier Classification ====
def _axis_diff_stats(records, percentile, is_abs=True):
    """Computes each axis's diff (or |diff|) median/percentile, shared by percentile_analysis and outlier_analysis.

    Returns:
        dict[str, dict]: stats[axis] = {"abs_diff": ndarray, "median": float,
                                          "percentile": percentile, "percentile_value": float}
    """
    stats = {}
    for axis in ("t", "x", "y", "z"):
        diff = np.array([r[f"d{axis}"] for r in records])
        if is_abs:
            diff = np.abs(diff)
        stats[axis] = {
            "abs_diff": diff,
            "median": np.median(diff),
            "percentile": percentile,
            "percentile_value": np.percentile(diff, percentile),
        }
    return stats


def percentile_analysis(records, is_abs, output_dir, file_name="abs_diff_distributions", percentile=PERCENTILE, val_thr=None):
    """Builds each axis's |diff| distribution, uses it to report a resolution, and plot the distribution with median and percentile threshold marked.

    Returns:
        tuple[dict, list[dict]]: (stats, outliers) where
            stats[axis] = {"abs_diff": ndarray, "median": float,
                           "percentile": percentile, "percentile_value": float}
    """
    if val_thr is not None:
        records = [r for r in records if r["val"] >= val_thr]

    stats = _axis_diff_stats(records, percentile, is_abs=is_abs)

    axis_units = {"t": "us", "x": "mm", "y": "mm", "z": "mm"}

    fig, axes = plt.subplots(1, 4, figsize=(15, 4.5))
    for ax, axis in zip(axes, ("t", "x", "y", "z")):
        s = stats[axis]
        unit = axis_units[axis]
        ax.hist(s["abs_diff"], bins=50, color="tab:blue", alpha=0.7, edgecolor="black")


        ax.axvline(s["median"], color="red", linestyle="-", label=f"median={s['median']:.2f}{unit}")
        ax.axvline(s["percentile_value"], color="red", linestyle="--",
                   label=f"{s['percentile']:.0f}th pct={s['percentile_value']:.2f}{unit}")
        ax.set_xlabel(f"|blob_{axis} - depo_{axis}| [{unit}]")
        ax.set_ylabel("count")
        ax.set_title(f"{axis}-axis: median={s['median']:.2f}{unit}, \n {s['percentile']:.0f}th pct={s['percentile_value']:.2f}{unit}")
        ax.legend(fontsize="small")
    fig.suptitle("Depo vs. Reco Blob |Center Difference| Distribution")
    fig.tight_layout()
    save_and_show(fig, output_dir, file_name, show=False)

    for axis in ("t","x", "y", "z"):
        s = stats[axis]
        unit = axis_units[axis]
        print(
            f"[ANALYSIS] {axis}-axis: median={s['median']:.3f}{unit} "
            f"{s['percentile']:.2f}th percentile={s['percentile_value']:.3f}{unit}"
        )

    return stats


def outlier_analysis(records, percentile=OUTLIER_PERCENTILE, val_thr=None):
    """Builds each axis's |diff| distribution, and uses it both to report a robust
    center/spread and to classify outliers 

    Returns:
        tuple[dict, list[dict]]: (stats, outliers) where
            stats[axis] = {"abs_diff": ndarray, "median": float,
                           "percentile": percentile, "percentile_value": float}
    """
    stats = _axis_diff_stats(records, percentile, is_abs=True)

    outliers = []
    for r in records:
        flagged = any(
            abs(r[f"d{axis}"]) > stats[axis]["percentile_value"]
            for axis in ("t", "x", "y", "z")
        )
        if val_thr is not None and r["val"] < val_thr:
            flagged = True
        if flagged:
            outliers.append(r)
    return stats, outliers


def _slice_blob_points(blobs, sliceid):
    """Collects (index, blob node, (z, y) corner points) for every blob in `sliceid`."""
    out = []
    for j, ob in enumerate(blobs):
        if ob.get("sliceid") != sliceid:
            continue
        corners = np.array(ob.get("corners", []))
        if corners.size < 6:
            continue
        out.append((j, ob, corners[:, [2, 1]]))
    return out


def _plot_slice_blob_outlines_tran_ax(ax, blobs, sliceid, target_blob_idx, show_labels=True):
    """Draws (Z, Y) outline polygons for every blob in `sliceid`, highlighting
    `target_blob_idx` (the outlier) and dimming the other overlapping blobs
    in the same slice so both are visible without competing for attention.

    Returns:
        list[ndarray]: the (z, y) corner points of every drawn blob, so the
            caller can size the axis limits to actually contain them.
    """
    slice_blobs = _slice_blob_points(blobs, sliceid)
    if not slice_blobs:
        print(f"[INFO] Slice {sliceid}: No matching blobs found to plot.")
        return []

    other_legend_added = False
    all_pts = []
    for j, ob, pts in slice_blobs:
        all_pts.append(pts)
        pts_center = pts.mean(axis=0)
        angles = np.arctan2(pts[:, 1] - pts_center[1], pts[:, 0] - pts_center[0])
        sorted_pts = pts[np.argsort(angles)]

        is_target = j == target_blob_idx
        if not show_labels:
            label = None
        elif is_target:
            label = f"outlier blob (val={ob['val']:.4f} [e-])"
        elif not other_legend_added:
            label = f"other blobs in slice"
            other_legend_added = True
        else:
            label = None

        poly = patches.Polygon(
            sorted_pts, closed=True, fill=False,
            edgecolor="tab:red" if is_target else "0.6",
            linewidth=2.5 if is_target else 1.0,
            alpha=1.0 if is_target else 0.4,
            joinstyle="round",
            zorder=10 if is_target else 8,
            label=label,
        )
        ax.add_patch(poly)

    return all_pts


def _boxes_overlap(box1, box2):
    """Checks whether two (z_lo, z_hi, y_lo, y_hi) boxes overlap."""
    z_lo1, z_hi1, y_lo1, y_hi1 = box1
    z_lo2, z_hi2, y_lo2, y_hi2 = box2
    return not (z_hi1 < z_lo2 or z_hi2 < z_lo1 or y_hi1 < y_lo2 or y_hi2 < y_lo1)


def _draw_break_marks(ax_left, ax_right):
    """Draws the standard diagonal '//' break-mark ticks between two adjacent
    axes, signaling that the (Z, Y) region jumps discontinuously between them."""
    d = 0.02
    kwargs = dict(transform=ax_left.transAxes, color="k", clip_on=False, lw=1.2)
    ax_left.plot((1 - d, 1 + d), (-d, d), **kwargs)
    ax_left.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)
    kwargs["transform"] = ax_right.transAxes
    ax_right.plot((-d, d), (-d, d), **kwargs)
    ax_right.plot((-d, d), (1 - d, 1 + d), **kwargs)


def _draw_transverse_layers(ax, depos, blobs, b, blob_idx, bc, depo_charge_in_slice, draw_depo, draw_blob, show_labels, depo_idx=0):
    """Draws the depo Gaussian heatmap and/or blob outlines onto `ax`, without touching axis limits."""
    if draw_depo:
        # depo_charge_in_slice (not b["val"]): the heatmap should show the
        # depo's own charge density, and b["val"] can be 0 for a degenerate
        # blob -- an all-zero density array makes pcolormesh color everything
        # with the colormap's midpoint (a solid magma-pink fill) instead of
        # a proper Gaussian.
        plot_depo_gaussian_tran_ax(ax, depos, depo_charge_in_slice, n_sigma=15, set_limit=False, show_labels=show_labels, index=depo_idx)
        if show_labels:
            # No marker for the depo center (redundant with the util's own
            # "Depo Center" +); a label-only, invisible artist instead
            # reports its charge in this slice in the legend.
            ax.plot([], [], " ", label=f"depo charge in slice={depo_charge_in_slice:.4f} [e-]")
    if draw_blob:
        _plot_slice_blob_outlines_tran_ax(ax, blobs, b.get("sliceid"), blob_idx, show_labels=show_labels)
        # bc is [t_us, x, y, z]; this panel's axes are (Z, Y), so the marker
        # coordinates are (index 3, index 2), not (index 2, index 1).
        ax.scatter([bc[3]], [bc[2]], color="lime", marker="x", s=120, zorder=11,
                   label=(f"blob {blob_idx} center" if show_labels else None))
    # The heatmap only covers the depo's n_sigma grid, which can be smaller
    # than the view; fill the rest of the axes with the colormap's
    # zero-density color (black) instead of the default white background.
    ax.set_facecolor("black")


def _plot_depo_gaussian_x_ax(ax, depos, v_drift, t_offset, response_plane_x, depo_idx=0, n_sigma=5):
    """Plots the depo's longitudinal Gaussian charge density against x-position
    (mm) instead of drift time -- same curve as plot_depo_gaussian_long_ax,
    just with every time sample run through convert_time2x first."""
    total_q = abs(depos["q"][depo_idx])
    sigma_us = depos["L"][depo_idx] / v_drift
    mean_us = (depos["t"][depo_idx] / 1000.0) + t_offset

    t_cont = np.linspace(mean_us - n_sigma * sigma_us, mean_us + n_sigma * sigma_us, 1000)
    y_dens = (total_q / (sigma_us * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((t_cont - mean_us) / sigma_us) ** 2)
    x_cont = convert_time2x(t_cont, v_drift, response_plane_x)

    ax.plot(x_cont, y_dens, color="royalblue", lw=1.0, ls="--", label="Depo (Gaussian)", alpha=0.8, zorder=3)
    ax.fill_between(x_cont, y_dens, color="royalblue", alpha=0.1, zorder=2)
    ax.set_xlabel("X [mm]")
    ax.set_ylabel(r"Charge Density [$e/\mu$s]")


def plot_outliers(data_cache, outliers, output_dir, n_outlier_plots=N_OUTLIER_PLOTS, v_drift=V_DRIFT, t_offset=T_OFFSET, response_plane_x=RESPONSE_PLANE_X, outlier_name="outliers"):
    """Saves a (transverse corner scatter) + (longitudinal Gaussian/slice window) overlay
    for the top `n_outlier_plots` outliers, sorted by descending 3D squared residual."""
    outliers_sorted = sorted(outliers, key=lambda r: r["dx"] ** 2 + r["dy"] ** 2 + r["dz"] ** 2, reverse=True
    )
    outlier_dir = os.path.join(output_dir, outlier_name)

    for r in outliers_sorted[:n_outlier_plots]:
        depos, blobs, depo_idx = data_cache[r["position"]]

        blob_idx = r["blob_index"]
        b = blobs[blob_idx]
        bc = blob_center(b, v_drift, response_plane_x)

        dc = depo_center(depos, depo_idx, v_drift, t_offset, response_plane_x)

        mean_ns = depos["t"][depo_idx] + t_offset * 1000.0
        sigma_ns = (depos["L"][depo_idx] / v_drift) * 1000.0
        depo_charge_in_slice = abs(depos["q"][depo_idx]) * gbounds(b["start"], b["start"] + b["span"], mean_ns, sigma_ns)

        print(f"[OUTLIER] Plotting position={r['position']} blob_index={blob_idx} "
              f"val={r['val']:.1f} dt={r['dt']:.3f}us dx={r['dx']:.3f}mm dy={r['dy']:.3f}mm dz={r['dz']:.3f}mm")

        # Transverse (Z, Y) panel: normally one axes zoomed to the union of
        # the depo's n_sigma window and every blob's outline in this slice.
        # But when the outlier blob sits far enough away that the two don't
        # even overlap, that union turns into a long, squished sliver where
        # neither region is readable. In that case split into two zoomed
        # mini-panels (near the depo, near the blob) with a broken-axis
        # break mark between them instead of one degenerate combined view.
        n_sigma = 10
        t_sigma = depos["T"][depo_idx]
        depo_box = (
            depos["z"][depo_idx] - n_sigma * t_sigma, depos["z"][depo_idx] + n_sigma * t_sigma,
            depos["y"][depo_idx] - n_sigma * t_sigma, depos["y"][depo_idx] + n_sigma * t_sigma,
        )
        slice_blob_pts = [pts for _, _, pts in _slice_blob_points(blobs, b.get("sliceid"))]
        # The broken-axis decision (and the "near blob" zoom box) is based on
        # the target outlier blob's own corners only, not every blob sharing
        # its slice -- another blob in the same slice can happen to sit right
        # next to the depo, which would otherwise make the combined box span
        # (and "overlap") both regions even though the outlier itself is far away.
        target_corners = np.array(b.get("corners", []))
        if target_corners.size >= 6:
            target_pts = target_corners[:, [2, 1]]
            blob_box = (target_pts[:, 0].min() - 2, target_pts[:, 0].max() + 2,
                        target_pts[:, 1].min() - 2, target_pts[:, 1].max() + 2)
        else:
            blob_box = depo_box
        broken = not _boxes_overlap(depo_box, blob_box)

        fig = plt.figure(figsize=(15, 5) if broken else (13, 5))
        outer_gs = fig.add_gridspec(1, 2, width_ratios=[1, 1])

        if broken:
            inner_gs = outer_gs[0].subgridspec(1, 2, wspace=0.08)
            ax_t_near = fig.add_subplot(inner_gs[0])
            ax_t_far = fig.add_subplot(inner_gs[1])

            _draw_transverse_layers(ax_t_near, depos, blobs, b, blob_idx, bc, depo_charge_in_slice,
                                     draw_depo=True, draw_blob=True, show_labels=True, depo_idx=depo_idx)
            # plot_depo_gaussian_tran_ax (called above via show_labels=True)
            # draws its own small in-axes legend; drop it since its handles
            # are folded into the combined fig-level legend built below.
            near_legend = ax_t_near.get_legend()
            if near_legend is not None:
                near_legend.remove()
            ax_t_near.set_xlim(depo_box[0], depo_box[1])
            ax_t_near.set_ylim(depo_box[2], depo_box[3])
            ax_t_near.set_aspect("equal", adjustable="box")
            ax_t_near.set_xlabel("Z [mm]")
            ax_t_near.set_ylabel("Y [mm]")
            ax_t_near.set_title(f"near depo (dy={r['dy']:.2f}mm  dz={r['dz']:.2f}mm)")

            _draw_transverse_layers(ax_t_far, depos, blobs, b, blob_idx, bc, depo_charge_in_slice,
                                     draw_depo=False, draw_blob=True, show_labels=True)
            ax_t_far.set_xlim(blob_box[0], blob_box[1])
            ax_t_far.set_ylim(blob_box[2], blob_box[3])
            ax_t_far.set_aspect("equal", adjustable="box")
            ax_t_far.set_xlabel("Z [mm]")
            ax_t_far.set_title("near blob")
            _draw_break_marks(ax_t_near, ax_t_far)

            # Placed outside the axes (below) so it never covers the plotted
            # blobs/heatmap; save_and_show() saves with bbox_inches='tight',
            # so the saved image simply grows to fit it instead of clipping.
            # Both panels draw every blob in the slice (so each shows whichever
            # of them actually fall in its own zoom window), which duplicates
            # labels like "blob N center" across the two -- de-duplicate by
            # label, keeping first occurrence, before building the legend.
            handles_all = ax_t_near.get_legend_handles_labels()[0] + ax_t_far.get_legend_handles_labels()[0]
            labels_all = ax_t_near.get_legend_handles_labels()[1] + ax_t_far.get_legend_handles_labels()[1]
            seen = set()
            handles, labels = [], []
            for h, l in zip(handles_all, labels_all):
                if l not in seen:
                    seen.add(l)
                    handles.append(h)
                    labels.append(l)
            fig.legend(handles, labels, fontsize="small", loc="upper center",
                       bbox_to_anchor=(0.25, -0.02), ncol=2)
        else:
            ax_t = fig.add_subplot(outer_gs[0])
            _draw_transverse_layers(ax_t, depos, blobs, b, blob_idx, bc, depo_charge_in_slice,
                                     draw_depo=True, draw_blob=True, show_labels=True, depo_idx=depo_idx)
            z_lo, z_hi, y_lo, y_hi = depo_box
            if slice_blob_pts:
                pts = np.vstack(slice_blob_pts)
                z_lo, z_hi = min(z_lo, pts[:, 0].min() - 2), max(z_hi, pts[:, 0].max() + 2)
                y_lo, y_hi = min(y_lo, pts[:, 1].min() - 2), max(y_hi, pts[:, 1].max() + 2)
            ax_t.set_xlim(z_lo, z_hi)
            ax_t.set_ylim(y_lo, y_hi)
            ax_t.set_aspect("equal", adjustable="box")
            ax_t.set_xlabel("Z [mm]")
            ax_t.set_ylabel("Y [mm]")
            ax_t.set_title(f"dy={r['dy']:.2f}mm  dz={r['dz']:.2f}mm")
            ax_t.legend(fontsize="small", loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)

        # Longitudinal (x) panel: x-position instead of drift time, and only
        # the target blob's own slice window is shown (no gray spans for
        # other slices -- unlike the transverse panel, every other slice is
        # simply a different x-window on the same depo, not useful context).
        ax_l = fig.add_subplot(outer_gs[1])
        _plot_depo_gaussian_x_ax(ax_l, depos, v_drift, t_offset, response_plane_x, depo_idx=depo_idx, n_sigma=5)

        x0 = convert_time2x(b["start"] / 1000.0, v_drift, response_plane_x)
        x1 = convert_time2x((b["start"] + b["span"]) / 1000.0, v_drift, response_plane_x)
        ax_l.axvspan(min(x0, x1), max(x0, x1), color="tab:red", alpha=0.3, label="Current slice")

        x_peak = convert_time2x((depos["t"][depo_idx] / 1000.0) + t_offset, v_drift, response_plane_x)
        ax_l.axvline(x_peak, color="red", linestyle=":", lw=1.5, label=f"Peak: {x_peak:.2f}mm", zorder=5)

        t_slice_centroid_us = truncated_gaussian_mean(b["start"], b["start"] + b["span"], mean_ns, sigma_ns) / 1000.0
        x_slice_centroid = convert_time2x(t_slice_centroid_us, v_drift, response_plane_x)
        ax_l.axvline(x_slice_centroid, color="tab:red", linestyle="-.", lw=1.5,
                    label=f"Slice centroid: {x_slice_centroid:.2f}mm", zorder=6)

        # bc[1] is the blob's own x (from the slice's time midpoint, see
        # blob_center()) -- the blob's reconstructed center, not the depo's.
        ax_l.axvline(bc[1], color="lime", linestyle="--", lw=1.5, label=f"Blob center: {bc[1]:.2f}mm", zorder=6)

        ax_l.legend(fontsize="small")
        ax_l.set_title(f"dx={r['dx']:.2f}mm")

        fig.suptitle(
            f"Outlier case(blob_index={blob_idx}) at position {r['position']})\n"
            f"depo center (x,y,z)=({dc[1]:.2f}, {dc[2]:.2f}, {dc[3]:.2f})mm   "
            f"blob center (x,y,z)=({bc[1]:.2f}, {bc[2]:.2f}, {bc[3]:.2f})mm\n"
            f"depo charge in slice={depo_charge_in_slice:.4f} [e-]   blob charge (val)={b['val']:.4f} [e-]"
        )
        fig.tight_layout()
        save_and_show(fig, outlier_dir, f"{r['position']}_blob{blob_idx}_overlay", show=False)


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "per_file":
        groups = collect_groups_per_file(
            args.data_base_dir, args.anode_index,
            args.depo_prefix, args.depo_surfix,
            args.cluster_prefix, args.cluster_surfix,
        )
    else:
        groups = collect_groups_one(
            args.depo_file, args.reco_file,
            args.t_offset, args.v_drift, args.anode1_x_pos,
        )

    records, data_cache = collect_records(
        groups, args.v_drift, args.t_offset, args.anode1_x_pos, args.mean_method,
    )
    if not records:
        print("[ERROR] No records collected; aborting.")
    else:
        save_csv(records, os.path.join(args.output_dir, f"center_diff_data_{args.tag}.csv"))

    percentile_analysis(records, True, args.output_dir, file_name=f"abs_diff_distributions_{args.tag}", percentile=args.percentile, val_thr=args.val_thr)

    outlier_stats, outliers = outlier_analysis(records, percentile=args.outlier_percentile, val_thr=args.val_thr)
    save_csv(outliers, os.path.join(args.output_dir, f"outliers_{args.tag}.csv"))
    plot_outliers(
        data_cache, outliers, args.output_dir,
        n_outlier_plots=args.n_outlier_plots,
        v_drift=args.v_drift, t_offset=args.t_offset, response_plane_x=args.anode1_x_pos,
        outlier_name=f"outliers_{args.tag}",
    )