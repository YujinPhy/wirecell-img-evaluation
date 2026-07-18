"""Longitudinal Charge Distribution Visualization Utilities.

This module provides functions to plot and save longitudinal charge
distributions comparing depositions (Gaussian), reconstructed blobs, and
true BDF blobs.

The reco-blob/BDF layer functions (plot_reco_blobs_long_ax, plot_bdfs_long_ax)
accept either a single node dict or a list of node dicts, and
plot_depo_gaussian_long_ax accepts an `index` argument to pick one entry out
of a multi-depo (e.g. track) depos dict. This lets the composite functions
below draw either the full multi-object overlay (default) or a single
depo/blob/bdf instance from within a track, and save it the same way.

Usage (plotting a single depo, a single reco blob, or a single BDF blob,
each on its own axes, without going through a composite/save function):
    # `depos` is a full track's depos dict (arrays); `blobs`/`bdfs` are lists
    # of node dicts, so `blobs[i]`/`bdfs[i]` picks one node out of the list.

    # 1) Depo only (index i out of the track's depos dict)
    fig, ax = plt.subplots()
    plot_depo_gaussian_long_ax(ax, depos, v_drift, t_offset_us, index=i)

    # 2) Reco blob only (single node dict, not a list)
    fig, ax = plt.subplots()
    plot_reco_blobs_long_ax(ax, blobs[i])

    # 3) True BDF blob only (single node dict, not a list)
    fig, ax = plt.subplots()
    plot_bdfs_long_ax(ax, bdfs[i])

Usage (overlaying depo + reco blob + BDF blob together, and saving to disk):
    # Same composite function used for full tracks; passing `depo_index` and
    # single blob/bdf dicts (instead of the full lists) restricts every
    # layer to one instance while still drawing them overlaid on one axes,
    # with slice edges and the charge info box, exactly like the full-track case.
    plot_longitudinal_charge_distribution_track(
        depos, blobs[i], bdfs[i], binning_obj, v_drift, t_offset_us,
        total_charge, output_dir, "single_depo_blob_bdf.png",
        depo_index=i,
    )

Structure:
- plot_depo_gaussian_long_ax: Plots the Gaussian curve for a single depo (or one entry, via `index`, from a multi-depo dict).
- plot_depo_gaussian_sum_long_ax: Plots the summed Gaussian curve for many depos (a track).
- plot_slice_edges_long_ax: Plots slice boundary vertical lines.
- plot_reco_blobs_long_ax: Plots reconstructed blob charge densities (single blob dict or list).
- plot_bdfs_long_ax: Plots true BDF blob charge densities (single blob dict or list).
- plot_longitudinal_charge_distribution: Composite plot for a single depo.
- plot_longitudinal_charge_distribution_track: Composite plot for a track (multiple depos, or one selected depo via `depo_index`).
"""

import numpy as np
import matplotlib.pyplot as plt

from utils.vis.plot_utils import save_and_show

_LONG_XLABEL = r"Drift Time [$\mu$s]"
_LONG_YLABEL = r"Charge Density [e/$\mu$s]"
_LONG_TITLE = "Longitudinal Charge Distribution"


def _finalize_long_ax(ax, title=_LONG_TITLE):
    """Applies the shared axis labels/title/legend once, after all curves are drawn."""
    ax.set_xlabel(_LONG_XLABEL, fontsize=11)
    ax.set_ylabel(_LONG_YLABEL, fontsize=11)
    ax.set_title(title, fontsize=13)
    ax.legend(loc='upper right', fontsize='small')


# ==== For a Point Depo ====
def plot_depo_gaussian_long_ax(ax, depo, v_drift, t_offset_us, index=0, n_sigma=5, set_limit=False, show_labels=True):
    """Plots a longitudinal Gaussian charge distribution for a single depo.

    Args:
        ax: Matplotlib axes object to draw the plot.
        depo: Loaded Depo data dictionary. May hold a single depo (arrays of
            length 1, the default `index=0`) or multiple depos (e.g. a full
            track's depos dict), in which case `index` selects which entry to plot.
        v_drift: Electron drift velocity [mm/us] used to convert distance to time.
        t_offset_us: Global time offset [us] added to the deposition time.
        index: Index of the depo entry to plot within `depo`'s arrays (default 0).
        n_sigma: The range of the plotted Gaussian curve in units of sigma (default is 5).
        set_limit: If True, automatically adjusts the x-axis limits to the calculated n_sigma range.
        show_labels: If True, adds labels, title, and legend to the axes.
    """
    if depo is None:
        print("[ERROR] Fail to load the Depo file.")
        return 0

    total_q = abs(depo['q'][index])
    sigma = depo['L'][index] / v_drift  # [us]
    mean = (depo['t'][index] / 1000.0) + t_offset_us  # [us]

    t_start = mean - n_sigma * sigma
    t_end = mean + n_sigma * sigma
    t_cont = np.linspace(t_start, t_end, 1000)

    y_dens = (total_q / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((t_cont - mean) / sigma) ** 2)

    ax.plot(t_cont, y_dens, color='royalblue', lw=1.0, ls='-',
            label='Depo (Gaussian)', alpha=0.8, zorder=3)
    ax.fill_between(t_cont, y_dens, color='royalblue', alpha=0.1, zorder=2)

    ax.axvline(mean, color='red', linestyle=':', lw=1.5,
               label=f'Peak: {mean:.2f} $\\mu$s', zorder=5)

    if set_limit:
        ax.set_xlim(t_start, t_end)

    if show_labels:
        _finalize_long_ax(ax)

    return 1


