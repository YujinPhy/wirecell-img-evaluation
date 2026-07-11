"""Deposition Data Inspection and Diagnostic Utilities.

This module provides diagnostic tools to print detailed properties of Wire-Cell
charge depositions (depos), supporting comparison between pre-drift (Gen 1)
and post-drift (Gen 0) states as well as single deposition details.

Structure:
- depos_inspect: Prints comparison stats of pre-drift and post-drift deposition datasets.
- single_depo_inspect: Prints detailed parameters (charge, time, coordinates, sigmas) of a single deposition.
"""

import numpy as np
from scipy.special import erf

from utils.report_format import WIDTH, print_banner, print_rule

def depos_inspect(depos_post, depos_pre):
    """Prints a comparative analysis of pre-drift and post-drift depositions.

    This function prints detailed metrics including container type, key lists,
    data types, total charge, drift time ranges, and spatial bounding boxes for
    both Gen 1 (pre-drift) and Gen 0 (post-drift) datasets.

    Args:
        depos_post (dict): The post-drift (Gen 0) depositions data.
        depos_pre (dict): The pre-drift (Gen 1) depositions data.
    """
    if depos_post is None or depos_pre is None:
        print("[ERROR] One or both generation data (gen 0, gen 1) are missing.")
        return

    count0 = len(depos_post['t'])
    count1 = len(depos_pre['t'])

    if count0 == 0 or count1 == 0:
        print(f"[ERROR] One or both generation datasets are empty (Gen0: {count0}, Gen1: {count1}).")
        return

    total_bytes = sum(arr.nbytes for d in [depos_post, depos_pre]
                      for arr in d.values() if isinstance(arr, np.ndarray))

    print_banner("[ DEPOS INSPECTION (Gen 0 & Gen 1) ]")

    keys_list = list(depos_post.keys())
    print(f"Container Type : {type(depos_post)}")
    print(f"Dict Size      : {len(keys_list)} (Number of keys)")
    print(f"Data Keys      : {keys_list}")

    dtype_pairs = [f"{k}({depos_post[k].dtype})" for k in keys_list]
    chunk_size = 4
    for i in range(0, len(dtype_pairs), chunk_size):
        chunk = dtype_pairs[i:i+chunk_size]
        dtype_info = ", ".join(chunk)
        if i == 0:
            print(f"Data Types     : {dtype_info}")
        else:
            print(f"                 {dtype_info}")
    
    if count0 == count1:
        print(f"# of Depos     : {count0:,} (Gen 0 & 1 Match)")
    else:
        print(f"# of Depos     : MISMATCH (Gen0: {count0:,} | Gen1: {count1:,})")
    print(f"Total Memory   : {total_bytes / (1024**2):.2f} MB (Combined)")
    print_rule()

    # Table Header
    print(f"{'Quantity':<18} | {'Gen 1 (Pre-drift)':<30} | {'Gen 0 (Post-drift)':<30}")
    print_rule()

    # (q) Charge
    q_pre, q_post = np.sum(depos_pre['q']), np.sum(depos_post['q'])
    print(f"{'Total q [e-]':<18} | {abs(q_pre):<30.5e} | {abs(q_post):<30.5e}")

    # (t) Time 
    t_pre_range = f"{np.min(depos_pre['t']):.1f} ~ {np.max(depos_pre['t']):.1f}"
    t_post_range = f"{np.min(depos_post['t']):.1f} ~ {np.max(depos_post['t']):.1f}"
    print(f"{'t Range [ns]':<18} | {t_pre_range:<30} | {t_post_range:<30}")

    # (x, y, z) Position 
    for axis in ['x', 'y', 'z']:
        v_pre, v_post = depos_pre[axis], depos_post[axis]
        pre_stat = f"{np.min(v_pre):.1f} ~ {np.max(v_pre):.1f}" 
        post_stat = f"{np.min(v_post):.1f} ~ {np.max(v_post):.1f}" 
        print(f"{axis + ' [mm]':<18} | {pre_stat:<30} | {post_stat:<30}")
    print_rule()

    # Gaussian Sigma (L, T)
    L_key, T_key = "L", "T"
    if L_key in depos_pre and T_key in depos_pre:
        for label, key in [("L-Sigma (Long.)", L_key), ("T-Sigma (Tran.)", T_key)]:
            v_pre = depos_pre[key]
            v_post = depos_post[key]
            
            range_pre = f"{np.min(v_pre):.4f} ~ {np.max(v_pre):.4f}"
            range_post = f"{np.min(v_post):.4f} ~ {np.max(v_post):.4f}"
            print(f"{label:<18} | {range_pre:<30} | {range_post:<30}")
            
            stat_pre = f"mean: {np.mean(v_pre):.4f}"
            stat_post = f"mean: {np.mean(v_post):.4f}"
            print(f"{'':<18} | {stat_pre:<30} | {stat_post:<30}")

    print_rule(char="=")

def single_depo_inspect(depos, idx, nsigma=3.0):
    """Prints detailed properties of a single deposition at the given index.

    Calculates and prints the total charge, charge within the specified n-sigma
    Gaussian window, coordinates, and longitudinal/transverse widths.

    Args:
        depos (dict): The depositions data dictionary.
        idx (int): The index of the deposition to inspect.
        nsigma (float, optional): Bounding window in units of standard deviation
            for charge fraction estimation. Defaults to 3.0.
    """
    if depos is None:
        print("[ERROR] Depo data (dict) is None.")
        return

    total_size = len(depos.get('t', []))
    if idx < 0 or idx >= total_size:
        print(f"[ERROR] Index {idx} is out of range. (Total size: {total_size})")
        return

    q_total = abs(depos['q'][idx])

    # Charge fraction within +/- nsigma of a 1D Gaussian profile (longitudinal
    # approximation; not a full 3D containment fraction).
    ratio_in_sigma = erf(nsigma / np.sqrt(2))
    q_in_sigma = q_total * ratio_in_sigma

    print_banner(f"[ Single Depo Inspection (Index: {idx}) ]")
    print(f" {'Quantities':<25} | {'Value':<20}")
    print_rule()

    # Charge
    print(f" {'Total Charge (q) [e-]':<25} | {q_total:<10.5e}")
    print(f" {f'Charge in {nsigma}sigma [e-]':<25} | {q_in_sigma:<10.5e} ({ratio_in_sigma*100:.2f}%)")
    print_rule()

    # Time
    print(f" {'Time (t) [ns]':<25} | {depos['t'][idx]:<10.2f}")

    # Position
    pos_str = f"({depos['x'][idx]:.2f}, {depos['y'][idx]:.2f}, {depos['z'][idx]:.2f})"
    print(f" {'(x,y,z) [mm]':<25} | {pos_str:<20}")

    # Sigma (safe lookup: falls back to 0.0 rather than risking an
    # IndexError when only the alternate key name is present)
    def _sigma_at(depos, keys, idx):
        for key in keys:
            if key in depos:
                return depos[key][idx]
        return 0.0

    L_val = _sigma_at(depos, ('L', 'sL'), idx)
    T_val = _sigma_at(depos, ('T', 'sT'), idx)
    print(f" {'Long. Sigma (L) [mm]':<25} | {L_val:<10.4f}")
    print(f" {'Tran. Sigma (T) [mm]':<25} | {T_val:<10.4f}")

    # Status
    status = "Post-drift 3D Gaussian" if (L_val > 0 or T_val > 0) else "Pre-drift Point-like"
    print(f" {'Status':<25} | {status}")
    print_rule(char="=")