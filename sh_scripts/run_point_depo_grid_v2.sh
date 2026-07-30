#!/bin/bash
###################################################################################
# Reproduces data/pdhd/point_depo_grid_v2/: like run_point_depo_grid_v1.sh, but
# with a finer (y,z) grid. v1 scanned the center of a 3x3 split of PDHD
# anode1/face1's sensitive volume y-z plane (9 points); v2 further splits each
# of those 9 cells into its own 3x3 sub-grid and takes each sub-cell's center,
# for 9x9=81 (y,z) points total (see docs/geometry/wirecell_sensitive_volume.md
# SS4: y in [76.10,6066.70]mm, z in [-1.00,2305.73]mm).
#
# A nested 3x3-of-3x3 split of a uniform range is mathematically identical to
# splitting that range directly into 9 equal cells (center_k = min + (k+0.5) *
# (range/9) for k=0..8), so the grid below is generated that way rather than
# via two literal nested loops -- same 81 points, simpler to compute.
#
# Each of the 81 points is still scanned over x every 100mm across the bulk
# drift region [100,3430]mm, same as v1 (cathode side of the response plane,
# so real diffusion/absorption physics applies -- see SS6 of the same doc).
#
# Regions run PARALLEL_JOBS at a time via `xargs -P` (each region's own WCT
# job is small, so 9 concurrent jobs is a reasonable default on this machine --
# raise/lower to match available cores/memory; `parallel` on this machine is
# moreutils' parallel, not GNU parallel, so xargs is used instead). Each
# region's per-job output (grid generation + wire-cell + Bee convert/upload)
# goes to its own <region>/run.log instead of the terminal, since concurrent
# jobs writing to stdout at once would interleave into an unreadable mess.
###################################################################################

set -e

PARALLEL_JOBS=9

ANODES="1"
X_BOUNDS_MM="100 3430"
DX_MM=100
DY_MM=0
DZ_MM=0
CHARGE=-50000
TIME_US=0
TIME_STEP_US=0

THETA_XZ_DEG=0
LEN=0.1
STEP=1

OUT_ROOT=/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depo_grid_v2

GRID_GEN=/nfs/data/1/yujin/wirecell-img-evaluation/scripts/point_depo_grid_generator.py
CFG=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf-grid.jsonnet
BEE_CONVERT=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py
UPLOAD=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/upload-to-bee.sh

# anode1/face1 sensitive volume y-z bounds (see header comment).
Y_MIN_MM=76.10
Y_MAX_MM=6066.70
Z_MIN_MM=-1.00
Z_MAX_MM=2305.73
N_SUB=9   # 3x3 of 3x3 == a direct 9-way split per axis

