"""Transverse (Y-Z) overlay plots comparing true blobs (from depo) to reco blobs.

Summary: Draws a depo-derived true-blob polygon (see `utils.true_blob`)
together with the reconstructed blob(s) it should overlap, on the same
(Z, Y) axes convention already used by `utils.vis.transverse_plots`, for
visual sanity-checking of the true-blob geometry. Optionally also draws
the source depo's own true (unsnapped) nsigma boundary
(`plot_depo_heatmap_tran_ax`) underneath the polygons, on a solid black
background, as an outline only (no fill), so the true-blob polygon's
shape can be checked against the raw depo extent it was built from, not
just against the reco blob.

Usage:
    import sys
    sys.path.insert(0, "scripts")
    from utils.vis.true_blob_plots import plot_true_vs_reco_check

    plot_true_vs_reco_check(
        true_blobs, reco_blobs, depo_indices=[0, 1000, 2500, 4999],
        output_dir="results/pdhd/true_blob_check", filename="single_trk_overlay",
        depos=depos,  # optional: also draws each depo's true nsigma boundary
    )
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

from utils.vis.plot_utils import save_and_show
from docs.axive.position_shape import reco_blob_polygon


def nearest_reco_blob(true_blob, reco_blobs):
    """Returns the reco blob node whose (Y, Z) centroid is closest to `true_blob`'s.

    Matching is spatial, not time-based: the offset between a depo's raw
    time and a reconstructed blob's `start` time (picked up from the
    frame's `start_time`/DepoTransform config) is a known, still-being-
    calibrated quantity in this project (see git history / CLAUDE.md), so
    a time-slice-overlap match is not yet reliable. Spatial matching is
    enough to sanity-check the true-blob polygon's geometry independent
    of that open time-offset question; `compare_true_to_reco`'s time- and
    charge-based metrics should be read with that caveat in mind.
    """
    true_poly = true_blob["polygon"]
    if true_poly is None or true_poly.is_empty:
        return None
    true_centroid = np.array(true_poly.centroid.coords[0])

    best, best_dist = None, None
    for b in reco_blobs:
        reco_centroid = np.array(reco_blob_polygon(b).centroid.coords[0])
        dist = np.linalg.norm(true_centroid - reco_centroid)
        if best_dist is None or dist < best_dist:
            best, best_dist = b, dist
    return best


def plot_depo_heatmap_tran_ax(ax, y, z, extent_tran, nsigma=3.0):
    """Draws the true depo's transverse (Z, Y) boundary on a black background.

    The axes background is set fully black (`ax.set_facecolor("black")`,
    covering the whole subplot, not just some finite grid), and the depo's
    true (unsnapped) extent -- the `nsigma * extent_tran` circle used as
    the raw cutoff in `utils.true_blob.true_blob_polygon` before wire-
    snapping -- is drawn as an outline only, with no fill, so it reads as a
    silhouette against the black background rather than a filled shape.
    This is deliberately not a continuous density heatmap: only the
    boundary is shown, so it stays legible under the (also unfilled) true-
    blob and reco-blob outlines `plot_true_vs_reco_tran_ax` draws on top.

    Args:
        ax: Matplotlib axes.
        y (float), z (float): Depo position.
        extent_tran (float): Transverse diffusion sigma.
        nsigma (float): Radius of the drawn boundary circle, in units of
            `extent_tran`.
    """
    ax.set_facecolor("black")
    ax.scatter(z, y, color="red", marker="+", s=80, zorder=3, label="Depo center")
    ax.add_patch(patches.Circle(
        (z, y), nsigma * extent_tran, fill=False, edgecolor="white", linestyle="--",
        linewidth=1.2, alpha=0.9, zorder=3, label=f"True depo ({nsigma:.0f}$\\sigma_T$ boundary)",
    ))


def plot_true_vs_reco_tran_ax(ax, true_polygon, reco_blob_node, depo=None, margin=5.0):
    """Draws one true-blob polygon and one reco-blob outline on the given axes.

    Follows the (Z, Y) axis convention used by
    `utils.vis.transverse_plots.plot_reco_blobs_tran_ax`. Axis limits are
    set explicitly from the drawn shapes' bounds, since generic Polygon
    patches are not always included in matplotlib's autoscaling.

    Args:
        depo (dict or None): If given, a dict with keys `y`, `z`,
            `extent_tran` for the source depo; its true (unsnapped) nsigma
            boundary is drawn on a black background under the polygons via
            `plot_depo_heatmap_tran_ax`, so the true-blob polygon's shape
            can be visually compared against the raw depo extent it was
            built from.
    """
    all_pts = []

    if depo is not None:
        plot_depo_heatmap_tran_ax(ax, depo["y"], depo["z"], depo["extent_tran"])

    if reco_blob_node is not None:
        reco_poly = reco_blob_polygon(reco_blob_node)
        reco_pts = np.array(reco_poly.exterior.coords)[:, [1, 0]]
        all_pts.append(reco_pts)
        ax.add_patch(patches.Polygon(
            reco_pts, closed=True, fill=False, edgecolor="#00FFFF",
            linewidth=3.0, label="Reco blob", zorder=5,
        ))

    if true_polygon is not None and not true_polygon.is_empty:
        true_pts = np.array(true_polygon.exterior.coords)[:, [1, 0]]
        all_pts.append(true_pts)
        ax.add_patch(patches.Polygon(
            true_pts, closed=True, fill=True, facecolor="#FF00FF", alpha=0.4,
            edgecolor="#FF00FF", linewidth=1.5, label="True blob (depo)", zorder=6,
        ))

    if all_pts:
        concat_pts = np.vstack(all_pts)
        z_min, z_max = concat_pts[:, 0].min(), concat_pts[:, 0].max()
        y_min, y_max = concat_pts[:, 1].min(), concat_pts[:, 1].max()
        ax.set_xlim(z_min - margin, z_max + margin)
        ax.set_ylim(y_min - margin, y_max + margin)

    ax.set_xlabel("Z [mm]")
    ax.set_ylabel("Y [mm]")
    ax.legend(loc="upper right", fontsize=8)


def plot_true_vs_reco_check(true_blobs, reco_blobs, depo_indices, output_dir, filename, depos=None):
    """Plots a grid of true-vs-reco overlays for the given depo indices.

    Args:
        true_blobs (list[dict]): Output of `utils.true_blob.build_true_blobs`.
        reco_blobs (list[dict]): Reco blob nodes, as returned by
            `utils.load.load_graph_nodes(cgraph, 'b')`.
        depo_indices (list[int]): Which entries of `true_blobs` to plot.
        output_dir (str): Directory to save the figure into.
        filename (str): Output file name (".png" appended if absent).
        depos (dict or None): If given, the same `load_generation_data`-style
            dict of arrays (keys `y`, `z`, `T`) used to build `true_blobs`;
            each subplot then also draws that depo's true (unsnapped)
            nsigma boundary on a black background under the polygons (see
            `plot_true_vs_reco_tran_ax`).
    """
    ncols = len(depo_indices)
    fig, axes = plt.subplots(1, ncols, figsize=(5 * ncols, 5), squeeze=False)
    axes = axes[0]

    for ax, idx in zip(axes, depo_indices):
        true_blob = true_blobs[idx]
        reco_blob_node = nearest_reco_blob(true_blob, reco_blobs)
        depo = None
        if depos is not None:
            depo = {"y": depos["y"][idx], "z": depos["z"][idx], "extent_tran": depos["T"][idx]}
        plot_true_vs_reco_tran_ax(ax, true_blob["polygon"], reco_blob_node, depo=depo)
        ax.set_title(f"depo #{idx}")
        ax.set_aspect("equal")
        ax.autoscale_view()

    fig.tight_layout()
    return save_and_show(fig, output_dir, filename, show=False)
