"""Shared plot save/display helper for the utils.vis package.

Keeps the "add .png suffix, create the output dir, save, optionally
show" sequence in one place instead of duplicated across every
top-level plotting function.
"""

import os

import matplotlib.pyplot as plt


def save_and_show(fig, output_dir, filename, dpi=300, show=True):
    """Saves fig to output_dir/filename and optionally displays it.

    Args:
        fig: Matplotlib Figure to save.
        output_dir (str): Directory to save into. Created if missing.
        filename (str): Output file name; ".png" is appended if absent.
        dpi (int, optional): Resolution for the saved file. Defaults to 300.
        show (bool, optional): If True, calls plt.show() after saving. Either way
            the figure is closed afterward -- leaving it open lets Jupyter's
            inline backend auto-display it again at the end of cell execution
            (on top of the explicit plt.show(), producing a duplicate render),
            and repeated batch calls (e.g. plotting many outlier cases) leak
            open figures until matplotlib's max-open-figure warning fires.
            Defaults to True.

    Returns:
        str: Full path of the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)

    if not filename.lower().endswith('.png'):
        filename = f"{filename}.png"

    full_path = os.path.join(output_dir, filename)
    fig.savefig(full_path, dpi=dpi, bbox_inches='tight')
    print(f"[INFO] Plot saved to {full_path}")

    if show:
        plt.show()
    plt.close(fig)

    return full_path