def plot_depo_gaussian_sum_long_ax(ax, depos, v_drift, t_offset_us, n_sigma=5, set_limit=False, show_labels=True):
    """Plots the summed longitudinal Gaussian charge density for many depos (a track).

    Vectorizes the calculation by summing the Gaussian distributions of all
    depositions onto a single fine time grid, in memory-efficient chunks.
    This avoids the rendering overhead of drawing one curve per depo.

    Args:
        ax: Matplotlib axes object to draw the plot.
        depos: Deposition data dict containing 't', 'q', and 'L' arrays.
        v_drift: Electron drift velocity [mm/us] used to convert distance to time.
        t_offset_us: Global time offset [us] added to the deposition time.
        n_sigma: The range of the plotted Gaussian curves in units of sigma (default is 5).
        set_limit: If True, automatically adjusts the x-axis limits to the data range.
        show_labels: If True, adds labels, title, and legend to the axes.
    """
    if depos is None:
        print("[ERROR] Fail to load the depos.")
        return 0

    t_arr = depos['t']
    q_arr = depos['q']
    L_arr = depos['L']
    num_depos = len(t_arr)

    means = (t_arr / 1000.0) + t_offset_us  # [us]
    sigmas = L_arr / v_drift  # [us]
    sigmas = np.where(sigmas <= 0, 1e-9, sigmas)
    qs = np.abs(q_arr)

    t_start = np.min(means - n_sigma * sigmas)
    t_end = np.max(means + n_sigma * sigmas)

    steps = 5000
    t_cont = np.linspace(t_start, t_end, steps)
    y_dens = np.zeros(steps)

    chunk_size = 5000
    for start_idx in range(0, num_depos, chunk_size):
        end_idx = min(start_idx + chunk_size, num_depos)
        m = means[start_idx:end_idx, np.newaxis]
        s = sigmas[start_idx:end_idx, np.newaxis]
        q = qs[start_idx:end_idx, np.newaxis]

        diff = (t_cont[np.newaxis, :] - m) / s
        gauss = (q / (s * np.sqrt(2 * np.pi))) * np.exp(-0.5 * diff ** 2)
        y_dens += np.sum(gauss, axis=0)

    ax.plot(t_cont, y_dens, color='royalblue', lw=2.5, ls='--',
            label='Depo (Gaussian Sum)', alpha=0.8, zorder=3)
    ax.fill_between(t_cont, y_dens, color='royalblue', alpha=0.1, zorder=2)

    if set_limit:
        ax.set_xlim(t_start, t_end)

    if show_labels:
        _finalize_long_ax(ax)

    return 1


# ==== For slices Edges ====
def plot_slice_edges_long_ax(ax, binning_obj, set_limit=False, show_labels=True):
    """Plots vertical dotted lines representing bin boundaries on a longitudinal axis.

    Args:
        ax: Matplotlib axes object to draw the plot.
        binning_obj: Binning object (utils.slicer.Binning) containing bin edges.
        set_limit: If True, adjusts the x-axis limits to match the binning range.
        show_labels: If True, adds a label for slice boundaries to the legend.
    """
    if binning_obj is None:
        print("[ERROR] No binning object provided.")
        return 0

    nbins = binning_obj.nbins()
    for i in range(nbins + 1):
        edge_t = binning_obj.edge(i)
        ax.axvline(edge_t, color='black', linestyle=':', lw=2, alpha=0.5, zorder=1)

    if set_limit:
        ax.set_xlim(binning_obj.min(), binning_obj.max())

    if show_labels:
        ax.legend(loc='upper right', fontsize='small')

    return 1


