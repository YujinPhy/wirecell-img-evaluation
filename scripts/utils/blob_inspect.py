"""Graph and Node Inspection Utilities for Wire-Cell Reconstruction Graphs.

This module provides tools to analyze and inspect the structural and geometric 
details of reconstruction graphs and individual nodes (e.g., Slice, Blob, 
Channel, Wire, Measure).

Structure:
- _get_node_type_info: Helper to summarize node attributes and data types.
- graph_inspect: Main function to analyze and print/return graph information.
- summarize_slices: Prints a structured summary of slice node data.
- summarize_blobs: Prints a geometric and signal summary of blob node data.
- single_blob_inspect: Performs a detailed inspection on a specific blob.
- blobs_charge_analysis: Analyzes and summarizes charge information for blobs.
- blob_corners: Calculates Cartesian coordinate bounds for blobs.
- blob_coord: Extracts raw coordinates along a specific axis.
- blob_centers: Calculates center coordinate along a specific axis.
- summarize_channel: Prints a summary of channel node data.
- summarize_wire: Prints a geometric summary of wire node data.
- summarize_measure: Prints a summary of measure node data.
"""

from collections import Counter
import wirecell.img.clusters as clusters
import textwrap
import numpy as np
from wirecell import units
from wirecell.util.wires.schema import plane_face_apa

from utils.report_format import WIDTH, print_banner, print_rule


def decode_wpid(wpid):
    """Decodes a packed WirePlaneId integer into {plane, face, apa}."""
    plane, face, apa = plane_face_apa(wpid)
    return {'plane': plane, 'face': face, 'apa': apa}


def _get_node_type_info(ndat):
    """Summarizes node attribute keys and their associated types.

    Args:
        ndat (list of dict): List of data dictionaries for nodes of a specific type.

    Returns:
        str: A comma-separated string containing sorted keys and their data types,
            e.g., "code(str), desc(str)".
    """
    if not ndat:
        return "-"

    key_types = {}
    for data_dict in ndat:
        for k, v in data_dict.items():
            tname = type(v).__name__
            if k not in key_types:
                key_types[k] = set()
            key_types[k].add(tname)
    
    def custom_sort_key(item):
        key = item[0]
        if key == 'code':
            return (0, key)
        elif key == 'desc':
            return (1, key)
        else:
            return (2, key)

    sorted_keys = sorted(key_types.items(), key=custom_sort_key)
    parts = [f"{k}({'/'.join(sorted(ts))})" for k, ts in sorted_keys]
    return ", ".join(parts)

def graph_inspect(gr):
    """Analyzes and prints/returns key structural details of a reconstruction graph.

    This function counts nodes by their type (e.g., Blob, Wire, Channel, Slice, Measure),
    extracts node data formats, summarizes edge types, prints the report to the console,
    and returns the formatted report string.

    Args:
        gr (networkx.Graph): The Wire-Cell reconstruction cluster graph to analyze.

    Returns:
        str: The multi-line formatted report string summarizing the graph details.
    """
    # Create a list to accumulate output strings
    output = []
    
    output.append("")  # Blank line for spacing
    output.append("=" * WIDTH)
    output.append(f"{'[ Graph INSPECTION ]':^{WIDTH}}")
    output.append("=" * WIDTH)
    
    node_names = { 'b': 'Blob', 'w': 'Wire', 'c': 'Channel', 's': 'Slice', 'm': 'Measure'}
    total_nodes = gr.number_of_nodes()
    total_edges = gr.number_of_edges()

    output.append(f"Total number of Nodes : {total_nodes}")
    output.append(f"Total number of Edges : {total_edges}")

    node_counter = Counter(dict(gr.nodes(data='code')).values())
    cm = clusters.ClusterMap(gr)

    # 1. Node Summary
    output.append(f"\nNode Composition & Data Formats:")
    header = f"{'Type Name':<14} | {'Code':<6} | {'Count':<8} | {'Data Formats (Keys: Types)'}"
    output.append(header)
    output.append("-" * WIDTH)

    for code, count in sorted(node_counter.items()):
        name = node_names.get(code, 'Unknown')
        ndat = cm.data_oftype(code)
        type_info = _get_node_type_info(ndat)
        
        wrapped_lines = textwrap.wrap(type_info, width=47)
        if not wrapped_lines:
            wrapped_lines = ["-"]
            
        output.append(f"{name:<14} | {code:<6} | {count:<8} | {wrapped_lines[0]}")
        for extra_line in wrapped_lines[1:]:
            output.append(f"{'':<14} | {'':<6} | {'':<8} | {extra_line}")
        output.append("-" * WIDTH)

    # 2. Edge Summary
    output.append(f"\nEdge Composition & (Type-to-Type):")
    edge_list = []
    for u, v in gr.edges():
        codes = sorted([gr.nodes[u].get('code', '?'), gr.nodes[v].get('code', '?')])
        edge_list.append(f"{codes[0]}-{codes[1]}")
    
    edge_counter = Counter(edge_list)
    
    for e_pair, count in sorted(edge_counter.items()):
        c1, c2 = e_pair.split('-')
        n1, n2 = node_names.get(c1, 'Unk'), node_names.get(c2, 'Unk')
        edge_info = f"    {e_pair} ({n1} <-> {n2})"
        output.append(f"{edge_info:<35} : {count} edges")

    output.append("=" * WIDTH)

    report = "\n".join(output)
    print(report)
    return report

