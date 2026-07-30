#!/bin/bash
###################################################################################
# Reproduces data/pdhd/point_depo_grid_v3/: like run_point_depo_grid_v2.sh, but
# with a much finer (y,z) grid, targeting ~10cm spacing to match the x-axis
# scan step (DX_MM=100). v2 used a single N_SUB=9 split shared by both axes
# (dy=665.6mm, dz=256.3mm); a true 10cm split would need N_Y=60, N_Z=23
# (1380 regions, ~17x v2), which is too many WCT jobs to run in a reasonable
# time, so v3 compromises at 15cm-ish spacing instead:
#   N_SUB_Y=40 -> dy = 5990.60/40 = 149.765mm
#   N_SUB_Z=15 -> dz = 2306.73/15 = 153.782mm
# for 40x15=600 (y,z) points total (see docs/geometry/wirecell_sensitive_volume.md
# SS4: y in [76.10,6066.70]mm, z in [-1.00,2305.73]mm).
#
# Unlike v2 (which used a single N_SUB shared by both axes, since y and z
# have different spans), v3 splits each axis independently so both axes land
# close to the same ~15cm spacing: center_k = min + (k+0.5) * (span/N_SUB).
#
# Each of the 600 points is still scanned over x every 100mm across the bulk
# drift region [100,3430]mm, same as v1/v2 (cathode side of the response
# plane, so real diffusion/absorption physics applies -- see SS6 of the same
# doc).
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

OUT_ROOT=/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depo_grid_v3

GRID_GEN=/nfs/data/1/yujin/wirecell-img-evaluation/scripts/point_depo_grid_generator.py
CFG=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf-grid.jsonnet
BEE_CONVERT=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py
UPLOAD=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/upload-to-bee.sh

# anode1/face1 sensitive volume y-z bounds (see header comment).
Y_MIN_MM=76.10
Y_MAX_MM=6066.70
Z_MIN_MM=-1.00
Z_MAX_MM=2305.73
N_SUB_Y=40   # dy = 5990.60/40 = 149.765mm
N_SUB_Z=15   # dz = 2306.73/15 = 153.782mm

# 40x15 y-z grid centers (mm): center_k = min + (k+0.5) * (span/N_SUB_*).
# Region names encode the center in cm to 3 decimals (not grid index), with
# "p" standing in for the decimal point (e.g. y=1074.533mm -> "y107p453").
REGIONS=$(awk -v ymin="$Y_MIN_MM" -v ymax="$Y_MAX_MM" -v zmin="$Z_MIN_MM" -v zmax="$Z_MAX_MM" \
    -v ny="$N_SUB_Y" -v nz="$N_SUB_Z" '
    function cm_label(mm,    s) {
        s = sprintf("%.3f", mm / 10.0)
        gsub(/\./, "p", s)
        return s
    }
    BEGIN {
        dy = (ymax - ymin) / ny
        dz = (zmax - zmin) / nz
        for (i = 0; i < ny; i++) {
            y = ymin + (i + 0.5) * dy
            for (j = 0; j < nz; j++) {
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
    # fd 3 keeps a path back to the real terminal after stdout/stderr below
    # get redirected into this region's own log file -- used only for short
    # progress lines (detailed WCT/Bee output still goes to the log, per the
    # header comment on why full output isn't printed to the terminal).
    exec 3>&1
    trap 'echo "[FAIL] $NAME (see $LOG_FILE)" >&3' ERR
    exec >"$LOG_FILE" 2>&1

    echo "[START] $NAME" >&3

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
    echo "[DONE] $NAME -> $BEE_URL" >&3
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
TOTAL_REGIONS=$(echo "$REGIONS" | wc -l)
echo "Launching $TOTAL_REGIONS regions, $PARALLEL_JOBS at a time..."
echo "$REGIONS" | xargs -P "$PARALLEL_JOBS" -n 3 bash -c 'run_region "$0" "$1" "$2"'
echo "All $TOTAL_REGIONS regions finished (see $OUT_ROOT/<region>/run.log for per-region detail)."
