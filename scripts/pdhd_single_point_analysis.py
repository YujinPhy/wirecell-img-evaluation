import argparse
import glob
import os
import re
import sys

from utils.load import *
from utils.depo_inspect import *
from utils.blob_inspect import *

from utils.slicer import *
from utils.vis.longitudinal_plots import *
from utils.vis.transverse_plots import *
from utils.vis.depo_3d import *
# from utils.wire_utils import *


# ==== Common Paramters for PDHD ====
WIRE_FILE = "/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2"

DATA_BASE_PATH = "/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd"
OUTPUT_PATH = "/nfs/data/1/yujin/wirecell-img-evaluation/results/pdhd/test_point_depo"

ANODE_INDEX = 1
RESPONSE_PLANE_X = 3430.47   # [mm]

V_DRIFT = 1.6            # [mm/us]
T_OFFSET = 314.5         # [us]

def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect a single point-depo run's depo/cluster/bdf outputs.")
    parser.add_argument(
        "--data-dir",
        help="directory containing depos-drifted-<N>.zip, clusters-apa-<N>.tar.gz, "
             "clusters-apa-bdf-<N>.tar.gz. Either a subdirectory name under "
             "%s (e.g. test_point_depo) or a full path." % DATA_BASE_PATH)
    return parser.parse_args()


# ==== Data I/O ====
def resolve_data_dir(data_dir):
    """Resolve data_dir against DATA_BASE_PATH so a bare subdirectory name works.

    Accepts either just a subdirectory name (looked up under DATA_BASE_PATH)
    or a normal relative/absolute path (used as-is if it exists).
    """
    under_base = os.path.join(DATA_BASE_PATH, data_dir)
    if os.path.isdir(under_base):
        return under_base
    if os.path.isdir(data_dir):
        return data_dir
    raise FileNotFoundError("data directory not found under %s or as given: %s" % (DATA_BASE_PATH, data_dir))


def find_anode_files(data_dir):
    """Locate the (anode, depo, rec, bdf) file set for a single anode inside data_dir."""
    depo_candidates = glob.glob(os.path.join(data_dir, "depos-drifted-*.zip"))
    if not depo_candidates:
        raise FileNotFoundError("no depos-drifted-*.zip found in %s" % data_dir)
    if len(depo_candidates) > 1:
        raise ValueError("expected a single anode's depo file in %s, found: %s" % (data_dir, depo_candidates))
    depo_file = depo_candidates[0]

    m = re.search(r"depos-drifted-(\d+)\.zip$", os.path.basename(depo_file))
    anode = m.group(1)

    reco_file = os.path.join(data_dir, "clusters-apa-%s.tar.gz" % anode)
    bdf_file = os.path.join(data_dir, "clusters-apa-bdf-%s.tar.gz" % anode)
    for fp in (reco_file, bdf_file):
        if not os.path.exists(fp):
            raise FileNotFoundError("expected file not found: %s" % fp)

    return anode, depo_file, reco_file, bdf_file


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


# ==== Deposition Analysis ====
def depo_center(depos, depo_idx=0):
    """Returns the (x, y, z) center [mm] of a depo from pre-drif (Gen1) depo data.

    Args:
        depos (dict): Depos data loaded from a depos-drifted-<N>.zip file.
        depo_idx (int): Index of the depo to analyze.
    """
    x = depos["x"][depo_idx]
    y = depos["y"][depo_idx]
    z = depos["z"][depo_idx]
    return np.array([x, y, z])


def depo_center_undrifted(depos, depo_idx=0, v_drift=V_DRIFT, t_offset=T_OFFSET, response_plane_x=RESPONSE_PLANE_X):
    """Recovers the pre-drift depo (x, y, z) center [mm] from post-drift (Gen0) depo data.

    Gen0's `t` already encodes the pure drift transit time (no frame offset
    applied), so `x = anode1_x_pos - v_drift * t_us` alone recovers the
    original x to sub-0.01mm accuracy (verified against Gen1 ground truth).
    No `t_offset` here: that offset only matters when converting a *reco-clock*
    time (e.g. a blob's slice `start`, see `blob_center`) into this same
    physical-drift-time clock; Gen0's `t` is already on it.
    """
    t_us = depos["t"][depo_idx] / 1000.0 + t_offset  # [us]
    x = convert_time2x(t_us, v_drift, response_plane_x)
    y = depos["y"][depo_idx]
    z = depos["z"][depo_idx]
    return np.array([x, y, z])