# ==== For Slice node ====
def summarize_slices(slices):
    """Prints a structured summary of the provided slice data.

    This function generates a tabular summary of slice metadata including 
    description, frame ID, identity, start time, span, and charge signal 
    information. It also prints detailed channel-by-channel signal lists.

    Args:
        slices (list of dict): List of dictionaries containing slice node data.
    """
    if not slices:
        print("No slice data found.")
        return

    print_banner(f"[ Slice Summary ({len(slices)} slices) ]")

    # Summary table header
    # desc, frameid, ident, start, span, signal_info
    header = f"{'Desc':<6} | {'Frame ID':<9} | {'Ident':<8} | {'Start (ns)':<12} | {'Span (ns)':<9} | {'Channel #':<12} | {'Total Val':<10}"
    print(header)
    print("-" * len(header))

    for s in slices:
        desc = s.get('desc', -1)
        fid = s.get('frameid', -1)
        ident = s.get('ident', -1)
        start = s.get('start', 0.0)
        span = s.get('span', 0.0)
        sig_list = s.get('signal', [])
        
        num_chans = len(sig_list)
        total_val = sum(item.get('val', 0.0) for item in sig_list)

        # Print summary line
        print(f"{desc:<6} | {fid:<9} | {ident:<8} | {start:<12.1f} | {span:<9.1f} | {num_chans:<12} | {total_val:<10.1f}")

    print("-" * len(header))

    # Print detailed signal data
    print("\n>>> Full Signal List (Channel-by-Channel):")
    for i, s in enumerate(slices):
        start_time = s.get('start', 0.0)
        sig_list = s.get('signal', [])
        
        print(f"\n[Slice {i} | Start: {start_time} ns]")
        if not sig_list:
            print("    (No signals in this slice)")
            continue
            
        # Print in chunks of 3 for better formatting as data can be large
        print(f"    Signals: ", end="")
        for j, sig in enumerate(sig_list):
            # Format channel info as ID(val) to keep it concise
            sig_str = f"ID:{sig['ident']}(v:{sig['val']:.0f})"
            print(f"{sig_str:<18}", end="")
            
            # Print 3 channels per line and wrap
            if (j + 1) % 3 == 0 and j != len(sig_list) - 1:
                print(f"\n{' '*13}", end="")
        print() # New line after slice ends

    print(f"\n{'='*WIDTH}")

