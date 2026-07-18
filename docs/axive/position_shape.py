"""Position/shape evaluation metrics: true blob vs. reconstructed blob.

Summary: Compares a depo-based "true blob" (see `utils.true_blob`) against a
reconstructed blob node (as returned by `utils.load.load_graph_nodes(cgraph,
'b')`) on position/shape and charge, independent of how either polygon was
built. This is evaluation-metric logic (IoU, centroid distance, time-slice
overlap, charge relative error), not blob construction, so it is kept
separate from `utils.true_blob`, which only builds a true blob from a
depo. See `docs/position_shape_evaluation.md` for the full write-up and
`docs/true_blob_prototype.md` for how the true blob being compared here is
built.

Usage:
    import sys
    sys.path.insert(0, "scripts")
    from utils.true_blob import build_true_blob
    from utils.eval.position_shape import compare_true_to_reco

    true_blob = build_true_blob(plane_geoms, t=..., y=..., z=..., charge=...,
                                 extent_long=..., extent_tran=..., speed=...)
    metrics = compare_true_to_reco(true_blob, reco_blob_node)
    # metrics == {"iou": ..., "centroid_distance": ..., "time_overlap_frac": ..., "charge_rel_error": ...}
"""

from shapely.geometry import MultiPoint


def reco_blob_polygon(blob_node):
    """Builds a (y, z) polygon from a reconstructed blob node's `corners` field.

    `corners` entries are `[x, y, z]` with `x` constant across all corners
    of one blob (the slice's `start` time); only `y, z` are used here.
    """
    yz_points = [(corner[1], corner[2]) for corner in blob_node["corners"]]
    return MultiPoint(yz_points).convex_hull


def compare_true_to_reco(true_blob, reco_blob_node):
    """Compares one true blob (see `utils.true_blob.build_true_blob`) to one reconstructed blob node.

    Args:
        true_blob (dict): Output of `utils.true_blob.build_true_blob`.
        reco_blob_node (dict): A blob node dict, as returned by
            `utils.load.load_graph_nodes(cgraph, 'b')`.

    Returns:
        dict: {"iou": float, "centroid_distance": float,
            "time_overlap_frac": float, "charge_rel_error": float}.
    """
    true_poly = true_blob["polygon"]
    reco_poly = reco_blob_polygon(reco_blob_node)

    if true_poly is None or true_poly.is_empty or reco_poly.is_empty:
        iou = 0.0
        centroid_distance = float("nan")
    else:
        intersection_area = true_poly.intersection(reco_poly).area
        union_area = true_poly.union(reco_poly).area
        iou = intersection_area / union_area if union_area > 0 else 0.0
        centroid_distance = true_poly.centroid.distance(reco_poly.centroid)

    t_start, t_end = true_blob["start"], true_blob["start"] + true_blob["span"]
    r_start, r_end = reco_blob_node["start"], reco_blob_node["start"] + reco_blob_node["span"]
    overlap = max(0.0, min(t_end, r_end) - max(t_start, r_start))
    union_span = max(t_end, r_end) - min(t_start, r_start)
    time_overlap_frac = overlap / union_span if union_span > 0 else 0.0

    reco_charge = reco_blob_node["val"]
    charge_rel_error = (true_blob["charge"] - reco_charge) / reco_charge if reco_charge else float("nan")

    return {
        "iou": iou,
        "centroid_distance": centroid_distance,
        "time_overlap_frac": time_overlap_frac,
        "charge_rel_error": charge_rel_error,
    }
