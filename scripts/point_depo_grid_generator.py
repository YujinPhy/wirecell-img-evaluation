#!/usr/bin/env python
"""Generates a 3D grid of point-depo positions for `wct-sim-nf-sp-img-bdf-grid.jsonnet`.

Replaces running `wire-cell` once per point depo (see `sh_scripts/run_single_point.sh`)
with a single grid of points fed into one job via `sim.tracks()`. Each grid
point becomes one short point-like track (see the jsonnet's `len`/`step`
args), so points must be spaced far enough apart (in the pitch plane `y,z`
and in drift `x`) that their reco blobs do not merge; the spacing is left to
the caller to tune (`--dx`/`--dy`/`--dz`), typically by inspecting the
resulting Bee view or plots and adjusting. As an alternative to separating
points spatially, `--time-step` separates them in time instead (see below).

Usage:
    python point_depo_grid_generator.py \\
        --bounds X_MIN X_MAX Y_MIN Y_MAX Z_MIN Z_MAX \\
        [--bounds X_MIN X_MAX Y_MIN Y_MAX Z_MIN Z_MAX ...] \\
        --dx 10 --dy 5 --dz 5 \\
        --charge -50000 --time 0 --time-step 0 \\
        -o grid_points.json

`--bounds` (mm) may be repeated once per anode/volume to cover several
sensitive volumes in one grid; all points are concatenated into a single
output list. `--dx` is the drift-direction (x) spacing and `--dy`/`--dz` are
the pitch-plane (y, z) spacing, also in mm.

`--time-step` (us) assigns each point a distinct depo time, spaced by this
amount, ordered by x descending: the point with the largest x (closest to the
anode for anode 1/face 1, see docs/geometry/wirecell_sensitive_volume.md SS4)
gets `--time`, and each smaller-x point gets `time + rank*time_step`. This
matches drift physics (larger x = shorter drift = earlier arrival) instead of
fighting it. Default `time_step=0` keeps the old behavior (all points at
`--time`). Widening the time spread this way requires a correspondingly
larger `nticks` on the jsonnet side, or the later (smaller-x) points get
clipped by `BinnedDiffusion_transform`'s time gate (see
docs/time_offset_calibration.md).
"""
import argparse
import json

import numpy as np


def _axis_values(v_min, v_max, spacing_mm):
    """Returns the scan points along one axis. spacing_mm == 0 means "don't scan this
    axis": a single point at v_min (v_max is ignored). Otherwise steps from v_min to
    v_max by spacing_mm, as np.arange."""
    if spacing_mm == 0:
        return np.array([v_min])
    return np.arange(v_min, v_max + 1e-9, spacing_mm)


def generate_grid_points(x_min, x_max, y_min, y_max, z_min, z_max,
                          dx_mm, dy_mm, dz_mm, charge, time_us):
    """Returns a list of {x,y,z (cm), charge, time (us)} dicts filling the given box.

    All args (bounds, spacing) are mm, matching this script's own CLI. The
    output x/y/z are converted to cm because that's what
    wct-sim-nf-sp-img-bdf-grid.jsonnet expects from an imported grid_points
    file (`wc.point(p.x, p.y, p.z, wc.cm)`) -- the jsonnet itself is left in
    cm, so the conversion happens here at the handoff instead.
    """
    xs = _axis_values(x_min, x_max, dx_mm)
    ys = _axis_values(y_min, y_max, dy_mm)
    zs = _axis_values(z_min, z_max, dz_mm)

    points = []
    for x in xs:
        for y in ys:
            for z in zs:
                points.append({
                    "x": float(x) / 10.0, "y": float(y) / 10.0, "z": float(z) / 10.0,
                    "charge": charge, "time": time_us,
                })
    return points


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bounds", nargs=6, type=float, action="append", required=True,
                         metavar=("X_MIN", "X_MAX", "Y_MIN", "Y_MAX", "Z_MIN", "Z_MAX"),
                         help="Grid bounding box in mm. Repeatable for multiple anodes/volumes.")
    parser.add_argument("--dx", type=float, default=10.0,
                         help="Drift (x) spacing in mm; 0 fixes x at X_MIN (X_MAX ignored). Default: 10.0")
    parser.add_argument("--dy", type=float, default=5.0,
                         help="Pitch-plane (y) spacing in mm; 0 fixes y at Y_MIN (Y_MAX ignored). Default: 5.0")
    parser.add_argument("--dz", type=float, default=5.0,
                         help="Pitch-plane (z) spacing in mm; 0 fixes z at Z_MIN (Z_MAX ignored). Default: 5.0")
    parser.add_argument("--charge", type=float, default=-50000,
                         help="Electrons per point (negative = fixed electrons/step). Default: -50000")
    parser.add_argument("--time", type=float, default=0.0, help="Depo time in us for the first point. Default: 0.0")
    parser.add_argument("--time-step", type=float, default=0.0,
                         help="Time spacing in us between points, ordered by x descending "
                              "(largest x / closest to anode gets --time first). "
                              "Default: 0.0 (all points at --time).")
    parser.add_argument("-o", "--output", required=True, help="Output JSON path.")
    args = parser.parse_args()

    print("[INFO] Parsed arguments:")
    for name, value in vars(args).items():
        print(f"[INFO]   {name} = {value}")

    all_points = []
    for x_min, x_max, y_min, y_max, z_min, z_max in args.bounds:
        pts = generate_grid_points(x_min, x_max, y_min, y_max, z_min, z_max,
                                    args.dx, args.dy, args.dz, args.charge, args.time)
        print(f"[INFO] bounds x=[{x_min},{x_max}] y=[{y_min},{y_max}] z=[{z_min},{z_max}] mm "
              f"-> {len(pts)} points")
        all_points.extend(pts)

    # Largest x (closest to anode, for anode 1/face 1) gets the earliest time.
    for rank, p in enumerate(sorted(all_points, key=lambda p: -p["x"])):
        p["time"] = args.time + rank * args.time_step

    with open(args.output, "w") as f:
        json.dump(all_points, f, indent=2)

    print(f"[INFO] Total {len(all_points)} points written to {args.output}")
    if len(all_points) > 5000:
        print("[WARNING] Large point count: TrackDepos re-sorts all depos after each "
              "track is added, so job startup cost grows with grid size.")


if __name__ == "__main__":
    main()