def depo_slice_center(depos, method, slice_start, slice_end, v_drift, t_offset, response_plane_x, depo_idx=0):
    """Depo (x, y, z) center restricted to one reco slice's time window.

    A single depo's diffusion Gaussian in time typically spans several reco
    slices, each producing its own reco blob; comparing every one of those
    blobs against the depo's global (untruncated) mean is not apples-to-
    apples, since a blob only captures the fraction of the depo's charge
    that falls inside its own slice.

    `method="truncated_mean"` (recommended) uses the truncated-normal mean
    of the depo's time-Gaussian within [slice_start, slice_end]
    (`truncated_gaussian_mean`), converted back to physical time/x with the
    same `t_us - t_offset` step as `blob_center` (both slice_start/slice_end
    and the truncated mean live on the reco clock). Any other `method` value
    falls back to the plain slice midpoint `(slice_start+slice_end)/2` --
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

        trunc_mean_us = truncated_gaussian_mean(slice_start, slice_end, mean_ns, sigma_ns) / 1000.0

        x = convert_time2x(trunc_mean_us - t_offset, v_drift, response_plane_x)
    else:
        mid_us = (slice_start + slice_end) / 2.0 / 1000.0
        x = convert_time2x(mid_us - t_offset, v_drift, response_plane_x)

    y = depos["y"][depo_idx]
    z = depos["z"][depo_idx]
    return np.array([x, y, z])


if __name__ == "__main__":
    args = parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    anode, depo_file, reco_file, bdf_file = find_anode_files(data_dir)
    print("[INFO] anode=%s" % anode)
    print("[INFO] depo_file=%s" % depo_file)
    print("[INFO] reco_file=%s" % reco_file)
    print("[INFO] bdf_file=%s" % bdf_file)

    # wire_data = load_wire_store(json_path=WIRE_FILE)

    # ==== Data Loading ====
    depo_post = load_generation_data(depo_file, 0)
    depo_pre = load_generation_data(depo_file, 1)

    blobs_graph = load_cluster_data(reco_file, 0)
    bdf_graph = load_cluster_data(bdf_file, 0)

    blobs = load_graph_nodes(blobs_graph, "b")
    bdfs = load_graph_nodes(bdf_graph, "b")

    blobs_slices = load_graph_nodes(blobs_graph, "s")
    blobs_wires = load_graph_nodes(blobs_graph, "w")


    # ==== Inspection ====
    depos_inspect(depo_post, depo_pre)
    single_depo_inspect(depo_post, 0)

    graph_inspect(blobs_graph)

    summarize_blobs(blobs)
    summarize_blobs(bdfs)
    # summarize_wire(blobs_wires)
    
    # single_blob_inspect(blobs, 0)
    # single_blob_inspect(blobs, 1)

    # ==== Slice Info ====
    summarize_slices(blobs_slices)
    slice_list = get_slice_info(blobs_graph)
    print(slice_list)





















    # ==== Plot: Only Depo ====
    # depo_gaussian_3d(depo_post, 0, 5, OUTPUT_PATH, "3d_point_depo_x300.png")
    # depo_gaussian_3d_time(depo_post, 0, 5,  V_DRIFT, T_OFFSET, OUTPUT_PATH, "3d_point_depo_time_x300.png")
    
    fig, ax = plt.subplots(figsize=(11, 7))
    plot_depo_gaussian_long_ax(ax, depo_post, V_DRIFT, T_OFFSET, 0)
    
    # # ==== Longitudinal Analysis ====
    # total_charges, slices_data = summrize_slice_charges(depo_post, blobs, bdfs, V_DRIFT, T_OFFSET)
    # print_slice_charge_summary(total_charges, slices_data)

    # # plot_longitudinal_charge_distribution(depo_post, blobs, bdfs, bins, V_DRIFT, T_OFFSET, total_charges, OUTPUT_PATH, "long_charge_distribution")
    
    # # ==== Tansverse Analysis ====
    # # slice_ids = [759, 760, 761]
    # # for i in slice_ids:
    # #     plot_transverse_charge_distribution(depo_post, blobs, bdfs, i, wire_data, slices_data, OUTPUT_PATH, f"trans_charge_distribution_sliceid{i}" )

    # # ==== Charge Density Study ====


    # blob_density(blobs, bdfs, V_DRIFT, T_SPAN)