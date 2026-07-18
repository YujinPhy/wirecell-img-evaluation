"""Transverse Charge Distribution Visualization Utilities.

This module provides functions to plot and save transverse (Y-Z plane)
charge distributions comparing a single depo (Gaussian), wire geometry,
and reconstructed blobs for one slice.

Structure:
- plot_depo_gaussian_tran_ax: Plots the transverse Gaussian for a single depo.
- plot_wires_tran_ax: Plots wire geometry for a given anode/face.
- plot_reco_blobs_tran_ax: Plots reconstructed blob outlines for a given slice.
- plot_transverse_charge_distribution: Composite plot for a single slice.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.patches import Circle
from matplotlib.collections import LineCollection

from utils.vis.plot_utils import save_and_show


# ==== For a Point Depo ====
def plot_depo_gaussian_tran_ax(ax, depo, slice_charge, n_sigma=5, set_limit=False, show_labels=True, index=0):
    """Plots a transverse Gaussian charge distribution for a single depo on a given axis.

    Args:
        ax: Matplotlib axes object to draw the plot.
        depo: Loaded Depo data dictionary.
        slice_charge: Total charge to be distributed in this slice.
        n_sigma: The range of the plotted Gaussian curve in units of sigma (default is 5).
        set_limit: If True, automatically adjusts the axis limits to the calculated n_sigma range.
        show_labels: If True, adds labels, title, and legend to the axes.
        index: Which entry of `depo` to plot, for multi-depo dicts (default 0).
    """
    if depo is None:
        print("[ERROR] Fail to load the Depo file.")
        return 0

    sigma = depo['T'][index]  # [mm]
    y_cen, z_cen = depo['y'][index], depo['z'][index]  # [mm]
    slice_charge = abs(slice_charge)

    grid_res = 300
    z_grid = np.linspace(z_cen - n_sigma * sigma, z_cen + n_sigma * sigma, grid_res)
    y_grid = np.linspace(y_cen - n_sigma * sigma, y_cen + n_sigma * sigma, grid_res)
    Z_mesh, Y_mesh = np.meshgrid(z_grid, y_grid)

    sigma2 = sigma ** 2
    amplitude = slice_charge / (2 * np.pi * sigma2)
    exponent = -0.5 * ((Z_mesh - z_cen) ** 2 + (Y_mesh - y_cen) ** 2) / sigma2
    density = amplitude * np.exp(exponent)

    im = ax.pcolormesh(Z_mesh, Y_mesh, density, cmap='magma', shading='auto', zorder=1)

    ax.scatter(z_cen, y_cen, color='red', marker='+', s=100, label='Depo Center', zorder=5)

    c1 = Circle((z_cen, y_cen), sigma, color='cyan', fill=False, linestyle='--',
                alpha=0.8, label=r'1-$\sigma_T$', zorder=4)
    c3 = Circle((z_cen, y_cen), 3 * sigma, color='white', fill=False, linestyle='-',
                alpha=0.6, linewidth=1.5, label=r'3-$\sigma_T$', zorder=4)
    ax.add_patch(c1)
    ax.add_patch(c3)

    if set_limit:
        ax.set_xlim(z_cen - n_sigma * sigma, z_cen + n_sigma * sigma)
        ax.set_ylim(y_cen - n_sigma * sigma, y_cen + n_sigma * sigma)
        ax.set_aspect('equal', adjustable='box')

    if show_labels:
        ax.set_xlabel("Z [mm]", fontsize=11)
        ax.set_ylabel("Y [mm]", fontsize=11)
        ax.set_title("Transverse Charge Distribution", fontsize=13)
        ax.legend(loc='upper right', fontsize='small')

        fig = ax.get_figure()
        fig.colorbar(im, ax=ax, label='Charge Density [$e/mm^2$]')

    return 1


# ==== For wires ====
def plot_wires_tran_ax(ax, wire_file_lists, anode_idx, face_pos, show_labels=True):
    """Plots wire geometry (U/V/W planes) for a given anode/face on a Y-Z axis.

    Args:
        ax: Matplotlib axes object to draw the plot.
        wire_file_lists: Loaded wire store data (see utils.load.load_wire_store).
        anode_idx (int): Index of the anode to draw.
        face_pos (int): Index of the face within the anode to draw.
        show_labels: If True, adds axis labels and a legend.
    """
    if wire_file_lists is None:
        print("[ERROR] Fail to load the Wire file.")
        return 0

    face_idx = wire_file_lists['anodes'][anode_idx]['faces'][face_pos]
    face = wire_file_lists['faces'][face_idx]
    colors = ['#00FF00', '#00FFFF', '#FFFFFF']
    plane_labels = ['U Plane', 'V Plane', 'W Plane']

    for i, p_ptr in enumerate(face['planes']):
        plane = wire_file_lists['planes'][p_ptr]
        wire_lines = []

        for w_ptr in plane['wires']:
            wire = wire_file_lists['wires'][w_ptr]
            pt1 = wire_file_lists['points'][wire['tail']]
            pt2 = wire_file_lists['points'][wire['head']]

            wz = [pt1['z'], pt2['z']]
            wy = [pt1['y'], pt2['y']]

            wire_lines.append([(wz[0], wy[0]), (wz[1], wy[1])])
        if wire_lines:
            lc = LineCollection(wire_lines, colors=colors[i], alpha=0.4,
                                 linewidths=0.8, zorder=2, label=plane_labels[i])
            ax.add_collection(lc)

    if show_labels:
        ax.set_xlabel("Z [mm]", fontsize=11)
        ax.set_ylabel("Y [mm]", fontsize=11)
        ax.legend(loc='upper right', fontsize='small')

    return 1


# ==== For Blobs ====
def plot_reco_blobs_tran_ax(ax, blobs, sliceid, set_limit=False, show_labels=True):
    """Plots reconstructed blob outlines (Y-Z corner polygons) for a given slice.

    Args:
        ax: Matplotlib axes object to draw the plot.
        blobs (list of dict): List of reconstructed blob node dictionaries.
        sliceid: Slice identity to filter blobs by.
        set_limit: If True, adjusts the axis limits to fit the drawn blob outlines.
        show_labels: If True, adds a legend entry for the blob outlines.
    """
    if not blobs:
        print("[ERROR] No blobs found.")
        return 0

    target_blobs = [b for b in blobs if b.get('sliceid') == sliceid]
    n_blob_in_slice = len(target_blobs)

    if not target_blobs:
        print(f"[INFO] Slice {sliceid}: No matching blobs found to plot.")
        return 0

    blob_legend_added = False
    all_pts = []

    for b in target_blobs:
        c_raw = np.array(b.get('corners', []))

        if c_raw.size >= 6:
            pts = c_raw[:, [2, 1]]
            if set_limit:
                all_pts.append(pts)

            pts_center = np.mean(pts, axis=0)
            angles = np.arctan2(pts[:, 1] - pts_center[1], pts[:, 0] - pts_center[0])
            sorted_pts = pts[np.argsort(angles)]

            if show_labels and not blob_legend_added:
                lbl = f'Slice {sliceid} Reco Blobs ({n_blob_in_slice})'
                blob_legend_added = True
            else:
                lbl = None

            poly = patches.Polygon(
                sorted_pts,
                closed=True,
                fill=False,
                edgecolor='#00FFFF',
                linewidth=4.0,
                joinstyle='round',
                zorder=10,
                label=lbl
            )
            ax.add_patch(poly)

    if set_limit and all_pts:
        concat_pts = np.vstack(all_pts)
        z_min, z_max = np.min(concat_pts[:, 0]), np.max(concat_pts[:, 0])
        y_min, y_max = np.min(concat_pts[:, 1]), np.max(concat_pts[:, 1])
        ax.set_xlim(z_min - 2, z_max + 2)
        ax.set_ylim(y_min - 2, y_max + 2)

    return 1


# ==== Composite plot ====
def plot_transverse_charge_distribution(depo, blobs, bdfs, sliceid, wire_data, charge_data,
                                         output_dir, filename, anode_idx=1, face_pos=1, show=True):
    """Composite transverse plot for one slice: depo Gaussian, wires, and reco blob outlines.

    Args:
        depo: Loaded single-depo data dictionary.
        blobs (list of dict): Reconstructed blob node dictionaries.
        bdfs (list of dict): True BDF blob node dictionaries (unused for now, kept for API symmetry).
        sliceid: Slice identity to plot.
        wire_data: Loaded wire store data (see utils.load.load_wire_store).
        charge_data (dict): Per-slice charge summary, keyed by sliceid, with
            'depo_q', 'reco_q', 'bdf_q' entries.
        output_dir (str): Directory to save the generated plot into.
        filename (str): Output file name (".png" appended if absent).
        anode_idx (int, optional): Anode index to draw wires for. Defaults to 1.
        face_pos (int, optional): Face index (within the anode) to draw wires for. Defaults to 1.
        show (bool, optional): If True, displays the plot after saving. Defaults to True.

    Returns:
        str: Full path of the saved plot.
    """
    fig, ax = plt.subplots(figsize=(7, 9))

    depo_charge_in_slice = charge_data[sliceid]['depo_q']
    q_blob = charge_data[sliceid]['reco_q']
    q_bdf = charge_data[sliceid]['bdf_q']

    target_blobs = [b for b in blobs if b.get('sliceid') == sliceid]
    n_blob_in_slice = len(target_blobs)

    plot_depo_gaussian_tran_ax(ax, depo, depo_charge_in_slice, n_sigma=15, set_limit=True, show_labels=True)
    plot_wires_tran_ax(ax, wire_data, anode_idx, face_pos, show_labels=False)
    plot_reco_blobs_tran_ax(ax, blobs, sliceid, set_limit=True, show_labels=False)

    ratio_blob = (q_blob / depo_charge_in_slice * 100) if depo_charge_in_slice > 0 else 0.0
    ratio_bdf = (q_bdf / depo_charge_in_slice * 100) if depo_charge_in_slice > 0 else 0.0

    info_text = (
        f"Num Blobs: {n_blob_in_slice}\n"
        f"Depo Charge in slices : {depo_charge_in_slice:.5e} e\n"
        f"Total Blob Charge     : {q_blob:.5e} e ({ratio_blob:.1f}%)\n"
        f"Total True Charge     : {q_bdf:.5e} e ({ratio_bdf:.1f}%)"
    )

    props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    ax.text(0.0, 1.01, info_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='bottom', horizontalalignment='left',
            fontfamily='monospace', bbox=props)

    return save_and_show(fig, output_dir, filename, show=show)