# ==== For Blob node ====
def summarize_blobs(blobs):
    """Prints a geometric and signal summary of the given blob data.

    This function decodes each blob's face ID to APA-Face format, prints 
    a tabular overview of slice identity, charge value, start time, and span,
    and displays detailed wire bounds and coordinate corners.

    Args:
        blobs (list of dict): List of dictionaries representing blob node data.
    """
    if not blobs:
        print("No blob data found.")
        return

    print_banner(f"[ BLOB DATA SUMMARY ({len(blobs)} nodes) ]")

    # 1. Main summary table (focused on metrics and IDs)
    # desc, ident, sliceid, faceid(APA-F), val, unc, start, span
    header = f"{'Desc':<5} | {'Ident':<6} | {'S-ID':<6} | {'APA-F':<8} | {'Value':<10} | {'Unc':<8} | {'Start':<10} | {'Span':<6}"
    print(header)
    print("-" * len(header))

    for b in blobs:
        decoded = decode_wpid(b.get('faceid', -1))
        apa_f = f"A{decoded['apa']}-F{decoded['face']}"
        
        print(f"{b.get('desc', -1):<5} | "
              f"{b.get('ident', -1):<6} | "
              f"{b.get('sliceid', -1):<6} | "
              f"{apa_f:<8} | "
              f"{b.get('val', 0.0):<10.1f} | "
              f"{b.get('unc', 0.0):<8.1f} | "
              f"{b.get('start', 0.0):<10.1f} | "
              f"{b.get('span', 0.0):<6.1f}")

    print("-" * len(header))

    print("\n>>> Detailed Geometry (Wire Bounds & Crossing Points):")
    for i, b in enumerate(blobs):
        ident = b.get('ident', -1)
        bounds = b.get('bounds', [])
        corners = b.get('corners', [])
        
        print(f"\n[Blob {i} | Ident: {ident}]")
        
        if bounds:
            b_elements = []
            for j, rng in enumerate(bounds):
                beg = rng.get('beg', 'N/A')
                end = rng.get('end', 'N/A')
                b_elements.append(f" ({beg}-{end})")

            print(f" Bounds -> {' | '.join(b_elements)}")
        
        if corners:
            c_elements = []
            for j, cor in enumerate(corners):
                c_elements.append(f" ({cor[0]:.1f}nm, {cor[1]:.1f}mm, {cor[2]:.1f}mm)")
            print(f" Corners ({len(corners)}) -> {' | '.join(c_elements)}")

    print(f"\n{'='*WIDTH}")

def single_blob_inspect(blobs, blob_idx):
    """Performs a detailed inspection on a specific blob by index.

    Extracts and formats identity, charge signal, time dimension, and raw
    spatial coordinate ranges (X, Y, Z) for the selected blob.

    Args:
        blobs (list of dict): List of dictionaries representing blob node data.
        blob_idx (int): The index of the blob to inspect within the list.
    """
    blob = blobs[blob_idx] if 0 <= blob_idx < len(blobs) else None

    if blob is None:
        print("[ERROR] Blob data is None.")
        return

    print_banner(f"[ BLOB INSPECTION (blob idx={blob_idx}) ]")

    # 1. Identification
    print(f"--- [ Identification & Signal ] ---")
    print(f"Slice ID  : {blob.get('sliceid', 'N/A')}")
    print(f"Face ID   : {blob.get('faceid', 'N/A')}")
    print(f"Value (q) : {blob.get('val', 0):.2e}")
    print(f"Unc       : {blob.get('unc', 0):.2e}")

    # 2. Time information
    print(f"\n--- [ Dimension (Time Domain) ] ---")
    print(f"Start Time: {blob.get('start', 0):10.2f} [ns]")
    print(f"Thickness : {blob.get('span', 0):10.2f} [ns]")

    # 3. Extract coordinate data safely
    corners = blob.get('corners')
    if corners is None or len(corners) == 0:
        print("\n[WARNING] No corner data found in this blob.")
    else:
        c_raw = np.array(corners)

        print(f"\n--- [ Coordinate Range ] ---")
        print(f"{'Axis':<12} | {'Raw Min':>10} ~ {'Raw Max':>10} | {'Unit'}")
        print_rule()
        
        axes_names = ['X (Drift)', 'Y', 'Z']
        for i, name in enumerate(axes_names):
            raw_min, raw_max = np.min(c_raw[:, i]), np.max(c_raw[:, i])
            unit = "[ns]" if i == 0 else "[mm]"
            print(f"{name:<12} | {raw_min:10.1f} ~ {raw_max:10.1f} | {unit}")

        print(f"\n--- [ All Corners List (Total: {len(c_raw)}) ] ---")
        for i, r in enumerate(c_raw):
            print(f"Corner [{i:02d}] : ({r[0]:9.1f}, {r[1]:7.1f}, {r[2]:7.1f}) [ns, mm, mm]")
    print("="*WIDTH + "\n")

