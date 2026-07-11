"""Data Loading Utilities for Wire-Cell 3D Image/Clustering Reconstruction and Visualization.

This module provides functions to load, filter, and transform different types of
data used in Wire-Cell reconstruction and image evaluation, specifically:
1. Deposition data (e.g., loaded from depos files).
2. Cluster graph data (e.g., loaded using wirecell.img.tap).

Structure:
- Depos loading functions (e.g., load_generation_data).
- Cluster graph loading and node filtering (e.g., load_cluster_data, load_graph_nodes).
"""

import bz2
import json

import numpy as np
import wirecell.img.tap as tap
import wirecell.gen.depos as deposmod
from wirecell import units
from collections import Counter

# ==== Depos ====
def load_generation_data(depo_file, gen_index):
    """Loads deposition data for a specific generation index from a stream.

    Args:
        depo_file (str): Path to the deposition file.
        gen_index (int): Generation index to load.

    Returns:
        dict or numpy.ndarray: The deposition data for the given generation,
            or None if no data is found or an exception occurs.
    """
    try:
        return next(deposmod.stream(depo_file, generation=gen_index))
    except StopIteration:
        # No data for this generation
        return None
    except Exception as e:
        print(f"Error loading Gen {gen_index}: {e}")
        return None

# ==== Cluster Graphs ====
def load_cluster_data(cluster_file, event_index=0):
    """Loads a cluster graph for a specific event index from a tap cluster file.

    Args:
        cluster_file (str): Path to the cluster graph file.
        event_index (int, optional): Index of the event (graph) to load. Defaults to 0.

    Returns:
        networkx.Graph: The loaded cluster graph object, or None if the file is
            empty, the index is out of range, or an exception occurs.
    """
    # print(f"\nLoading clusters from {cluster_file}...")
    try:
        all_clusters = list(tap.load(cluster_file)) # tap.load yields a sequence of graphs (events)
        
        if not all_clusters:
            print(f"Error: Cluster file '{cluster_file}' is empty.")
            return None
        
        # Check if the requested event index exists
        if event_index >= len(all_clusters):
            print(f"Error: Event index {event_index} out of range (Total events: {len(all_clusters)})")
            return None
            
        cgraph = all_clusters[event_index]
        # print(f"Successfully loaded event {event_index} with {cgraph.number_of_nodes()} nodes.")
        return cgraph

    except Exception as e:
        print(f"Failed to load cluster data: {e}")
        return None

def load_graph_nodes(cgraph, type_code, filter_func = lambda n : True):
    """Retrieves and filters nodes of a specific type from a cluster graph.

    Args:
        cgraph (networkx.Graph): The cluster graph to query.
        type_code (str): The node type code to match (e.g., 'b' for blobs).
        filter_func (callable, optional): A function that takes a node data dictionary
            and returns a boolean (True to keep, False to exclude). Defaults to a
            function that always returns True.

    Returns:
        list: A list of dictionaries, where each dictionary contains the attributes
            of a matching node.
    """
    ret = list()
    for node, ndata in cgraph.nodes.data():
        if ndata.get('code') == type_code and filter_func(ndata):
            ret.append(ndata)
    return ret

