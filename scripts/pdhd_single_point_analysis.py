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

# from scripts.utils.evaluation.charge_analysis import *
# from scripts.utils.evaluation.img_evaluation import *

# ==== Common Paramters for PDHD ====
WIRE_FILE = "/nfs/data/1/yujin/img_evaluation/wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2"

DATA_BASE_PATH = "/nfs/data/1/yujin/img_evaluation/data/pdhd"
OUTPUT_PATH = "/nfs/data/1/yujin/img_evaluation/results/pdhd/test_point_depo"

V_DRIFT = 1.6 # [us]
T_SPAN = 2 # [us]
T_OFFSET = 314.5 # [us]
ANODE1_X_POS = 3430.47 # [mm]


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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect a single point-depo run's depo/cluster/bdf outputs.")
    parser.add_argument(
        "--data-dir",
        help="directory containing depos-drifted-<N>.zip, clusters-apa-<N>.tar.gz, "
             "clusters-apa-bdf-<N>.tar.gz. Either a subdirectory name under "
             "%s (e.g. test_point_depo) or a full path." % DATA_BASE_PATH)
    return parser.parse_args()


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
    # depos_inspect(depo_post, depo_pre)
    # single_depo_inspect(depo_post, 0)

    # graph_inspect(blobs_graph)

    # summarize_blobs(blobs)
    # summarize_blobs(bdfs)
    # summarize_slices(blobs_slices)
    # summarize_wire(blobs_wires)

    # single_blob_inspect(blobs, 0)
    # single_blob_inspect(blobs, 1)


    # ==== Binning ====
    refernce_t = blobs_slices[0]["start"] / 1000 # us
    t_min = 1514
    t_max = 1526

    bins = Binning(t_min, t_max, T_SPAN, refernce_t)


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