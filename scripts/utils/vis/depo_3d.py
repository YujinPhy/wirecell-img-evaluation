"""3D Gaussian Deposition Visualization Utilities.

This module provides functions to render a single deposition's Gaussian
charge cloud as a 3D ellipsoid, either in pure spatial coordinates or with
the longitudinal axis converted to drift time.

Structure:
- depo_gaussian_3d: Renders a depo's 1/3-sigma ellipsoid in (Z, X, Y) space.
- depo_gaussian_3d_time: Renders a depo's 1/3-sigma ellipsoid in (Z, Time, Y) space.
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (registers the '3d' projection)
from matplotlib.lines import Line2D

from utils.vis.plot_utils import save_and_show

_SIGMA_LEGEND_ELEMENTS = [
    Line2D([0], [0], marker='o', color='w', label=r'1-$\sigma$ Core',
           markerfacecolor='crimson', markersize=12, alpha=0.6),
    Line2D([0], [0], marker='o', color='w', label=r'3-$\sigma$ Boundary',
           markerfacecolor='royalblue', markersize=15, alpha=0.2),
]


def _ellipsoid_mesh(center, sigmas, n_sigma, mesh_res=60):
    """Builds a parametric ellipsoid surface mesh.

    Args:
        center (sequence of float): (axis0, axis1, axis2) center coordinates.
        sigmas (sequence of float): (axis0, axis1, axis2) sigma widths.
        n_sigma (float): Ellipsoid radius in units of sigma.
        mesh_res (int, optional): Angular mesh resolution. Defaults to 60.

    Returns:
        tuple of numpy.ndarray: (axis0, axis1, axis2) surface coordinate grids,
            in the same axis order as `center`/`sigmas`.
    """
    u = np.linspace(0, 2 * np.pi, mesh_res)
    v = np.linspace(0, np.pi, mesh_res)
    e0 = n_sigma * sigmas[0] * np.outer(np.cos(u), np.sin(v)) + center[0]
    e1 = n_sigma * sigmas[1] * np.outer(np.sin(u), np.sin(v)) + center[1]
    e2 = n_sigma * sigmas[2] * np.outer(np.ones(np.size(u)), np.cos(v)) + center[2]
    return e0, e1, e2


def _finalize_3d_ax(ax, xlabel, ylabel, zlabel, xlim, ylim, zlim, info_text):
    """Applies the shared axis labels/limits/legend/info-box for the 3D depo plots."""
    ax.set_xlabel(xlabel, labelpad=12)
    ax.set_ylabel(ylabel, labelpad=12)
    ax.set_zlabel(zlabel, labelpad=12)

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_zlim(*zlim)

    # All three axis ranges are equal width, so a 1:1:1 box aspect keeps the
    # ellipsoid from looking stretched.
    ax.set_box_aspect([1, 1, 1])
    ax.view_init(elev=25, azim=135)

    ax.legend(handles=_SIGMA_LEGEND_ELEMENTS, loc='upper right')
    ax.text2D(0.02, 0.95, info_text, transform=ax.transAxes,
              bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))


def depo_gaussian_3d(depos, index, half_range, output_dir, filename, show=True):
    """Renders a single depo's Gaussian charge cloud as a 3D ellipsoid in spatial coordinates.

    Plot axes are permuted from the physical (X, Y, Z) = (longitudinal,
    vertical, beam) frame to (Z, X, Y) so the beam direction reads left-right.

    Args:
        depos (dict): Deposition data dictionary (needs 'q', 'x', 'y', 'z', and
            'L'/'sL', 'T'/'sT').
        index (int): Index of the depo to render.
        half_range (float): Half-width [mm] of each axis range around the depo center.
        output_dir (str): Directory to save the generated plot into.
        filename (str): Output file name (".png" appended if absent).
        show (bool, optional): If True, displays the plot after saving. Defaults to True.

    Returns:
        str: Full path of the saved plot, or None if depos is missing.
    """
    if depos is None or 'q' not in depos:
        print("[ERROR] Fail to load the data.")
        return None

    Q = abs(depos['q'][index])
    sL = depos['sL'][index] if 'sL' in depos else depos['L'][index]  # longitudinal (X) sigma [mm]
    sT = depos['sT'][index] if 'sT' in depos else depos['T'][index]  # transverse (Y, Z) sigma [mm]
    cx, cy, cz = depos['x'][index], depos['y'][index], depos['z'][index]

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')

    center = [cx, cy, cz]
    sigmas = [sL, sT, sT]

    for n_sigma, color, alpha in ((3, 'royalblue', 0.12), (1, 'crimson', 0.35)):
        ex, ey, ez = _ellipsoid_mesh(center, sigmas, n_sigma)
        # Plot-axis order: physical Z (beam) on X, physical X (longitudinal) on Y,
        # physical Y (vertical) on Z.
        ax.plot_surface(ez, ex, ey, color=color, alpha=alpha, linewidth=0)

    info_text = (f"Range: Center +/- {half_range:.1f}mm\n"
                 f"Total Q: {Q:.2e} e\n"
                 f"$\\sigma_L$ (X): {sL:.3f} mm\n"
                 f"$\\sigma_T$ (Y,Z): {sT:.3f} mm")

    _finalize_3d_ax(
        ax,
        xlabel="Z (Beam) [mm]", ylabel="X (Longitudinal) [mm]", zlabel="Y (Vertical) [mm]",
        xlim=(cz - half_range, cz + half_range),
        ylim=(cx - half_range, cx + half_range),
        zlim=(cy - half_range, cy + half_range),
        info_text=info_text,
    )

    plt.tight_layout()
    return save_and_show(fig, output_dir, filename, show=show)


def depo_gaussian_3d_time(depos, index, half_range_mm, v_drift, time_offset, output_dir, filename, show=True):
    """Renders a single depo's Gaussian charge cloud as a 3D ellipsoid in (Z, Time, Y) space.

    The longitudinal spread is converted from a spatial sigma to a drift-time
    sigma via v_drift, so the plot directly shows what a readout would see.

    Args:
        depos (dict): Deposition data dictionary (needs 'q', 't', 'y', 'z', and
            'L'/'sL', 'T'/'sT').
        index (int): Index of the depo to render.
        half_range_mm (float): Half-width [mm] of the spatial (Z, Y) axis ranges.
        v_drift (float): Electron drift velocity [mm/us], used to convert the
            longitudinal spatial sigma into a time sigma.
        time_offset (float): Global time offset [us] added to the deposition's center time.
        output_dir (str): Directory to save the generated plot into.
        filename (str): Output file name (".png" appended if absent).
        show (bool, optional): If True, displays the plot after saving. Defaults to True.

    Returns:
        str: Full path of the saved plot, or None if depos is missing.
    """
    if depos is None or 't' not in depos:
        print("[ERROR] Depo data is missing the 't' (time) field.")
        return None

    Q = abs(depos['q'][index])
    sL_mm = depos['sL'][index] if 'sL' in depos else depos['L'][index]
    sT_mm = depos['sT'][index] if 'sT' in depos else depos['T'][index]

    ct_base = depos['t'][index] / 1000  # [us], depo's own center time
    ct_us = ct_base + time_offset  # [us], center time after offset

    cy_mm, cz_mm = depos['y'][index], depos['z'][index]
    st_us = sL_mm / v_drift  # spatial spread converted to a time spread [us]

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')

    center = [cz_mm, ct_us, cy_mm]
    sigmas = [sT_mm, st_us, sT_mm]

    for n_sigma, color, alpha in ((3, 'royalblue', 0.12), (1, 'crimson', 0.35)):
        ez, et, ey = _ellipsoid_mesh(center, sigmas, n_sigma)
        ax.plot_surface(ez, et, ey, color=color, alpha=alpha, linewidth=0)

    half_range_us = half_range_mm / v_drift

    info_text = (f"Data Center 't': {ct_base:.2f} us\n"
                 f"Offset applied: {time_offset} us\n"
                 f"Plot Center: {ct_us:.2f} us\n"
                 f"$\\sigma_t$: {st_us:.3f} us")

    _finalize_3d_ax(
        ax,
        xlabel="Z (Beam) [mm]", ylabel="Time (Drift) [us]", zlabel="Y (Vertical) [mm]",
        xlim=(cz_mm - half_range_mm, cz_mm + half_range_mm),
        ylim=(ct_us - half_range_us, ct_us + half_range_us),
        zlim=(cy_mm - half_range_mm, cy_mm + half_range_mm),
        info_text=info_text,
    )

    plt.tight_layout()
    return save_and_show(fig, output_dir, filename, show=show)