# ==== For Reco Blobs / BlobDepoFills (shared step-density plot) ====
def _plot_blob_charge_long_ax(ax, blobs, color, label, set_limit=False, show_labels=True):
    """Plots a step-wise charge density curve for a list of blob-like nodes.

    Shared by plot_reco_blobs_long_ax and plot_bdfs_long_ax, which only
    differ in color/label.

    Args:
        ax: Matplotlib axes object to draw the plot.
        blobs (dict or list of dict): A single blob (or BDF) node dictionary,
            or a list of them.
        color (str): Matplotlib color for the curve/fill.
        label (str): Legend label for the curve.
        set_limit: If True, automatically adjusts the x-axis limits to the blob range.
        show_labels: If True, adds labels, title, and legend to the axes.
    """
    if not blobs:
        print("[ERROR] No blobs found.")
        return 0

    if isinstance(blobs, dict):
        blobs = [blobs]

    blobs = [b for b in blobs if b.get('val', 0)]
    if not blobs:
        print("[ERROR] No blobs with non-zero charge found.")
        return 0

    min_t = (min(b.get('start', 0) for b in blobs)) / 1000.0  # [us]
    max_t = (max(b.get('start', 0) + b.get('span', 0) for b in blobs)) / 1000.0  # [us]

    steps = 5000
    t_min_plot, t_max_plot = min_t - 2.0, max_t + 2.0
    t_cont = np.linspace(t_min_plot, t_max_plot, steps)
    charge_density_array = np.zeros(steps)

    for b in blobs:
        b_start = b.get('start', 0) / 1000.0
        b_span = b.get('span', 0) / 1000.0
        b_end = b_start + b_span
        val_q = b.get('val', 0)

        d_val = val_q / b_span if b_span > 0 else 0
        mask = (t_cont >= b_start) & (t_cont < b_end)
        charge_density_array[mask] += d_val

    ax.plot(t_cont, charge_density_array, color=color, lw=1.0, drawstyle='steps-post', label=label)
    ax.fill_between(t_cont, charge_density_array, color=color, alpha=0.15, step='post')

    if set_limit:
        ax.set_xlim(t_min_plot, t_max_plot)

    if show_labels:
        _finalize_long_ax(ax)

    return 1


def plot_reco_blobs_long_ax(ax, blobs, set_limit=False, show_labels=True):
    """Plots the longitudinal charge distribution for reconstructed blobs.

    `blobs` may be a single blob node dict or a list of them.
    """
    return _plot_blob_charge_long_ax(ax, blobs, color='darkgreen', label='Reco Charge',
                                      set_limit=set_limit, show_labels=show_labels)


def plot_bdfs_long_ax(ax, bdfs, set_limit=False, show_labels=True):
    """Plots the longitudinal charge distribution for BlobDepoFill (true) blobs.

    `bdfs` may be a single blob node dict or a list of them.
    """
    return _plot_blob_charge_long_ax(ax, bdfs, color='darkorange', label='True Charge',
                                      set_limit=set_limit, show_labels=show_labels)


# ==== Composite plots ====
def _count_items(x):
    """Counts blob/BDF entries in `x`, which may be a single dict, a list, or None."""
    if not x:
        return 0
    if isinstance(x, dict):
        return 1
    return len(x)


def _charge_info_text(total_charge, num_blobs, v_drift, t_offset_us, num_depos=None):
    """Builds the shared info-box text from a total_charge summary dict."""
    q_depo = total_charge.get('depo', 0.0)
    q_in_slices = total_charge.get('depo_in_slices', 0.0)
    q_blob = total_charge.get('blob', 0.0)
    q_bdf = total_charge.get('bdf', 0.0)

    ratio_in_slices = (q_in_slices / q_depo * 100) if q_depo > 0 else 0.0
    ratio_blob = (q_blob / q_depo * 100) if q_depo > 0 else 0.0
    ratio_bdf = (q_bdf / q_depo * 100) if q_depo > 0 else 0.0

    lines = [
        f"Drift Velocity: {v_drift} mm/µs",
        f"Time Offset: {t_offset_us} µs",
    ]
    if num_depos is not None:
        lines.append(f"Num Depos: {num_depos}")
    lines += [
        f"Num Blobs: {num_blobs}",
        f"Total Depo Charge     : {q_depo:.5e} e",
        f"Depo Charge in slices : {q_in_slices:.5e} e ({ratio_in_slices:.1f}%)",
        f"Total Blob Charge     : {q_blob:.5e} e ({ratio_blob:.1f}%)",
        f"Total True Charge     : {q_bdf:.5e} e ({ratio_bdf:.1f}%)",
    ]
    return "\n".join(lines)


