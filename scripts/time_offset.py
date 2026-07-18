"""Analytic and empirical calibration of the BlobDepoFill time offset.

Summary: `Img::BlobDepoFill` (wire-cell-toolkit/img/src/BlobDepoFill.cxx)
matches a depo's truth time to a reconstructed blob's time slice via a
single additive constant, `time_offset`, that the toolkit does not compute
for the caller. This module provides:
1. `analytic_time_offset`: the exactly-computable part of that constant,
   derived from the same DAQ/response-plane/drift-speed parameters already
   used to run the simulation (see `docs/time_offset_calibration.md`).
2. `overlap_coefficient` / `scan_residual`: a narrow empirical scan, centered
   on that analytic baseline, that measures the small residual left over
   from signal-processing deconvolution effects the analytic formula does
   not capture.

All time/length quantities in this module use this codebase's usual
system-of-units convention (`from wirecell import units`, e.g. `-250.0 *
units.us`), matching `depo['t']` and reco blob `start`/`span` values as
loaded by `utils.load` -- never bare microsecond/millimeter floats.

Usage:
    import sys
    sys.path.insert(0, "scripts")
    from wirecell import units
    from utils.time_offset import analytic_time_offset, scan_residual

    baseline = analytic_time_offset(
        tick0_time=-250.0 * units.us,
        response_plane=100.0 * units.mm,
        drift_speed=1.6 * units.mm / units.us,
    )
    best_offset, curve = scan_residual(
        depo_t=depos["t"][0], depo_tsigma=depos["L"][0] / speed,
        reco_blobs=reco_blobs, baseline_offset=baseline,
    )
"""

import numpy as np

from utils.slicer import gbounds


def analytic_time_offset(tick0_time, response_plane, drift_speed):
    """Computes the exactly-derivable part of the BlobDepoFill time offset.

    This is `abs(tick0_time) + response_plane / drift_speed`: the DAQ/G4-clock
    convention fixing what absolute time output tick 0 corresponds to
    (`tick0_time`), plus the drift transit time from the response plane to
    the collection wires. Both quantities are read directly from the same
    jsonnet params used to run the simulation (e.g.
    `wire-cell-toolkit/cfg/pgrapher/experiment/pdhd/params.jsonnet`), not fit
    from data. See `docs/time_offset_calibration.md` for the full derivation
    and why a residual on top of this value is still expected.

    Args:
        tick0_time (float): The absolute (G4) time corresponding to output
            tick 0 (PDHD: `-250.0 * units.us`).
        response_plane (float): Distance from the response plane to the
            collection wires (PDHD: `100.0 * units.mm`).
        drift_speed (float): Nominal drift speed (PDHD: `1.6 * units.mm /
            units.us`).

    Returns:
        float: The analytic baseline offset, in the same system-of-units
            convention as the inputs.
    """
    return abs(tick0_time) + response_plane / drift_speed


def overlap_coefficient(depo_t, depo_tsigma, reco_blobs, offset):
    """Computes the overlap coefficient between a depo's time-domain Gaussian
    model and the charge distribution across a set of reco blobs' own time slices.

    The depo is modeled as a Gaussian in arrival time, mean `depo_t +
    offset` and sigma `depo_tsigma` (matching the `extent_long / speed`
    convention used throughout `utils.true_blob`). Each reco blob's own
    `[start, start + span)` window is used directly as one bin of a discrete
    probability distribution over time (`val` normalized by the total charge
    across `reco_blobs`), rather than re-binning into an arbitrary fixed
    width: this is a tighter version of the same "overlap coefficient"
    (histogram intersection) metric used by the prior `scripts/timeoffset/`
    study, computed exactly via `gbounds` instead of by numerically
    integrating a point-wise minimum of two continuous curves.

    Args:
        depo_t (float): Depo truth time.
        depo_tsigma (float): Depo time-domain diffusion sigma (`extent_long
            / speed`).
        reco_blobs (list[dict]): Reco blob nodes, as returned by
            `utils.load.load_graph_nodes(cgraph, 'b')`. Each must carry
            `start`, `span`, `val`.
        offset (float): Candidate `time_offset` value to test.

    Returns:
        float: Overlap coefficient in [0, 1]; 1.0 means the depo's Gaussian
            time model and the reco charge distribution assign identical
            fractions to every reco time slice.
    """
    total_val = sum(b["val"] for b in reco_blobs)
    if total_val <= 0 or depo_tsigma <= 0:
        return 0.0

    mu = depo_t + offset
    overlap = 0.0
    for b in reco_blobs:
        t0, t1 = b["start"], b["start"] + b["span"]
        true_frac = gbounds(t0, t1, mu, depo_tsigma)
        reco_frac = b["val"] / total_val
        overlap += min(true_frac, reco_frac)
    return overlap


def scan_residual(depo_t, depo_tsigma, reco_blobs, baseline_offset,
                   window=None, step=None):
    """Scans a narrow window of candidate offsets around an analytic baseline.

    Unlike the prior `scripts/timeoffset/` study's blind wide sweeps (tens of
    microseconds), this scans only `+/- window` around `baseline_offset`,
    since the analytic part of the offset is already known and only a small
    signal-processing residual remains to be measured (see
    `docs/time_offset_calibration.md`).

    Args:
        depo_t (float): Depo truth time.
        depo_tsigma (float): Depo time-domain diffusion sigma.
        reco_blobs (list[dict]): Reco blob nodes; see `overlap_coefficient`.
        baseline_offset (float): Analytic baseline, as returned by
            `analytic_time_offset`, to scan around.
        window (float, optional): Half-width of the scan window. Defaults to
            `10.0 * units.us` if not given.
        step (float, optional): Scan step size. Defaults to `0.05 *
            units.us` if not given.

    Returns:
        tuple: (best_offset, curve) where `best_offset` is the offset
            maximizing the overlap coefficient, and `curve` is a list of
            (offset, overlap_coefficient) pairs spanning the scanned window.
    """
    from wirecell import units
    if window is None:
        window = 10.0 * units.us
    if step is None:
        step = 0.05 * units.us

    offsets = np.arange(baseline_offset - window, baseline_offset + window + step, step)
    scores = np.array([
        overlap_coefficient(depo_t, depo_tsigma, reco_blobs, offset)
        for offset in offsets
    ])
    best_offset = float(offsets[int(np.argmax(scores))])
    curve = list(zip(offsets.tolist(), scores.tolist()))
    return best_offset, curve