def blobs_charge_analysis(blobs, charge_threshold=0.0, print_list=True):
    """Analyzes and summarizes charge information for a list of blobs.

    Categorizes blobs into valid and noise/ghost categories based on a charge 
    threshold, prints detailed statistics, and reports total valid charge.

    Args:
        blobs (list of dict): List of dictionaries representing blob node data.
        charge_threshold (float, optional): The charge value threshold. Defaults to 0.0.
        print_list (bool, optional): Whether to print detailed lists of blobs. Defaults to True.
    """
    if not blobs:
        print("[ERROR] No blobs found.")
        return

    valid_blobs = [b for b in blobs if b.get('val', 0) > charge_threshold]
    noise_blobs = [b for b in blobs if b.get('val', 0) <= charge_threshold]
    
    total_q = sum(b.get('val', 0) for b in valid_blobs)

    # --- [Detailed List Output] Only run if print_list is True ---
    if print_list:
        # 1. Print Valid Blobs
        print(f"\n### [ Valid Blobs (Charge > {charge_threshold:.1e} [e-]) ] ###")
        print(f"{'Idx':<4} | {'SliceID':<7} | {'Start [ns]':<10} | {'Span [ns]':<8} | {'Charge [e-]':<12} | {'Ratio [%]'}")
        print_rule()

        if not valid_blobs:
            print(f"No blobs found above the threshold ({charge_threshold:.1e}).")
        else:
            for i, b in enumerate(valid_blobs):
                sid = b.get('sliceid', 'N/A')
                start = b.get('start', 0)
                span = b.get('span', 0)
                q_val = b.get('val', 0)
                ratio = (q_val / total_q * 100) if total_q > 0 else 0
                print(f"{i:<4} | {sid:>7} | {start:10.2f} | {span:8.2f} | {q_val:12.6e} | {ratio:9.2f}%")

        # 2. Print Noise/Ghost Blobs
        if noise_blobs:
            print(f"\n### [ Sub-threshold Blobs (<= {charge_threshold:.1e}) ] ###")
            print(f"{'Idx':<4} | {'SliceID':<7} | {'Start [ns]':<10} | {'Span [ns]':<8} | {'Charge [e-]'}")
            print_rule()
            for i, b in enumerate(noise_blobs):
                sid = b.get('sliceid', 'N/A')
                start = b.get('start', 0)
                span = b.get('span', 0)
                q_val = b.get('val', 0)
                print(f"{i:<4} | {sid:>7} | {start:10.2f} | {span:8.2f} | {q_val:12.2e}")

    # --- [Summary Section] Always printed regardless of print_list ---
    print(("\n" + "="*WIDTH) if not print_list else ("-" * WIDTH))
    print(f"Summary (Threshold: {charge_threshold:.2e}):")
    print(f"  - Total Blobs: {len(blobs)}")
    print(f"  - Valid (> Thr): {len(valid_blobs)}")
    print(f"  - Invalid (<= Thr): {len(noise_blobs)}")
    print(f"  - Total Sum of Valid Charges : {total_q:.3e} [e-]")
    print("="*WIDTH + "\n")

def blob_corners(blobs):
    """Calculates spatial Cartesian min/max coordinate bounds for each blob.

    Args:
        blobs (list of dict): List of dictionaries representing blob node data.

    Returns:
        numpy.ndarray: A 3D numpy array of shape (3, 2, Nblobs) containing 
            coordinate min/span values.
    """
    spans = set()

    mm = np.zeros((3,2, len(blobs)))
    for ind, b in enumerate(blobs):
        c = np.array(b['corners'])
        span = b['span']
        spans.add(span)
        for axis in [0,1,2]:
            cmin = np.min(c[:,axis])
            mm[axis][0][ind] = cmin
            if axis:
                mm[axis][1][ind] = np.max(c[:,axis]) - cmin
            else:
                mm[axis][1][ind] = span

    spans = [s/units.cm for s in spans]
    print(f'spans: {spans} cm')
    return mm

