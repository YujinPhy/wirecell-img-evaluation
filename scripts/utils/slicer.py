"""Slicing and Binning Utilities for Wire-Cell Reconstruction.

This module provides data structures and mathematical functions to manage uniform
binning grids and integrate analytical charge distributions (e.g., Gaussian
energy depositions) over individual grid cells.

Structure:
- Binning: Class representing linear, uniform discretization of coordinate spaces,
           supporting coordinate-to-bin conversion and boundary checks.
- Gaussian Utilities: Mathematical functions including PDF, CDF (gcumulative),
                      interval integration (gbounds), and grid-aligned binning
                      (gaussian_bins).
"""

import numpy as np
from scipy.special import erf

class Binning:
    """Manages uniform discretization of a linear space.

    Attributes:
        _nbins (int): Number of bins.
        _minval (float): Minimum value of the binning range.
        _maxval (float): Maximum value of the binning range.
        _binsize (float): Width of a single bin.
    """
    def __init__(self, min_val, max_val, span, reference=0.0):
        """Initializes Binning by aligning min and max boundaries to a reference.

        Args:
            min_val (float): The minimum range of the data.
            max_val (float): The maximum range of the data.
            span (float): The width of a single bin.
            reference (float, optional): The reference grid point from which the bin
                boundaries are aligned. Defaults to 0.0.
        """
        # 1. Calculate how many steps (index) min_val and max_val are from reference
        i_min = int(np.floor((min_val - reference) / span))
        i_max = int(np.ceil((max_val - reference) / span))
        
        # 2. Determine total number of bins
        nbins = i_max - i_min
        
        # 3. Calculate actual min and max aligned to reference
        new_min = reference + i_min * span
        new_max = reference + i_max * span
        
        self.set(nbins, new_min, new_max)

    def set(self, nbins, minval, maxval):
        """Sets the binning parameters directly.

        Args:
            nbins (int): Number of bins.
            minval (float): Minimum value of the range.
            maxval (float): Maximum value of the range.
        """
        self._nbins = nbins
        self._minval = minval
        self._maxval = maxval
        self._binsize = (maxval - minval) / nbins if nbins > 0 else 0.0

    # Attribute accessors (naming maintained similar to C++)
    def nbins(self):
        """Returns the number of bins.

        Returns:
            int: The number of bins.
        """
        return self._nbins

    def min(self):
        """Returns the minimum value of the range.

        Returns:
            float: The minimum value of the range.
        """
        return self._minval

    def max(self):
        """Returns the maximum value of the range.

        Returns:
            float: The maximum value of the range.
        """
        return self._maxval

    def binsize(self):
        """Returns the width of a single bin.

        Returns:
            float: The width of a single bin.
        """
        return self._binsize

    def span(self):
        """Returns the entire span of the binning range.

        Returns:
            float: The total span (max - min).
        """
        return self._maxval - self._minval

    def bin(self, val):
        """Converts a coordinate value to a bin index.

        Args:
            val (float): The coordinate value to convert.

        Returns:
            int: The calculated bin index.
        """
        return int((val - self._minval) / self._binsize)

    def center(self, ind):
        """Returns the center coordinate of a bin index.

        Args:
            ind (int): The bin index.

        Returns:
            float: The center coordinate of the bin.
        """
        return self._minval + (ind + 0.5) * self._binsize

    def edge(self, ind):
        """Returns the boundary coordinate of a bin index.

        Args:
            ind (int): The bin index.

        Returns:
            float: The edge coordinate of the bin.
        """
        return self._minval + ind * self._binsize

    def inside(self, val):
        """Checks if a coordinate value is within the physical range.

        Args:
            val (float): The coordinate value to check.

        Returns:
            bool: True if minval <= val < maxval, False otherwise.
        """
        return self._minval <= val < self._maxval

    def inbounds(self, bin_idx):
        """Checks if a bin index is valid.

        Args:
            bin_idx (int): The bin index to check.

        Returns:
            bool: True if 0 <= bin_idx < nbins, False otherwise.
        """
        return 0 <= bin_idx < self._nbins


def gaussian_pdf(x, mean=0.0, sigma=1.0):
    """Calculates the Gaussian probability density function (PDF).

    Args:
        x (float or numpy.ndarray): Coordinate(s) at which to evaluate the PDF.
        mean (float, optional): Mean of the distribution. Defaults to 0.0.
        sigma (float, optional): Standard deviation of the distribution. Defaults to 1.0.

    Returns:
        float or numpy.ndarray: The evaluated Gaussian PDF value(s). Returns zero if
            sigma is less than or equal to 0.
    """
    if sigma <= 0: return np.zeros_like(x)
    return (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / sigma)**2)


def gcumulative(L, mean=0.0, sigma=1.0):
    """Calculates the Gaussian cumulative distribution function (CDF) P(X <= L).

    Args:
        L (float or numpy.ndarray): Upper limit of integration.
        mean (float, optional): Mean of the distribution. Defaults to 0.0.
        sigma (float, optional): Standard deviation of the distribution. Defaults to 1.0.

    Returns:
        float or numpy.ndarray: The cumulative probability value(s). If sigma is 0,
            returns 1.0 if L >= mean else 0.0.
    """
    if sigma == 0: return 1.0 if L >= mean else 0.0
    scale = np.sqrt(2) * sigma
    return 0.5 + 0.5 * erf((L - mean) / scale)

def gbounds(L1, L2, mean=0.0, sigma=1.0):
    """Calculates the integral of the Gaussian distribution between two limits [L1, L2].

    Args:
        L1 (float or numpy.ndarray): Lower limit.
        L2 (float or numpy.ndarray): Upper limit.
        mean (float, optional): Mean of the distribution. Defaults to 0.0.
        sigma (float, optional): Standard deviation of the distribution. Defaults to 1.0.

    Returns:
        float or numpy.ndarray: The absolute value of the integral between L1 and L2.
    """
    return abs(gcumulative(L2, mean, sigma) - gcumulative(L1, mean, sigma))

def gaussian_bins(binning_obj, mean=0.0, sigma=1.0):
    """Integrates a Gaussian distribution over each bin in a Binning object.

    This corresponds to the WireCell::gaussian template function.

    Args:
        binning_obj (Binning): The Binning object defining the integration grid.
        mean (float, optional): Mean of the distribution. Defaults to 0.0.
        sigma (float, optional): Standard deviation of the distribution. Defaults to 1.0.

    Returns:
        tuple: A tuple containing:
            - bin_values (numpy.ndarray): The integrated probability value for each bin.
            - total_integral (float): The sum of the integrated values over all bins.
    """
    nbins = binning_obj.nbins()
    if nbins <= 0: return np.array([]), 0.0
    
    # Calculate cumulative values at all edges (nbins + 1)
    edges = [binning_obj.edge(i) for i in range(nbins + 1)]
    cumus = [gcumulative(e, mean, sigma) for e in edges]
    
    # Calculate contents of each bin by taking differences of adjacent cumulative values
    bin_values = np.diff(cumus)
    total_integral = np.sum(bin_values)
    
    return bin_values, total_integral
