#!/bin/bash
###################################################################################
# TEMPORARY one-off regeneration copy of run_point_depo_grid_v3.sh -- not a
# permanent addition to sh_scripts/, delete after use.
#
# Regenerates the 40 point_depo_grid_v3 regions that were deleted: all 40 y
# positions at the single z=229.673mm row (z-index j=1 of the 15-way z split,
# N_SUB_Z=15, dz=153.782mm). These were removed because that z row
# deterministically produced 68 Gen0 depos instead of 34 (each of the 34 x
# positions paired with a second, unrequested point at z=230.673mm, 1mm off) --
# reproduced even after a clean rm -rf + rerun, so the cause sits in the WCT
# sim/geometry config for this particular z, not in a stale/double-run
# artifact. This script does not attempt to fix that; it only regenerates the
# same 40 regions the same way run_point_depo_grid_v3.sh would.
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
LEN=0.05  # was 0.1 (== step=1mm exactly); testing whether a clear len < step
          # margin avoids the len<=step floating-point boundary that produced
          # 2 depos per track for the z=229.673mm row (see run.log evidence:
          # "depos: 2 over 1.0000000000000284mm" vs "depos: 1 over
          # 0.9999999999999858mm" in a clean region).
STEP=1

OUT_ROOT=/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depo_grid_v3

GRID_GEN=/nfs/data/1/yujin/wirecell-img-evaluation/scripts/point_depo_grid_generator.py
CFG=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf-grid.jsonnet
BEE_CONVERT=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py
UPLOAD=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/upload-to-bee.sh

# anode1/face1 sensitive volume y-z bounds (see run_point_depo_grid_v3.sh header).
Y_MIN_MM=76.10
Y_MAX_MM=6066.70
Z_MIN_MM=-1.00
Z_MAX_MM=2305.73
N_SUB_Y=40
N_SUB_Z=15
Z_INDEX=1   # the removed row: z = Z_MIN_MM + (Z_INDEX + 0.5) * (span/N_SUB_Z) = 229.673mm

# Only the 40 (y, z=229.673mm) regions -- same center formula as
# run_point_depo_grid_v3.sh's REGIONS awk, restricted to the single z-index
# above instead of looping over all 15.
REGIONS=$(awk -v ymin="$Y_MIN_MM" -v ymax="$Y_MAX_MM" -v zmin="$Z_MIN_MM" -v zmax="$Z_MAX_MM" \
    -v ny="$N_SUB_Y" -v nz="$N_SUB_Z" -v zidx="$Z_INDEX" '
    function cm_label(mm,    s) {
        s = sprintf("%.3f", mm / 10.0)
        gsub(/\./, "p", s)
        return s
    }
    BEGIN {
        dy = (ymax - ymin) / ny
        dz = (zmax - zmin) / nz
        z = zmin + (zidx + 0.5) * dz
        for (i = 0; i < ny; i++) {
            y = ymin + (i + 0.5) * dy
            printf "y%s_z%s %.3f %.3f\n", cm_label(y), cm_label(z), y, z
        }
    }
')

echo "Regions to regenerate (region name, y_mm, z_mm):"
echo "$REGIONS"
echo "---"

mkdir -p "$OUT_ROOT"

export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"

# Identical to run_point_depo_grid_v3.sh's run_region (see that file for
# rationale on fd 3 / trap / xargs usage).
run_region() {
    set -e

    NAME="$1"
    Y="$2"
    Z="$3"

    REGION_DIR="$OUT_ROOT/$NAME"
    mkdir -p "$REGION_DIR"
    cd "$REGION_DIR"

    LOG_FILE="$REGION_DIR/run.log"
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

TOTAL_REGIONS=$(echo "$REGIONS" | wc -l)
echo "Launching $TOTAL_REGIONS regions, $PARALLEL_JOBS at a time..."
echo "$REGIONS" | xargs -P "$PARALLEL_JOBS" -n 3 bash -c 'run_region "$0" "$1" "$2"'
echo "All $TOTAL_REGIONS regions finished (see $OUT_ROOT/<region>/run.log for per-region detail)."
