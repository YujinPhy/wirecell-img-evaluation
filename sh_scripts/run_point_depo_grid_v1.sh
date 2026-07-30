#!/bin/sh
###################################################################################
# Reproduces data/pdhd/point_depo_grid_v1/: runs run_grid_points.sh's pipeline
# once per (y,z) center of a 3x3 split of PDHD anode1/face1's sensitive volume
# y-z plane (see docs/geometry/wirecell_sensitive_volume.md SS4: y in
# [76.10,6066.70]mm, z in [-1.00,2305.73]mm), scanning x every 100mm across the
# bulk drift region [100,3430]mm (cathode side of the response plane, so real
# diffusion/absorption physics applies -- see SS6 of the same doc).
###################################################################################

set -e

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

OUT_ROOT=/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depo_grid_v1

GRID_GEN=/nfs/data/1/yujin/wirecell-img-evaluation/scripts/point_depo_grid_generator.py
CFG=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf-grid.jsonnet
BEE_CONVERT=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py
UPLOAD=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/upload-to-bee.sh

# 3x3 y-z grid centers (mm) of anode1/face1's sensitive volume, computed from
# y in [76.10,6066.70]mm (3 x 1996.867mm cells) and z in [-1.00,2305.73]mm
# (3 x 768.91mm cells): center = min + (index+0.5) * cell_size.
REGIONS="
y0_z0 1074.533 383.455
y1_z0 3071.400 383.455
y2_z0 5068.267 383.455
y0_z1 1074.533 1152.365
y1_z1 3071.400 1152.365
y2_z1 5068.267 1152.365
y0_z2 1074.533 1921.275
y1_z2 3071.400 1921.275
y2_z2 5068.267 1921.275
"

mkdir -p "$OUT_ROOT"

export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"

echo "$REGIONS" | while read -r NAME Y Z; do
    [ -z "$NAME" ] && continue

    REGION_DIR="$OUT_ROOT/$NAME"
    mkdir -p "$REGION_DIR"
    cd "$REGION_DIR"

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
done