def _draw_charge_info_box(ax, info_text):
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    ax.text(0.02, 0.95, info_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', fontfamily='monospace', bbox=props)


def plot_longitudinal_charge_distribution(depo, blobs, bdfs, binning_obj, v_drift, t_offset_us,
                                           total_charge, output_dir, filename, show=True):
    """Composite longitudinal plot for a single depo vs. reco blobs vs. true BDF blobs.

    Args:
        depo: Loaded single-depo data dictionary.
        blobs (dict or list of dict): A single reconstructed blob node
            dictionary, or a list of them.
        bdfs (dict or list of dict): A single true BDF blob node dictionary,
            or a list of them.
        binning_obj: Binning object for drawing slice boundaries.
        v_drift (float): Electron drift velocity [mm/us].
        t_offset_us (float): Global time offset [us].
        total_charge (dict): Summary of total charges for depo, blobs, and bdfs.
        output_dir (str): Directory to save the generated plot into.
        filename (str): Output file name (".png" appended if absent).
        show (bool, optional): If True, displays the plot after saving. Defaults to True.

    Returns:
        str: Full path of the saved plot.
    """
    fig, ax = plt.subplots(figsize=(11, 7))

    # Only the binning range sets the final x-limits: it is the actual
    # analysis window, while the depo Gaussian's n_sigma range is usually
    # much wider and would otherwise dominate the zoom level.
    plot_depo_gaussian_long_ax(ax, depo, v_drift, t_offset_us, n_sigma=10, set_limit=False, show_labels=False)
    plot_reco_blobs_long_ax(ax, blobs, set_limit=False, show_labels=False)
    plot_bdfs_long_ax(ax, bdfs, set_limit=False, show_labels=False)
    plot_slice_edges_long_ax(ax, binning_obj, set_limit=True, show_labels=False)
    _finalize_long_ax(ax)

    info_text = _charge_info_text(total_charge, _count_items(blobs), v_drift, t_offset_us)
    _draw_charge_info_box(ax, info_text)

    return save_and_show(fig, output_dir, filename, show=show)


def plot_longitudinal_charge_distribution_track(depos, blobs, bdfs, binning_obj, v_drift, t_offset_us,
                                                  total_charge, output_dir, filename, show=True,
                                                  depo_index=None):
    """Composite longitudinal plot for a track (multiple depos) vs. reco blobs vs. true BDF blobs.

    By default all depos in `depos` are summed together (unchanged behavior).
    Pass `depo_index` to instead plot a single depo entry from `depos`; the
    `blobs`/`bdfs` arguments already accept a single node dict as well as a
    list (see plot_reco_blobs_long_ax / plot_bdfs_long_ax), so passing e.g.
    `blobs[i]` restricts the blob layer to one instance too. This allows
    plotting/saving either the full multi-object track overlay (default) or
    a single depo/blob/bdf instance, using the same composite function.

    Args:
        depos (dict): Deposition data containing 't', 'q', and 'L' arrays.
        blobs (dict or list of dict): A single reconstructed blob node
            dictionary, or a list of them.
        bdfs (dict or list of dict): A single true BDF blob node dictionary,
            or a list of them.
        binning_obj: Binning object for drawing slice boundaries.
        v_drift (float): Electron drift velocity [mm/us].
        t_offset_us (float): Global time offset [us].
        total_charge (dict): Summary of total charges for depo, blobs, and bdfs.
        output_dir (str): Directory to save the generated plot into.
        filename (str): Output file name (".png" appended if absent).
        show (bool, optional): If True, displays the plot after saving. Defaults to True.
        depo_index (int, optional): If given, plots only this single depo
            entry from `depos` instead of summing all of them. Defaults to None.

    Returns:
        str: Full path of the saved plot, or None if depos is missing.
    """
    if depos is None:
        print("[ERROR] Fail to load the depos.")
        return None

    fig, ax = plt.subplots(figsize=(11, 7))

    # Same reasoning as the single-depo composite: let the binning range
    # own the final x-limits rather than the (typically much wider) depo range.
    if depo_index is None:
        plot_depo_gaussian_sum_long_ax(ax, depos, v_drift, t_offset_us, n_sigma=5, set_limit=False, show_labels=False)
        num_depos = len(depos['t'])
    else:
        plot_depo_gaussian_long_ax(ax, depos, v_drift, t_offset_us, index=depo_index, n_sigma=5,
                                    set_limit=False, show_labels=False)
        num_depos = 1

    plot_reco_blobs_long_ax(ax, blobs, set_limit=False, show_labels=False)
    plot_bdfs_long_ax(ax, bdfs, set_limit=False, show_labels=False)
    plot_slice_edges_long_ax(ax, binning_obj, set_limit=True, show_labels=False)
    _finalize_long_ax(ax)

    info_text = _charge_info_text(total_charge, _count_items(blobs), v_drift, t_offset_us, num_depos=num_depos)
    _draw_charge_info_box(ax, info_text)

    return save_and_show(fig, output_dir, filename, show=show)