def blob_coord(blobs, axis=0):
    """Extracts raw coordinates along a specific spatial axis for all blobs.

    Args:
        blobs (list of dict): List of dictionaries representing blob node data.
        axis (int, optional): The target axis index (0: X, 1: Y, 2: Z). Defaults to 0.

    Returns:
        numpy.ndarray: An array of coordinate values for the selected axis.
    """
    ret = list()
    for b in blobs:
        ret.append(b['corners'][0][axis])
    return np.array(ret)

def blob_centers(blobs, index=2):
    """Calculates the center coordinate along a specific axis for each blob.

    Args:
        blobs (list of dict): List of dictionaries representing blob node data.
        index (int, optional): The target axis index. Defaults to 2.

    Returns:
        numpy.ndarray: An array of calculated center coordinates.
    """
    ret = list()
    for b in blobs:
        c = 0
        corners = b['corners']
        for corner in corners:
            c += corner[index]
        cen = c/len(corners)
        ret.append(cen)
    return np.array(ret)

def summarize_channel(channels):
    """Prints a structured summary of the channel node data.

    Args:
        channels (list of dict): List of dictionaries representing channel node data.
    """
    if not channels:
        print("No channel data found.")
        return

    # Extract data
    idents = [c.get('ident', -1) for c in channels]
    indices = [c.get('index', -1) for c in channels]
    wpids = [c.get('wpid', -1) for c in channels]
    descs = [c.get('desc', -1) for c in channels]

    print(f"\n=== Channel Summary ({len(channels)} channels) ===")
    
    # Print unique values and ranges
    print(f"Ident (Global ID) : {min(idents)} ~ {max(idents)} (Range)")
    print(f"Index (Row/Seq)   : {min(indices)} ~ {max(indices)} (Range)")
    print(f"Unique WPIDs      : {sorted(list(set(wpids)))}")
    print(f"Unique Descs      : {sorted(list(set(descs)))}")
    
    # Print one sample channel node in detail to verify key name matching
    if len(channels) > 0:
        print(f"\nSample Channel Node: {channels[0]}")
    
    print("-" * 50)

def summarize_wire(wires):
    """Prints a geometric summary of the wire node data.

    Args:
        wires (list of dict): List of dictionaries representing wire node data.
    """
    if not wires:
        print("No wire data found.")
        return

    # 1. Extract integer IDs and index information
    wips = [w.get('wpid', -1) for w in wires]
    segments = [w.get('seg', -1) for w in wires]
    channels = [w.get('chid', -1) for w in wires]
    descs = [w.get('desc') for w in wires]
    ident = [w.get('ident', -1) for w in wires]
    indexs = [w.get('index', -1) for w in wires]

    # 2. Extract coordinate information (Tail & Head)
    tails = [w.get('tail', 0) for w in wires]
    heads = [w.get('head', 0) for w in wires]

    print(f"\n=== Wire Geometric Summary ({len(wires)} wires) ===")
    col_num = 10
    # Print basic ID information (first 10 items as examples)
    print(f"Indexs       : {indexs[:col_num]}") 
    print(f"Channel IDs  : {channels[:col_num]}")
    print(f"WIP Indices  : {wips[:]} ...")
    print(f"Segments     : {segments[:col_num]}")
    descs = [w.get('desc') for w in wires]
    print(f"Unique Desc values: {set(descs)}")
    if len(wires) > 0:
        # Tail coordinate range
        print(tails)
        print(heads)
    
    print("-" * 40)

def summarize_measure(measures):
    """Prints a summary of the measure node data.

    Args:
        measures (list of dict): List of dictionaries representing measure node data.
    """
    if not measures:
        print("No measure data found.")
        return
    
    # 1. Extract integer IDs and index information
    wips = [w.get('wpid', -1) for w in measures]