# 9x9 y-z grid centers (mm): center_k = min + (k+0.5) * ((max-min)/N_SUB).
# Region names encode the center in cm to 3 decimals (not grid index), with
# "p" standing in for the decimal point (e.g. y=1074.533mm -> "y107p453").
REGIONS=$(awk -v ymin="$Y_MIN_MM" -v ymax="$Y_MAX_MM" -v zmin="$Z_MIN_MM" -v zmax="$Z_MAX_MM" -v n="$N_SUB" '
    function cm_label(mm,    s) {
        s = sprintf("%.3f", mm / 10.0)
        gsub(/\./, "p", s)
        return s
    }
    BEGIN {
        dy = (ymax - ymin) / n
        dz = (zmax - zmin) / n
        for (i = 0; i < n; i++) {
            y = ymin + (i + 0.5) * dy
            for (j = 0; j < n; j++) {
                z = zmin + (j + 0.5) * dz
                printf "y%s_z%s %.3f %.3f\n", cm_label(y), cm_label(z), y, z
            }
        }
    }
')

mkdir -p "$OUT_ROOT"

export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"

# Runs one region end-to-end (grid gen -> WCT pipeline -> Bee convert/upload ->
# run record). Pulled out into a function, rather than inline in a loop, so
# `xargs -P` can invoke it as an independent unit per region -- each
# invocation gets its own subshell (own `cd`), so concurrent regions never
# race on working directory the way looped `cd` + `&` would.
run_region() {
    # xargs invokes this via a fresh non-interactive shell that doesn't
    # inherit the top-level `set -e`, so it's set again here -- without it, a
    # failed wire-cell/python step wouldn't stop the rest of this region's
    # steps from running on top of the failure.
    set -e

    NAME="$1"
    Y="$2"
    Z="$3"

    REGION_DIR="$OUT_ROOT/$NAME"
    mkdir -p "$REGION_DIR"
    cd "$REGION_DIR"

    LOG_FILE="$REGION_DIR/run.log"
    exec >"$LOG_FILE" 2>&1

    Y_BOUNDS_MM="$Y $Y"
    Z_BOUNDS_MM="$Z $Z"
    GRID_JSON="$REGION_DIR/grid_points.json"

    echo "==== Region $NAME: y=${Y}mm z=${Z}mm -> $REGION_DIR ===="

    # 1. Generate this region's grid points (point cloud).
    source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate
    python "$GRID_GEN" --bounds $X_BOUNDS_MM $Y_BOUNDS_MM $Z_BOUNDS_MM \
        --dx "$DX_MM" --dy "$DY_MM" --dz "$DZ_MM" \
        --charge "$CHARGE" --time "$TIME_US" --time-step "$TIME_STEP_US" \
        -o "$GRID_JSON"
    deactivate

    TLA_ANODES="[$(echo $ANODES | tr ' ' ',')]"

    # 2. Run the WCT sim -> NF/SP -> img -> BlobDepoFill pipeline.
    wire-cell -L debug -l stdout --ext-code elecGain=14 \
        --tla-code anodes=$TLA_ANODES \
        --tla-code grid_points="import '$GRID_JSON'" \
        --tla-code theta_xz_deg=$THETA_XZ_DEG \
        --tla-code len=$LEN \
        --tla-code step=$STEP \
        $CFG

    # 3. Convert results to Bee display and upload.
    source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate
    PAIR_ARGS=""
    for a in $ANODES; do
        PAIR_ARGS="$PAIR_ARGS --pair $a clusters-apa-$a.tar.gz clusters-apa-bdf-$a.tar.gz"
    done
    python $BEE_CONVERT $PAIR_ARGS
    deactivate

    BEE_URL=$(source "$UPLOAD" upload.zip)
    echo "Bee URL: $BEE_URL"

    # 4. Record this region's run settings + Bee URL.
    RUN_TS=$(date +%Y%m%dT%H%M%S)
    RECORD_FILE="$REGION_DIR/run-${RUN_TS}.json"
    cat > "$RECORD_FILE" <<EOF
{
    "timestamp": "${RUN_TS}",
    "cfg": "${CFG}",
    "region": "${NAME}",
    "params": {
        "anodes": ${TLA_ANODES},
        "x_bounds_mm": "${X_BOUNDS_MM}",
        "y_bounds_mm": "${Y_BOUNDS_MM}",
        "z_bounds_mm": "${Z_BOUNDS_MM}",
        "dx_mm": ${DX_MM},
        "dy_mm": ${DY_MM},
        "dz_mm": ${DZ_MM},
        "charge": ${CHARGE},
        "time_us": ${TIME_US},
        "time_step_us": ${TIME_STEP_US}
    },
    "bee_url": "${BEE_URL}"
}
EOF
    echo "Run record written to ${RECORD_FILE}"
}

export -f run_region
export OUT_ROOT GRID_GEN CFG BEE_CONVERT UPLOAD PYTHONPATH \
    ANODES X_BOUNDS_MM DX_MM DY_MM DZ_MM CHARGE TIME_US TIME_STEP_US \
    THETA_XZ_DEG LEN STEP

# `parallel` on this machine is moreutils' parallel, not GNU parallel (no
# --colsep/{1} placeholders/--joblog), so PARALLEL_JOBS-way concurrency is
# done via `xargs -P` instead: `-n 3` groups each REGIONS line's 3
# whitespace-separated fields (NAME Y Z) into one run_region call; `bash -c
# 'run_region "$0" "$1" "$2"'` maps them in ($0=NAME, $1=Y, $2=Z) because the
# first token after the -c script string fills $0, not $1.
echo "$REGIONS" | xargs -P "$PARALLEL_JOBS" -n 3 bash -c 'run_region "$0" "$1" "$2"'
