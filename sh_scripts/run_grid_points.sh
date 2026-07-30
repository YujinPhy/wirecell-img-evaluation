#!/bin/sh

###################################################################################
# Run parameters (forwarded to CFG's jsonnet TLAs)
###################################################################################
# Anode indices to simulate and convert (space-separated, any subset of 0-3).
ANODES="1"

# Grid bounds (mm), one min/max pair per axis. Fill in real sensitive-volume bounds
# (e.g. via scripts/utils/wires.py's face_sensitive_bounds, or
# wire-cell-python's own wire-geometry inspection tools) before running.
X_BOUNDS_MM="100 3400"   # x_min x_max, mm (drift direction)
Y_BOUNDS_MM="3000 3000"  # y_min y_max, mm
Z_BOUNDS_MM="1000 1000"  # z_min z_max, mm

DX_MM=100   # drift (x) spacing, mm
DY_MM=0    # pitch-plane (y) spacing, mm
DZ_MM=0    # pitch-plane (z) spacing, mm
CHARGE=-50000  # electrons/step (negative)
TIME_US=0
TIME_STEP_US=0  # us between consecutive points' depo time (regular interval);
                    # 0 keeps all points at TIME_US.

THETA_XZ_DEG=0  # deg, per-point track direction (see run_single_point.sh)
LEN=0.1           # cm, per-point track length
STEP=1            # mm, for point depo use 1

# Grid position file (JSON)
GRID_JSON="$(pwd)/grid_points.json"

###################################################################################
# Required Scripts
###################################################################################
# Generate grid points (point cloud) for the given anodes and bounds, with the specified spacing and charge/time parameters.
GRID_GEN=/nfs/data/1/yujin/wirecell-img-evaluation/scripts/point_depo_grid_generator.py

# WireCell Jsonnet cfg
CFG=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf-grid.jsonnet

# Bee conversion script and upload script (to generate a Bee URL for the results).
BEE_CONVERT=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py

# Upload script to generate a Bee URL for the results.
UPLOAD=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/upload-to-bee.sh

####################################################################################
# Run the grid points simulation and convert to Bee display.
####################################################################################
# 1. Activate the Wire-Cell Python virtual environment 
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate

# 2. Generate the grid points (point cloud) for the given anodes and bounds, with the specified spacing and charge/time parameters via `$GRID_GEN`.
# point_depo_grid_generator.py's --bounds/--dx/--dy/--dz are all mm now, so
# these pass straight through; it does its own mm->cm conversion internally
# right before writing grid_points.json, since the jsonnet (unchanged) still
# expects cm from that file.
python "$GRID_GEN" --bounds $X_BOUNDS_MM $Y_BOUNDS_MM $Z_BOUNDS_MM \
    --dx "$DX_MM" --dy "$DY_MM" --dz "$DZ_MM" \
    --charge "$CHARGE" --time "$TIME_US" --time-step "$TIME_STEP_US" \
    -o "$GRID_JSON"

deactivate

TLA_ANODES="[$(echo $ANODES | tr ' ' ',')]"

# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14 \
    --tla-code anodes=$TLA_ANODES \
    --tla-code grid_points="import '$GRID_JSON'" \
    --tla-code theta_xz_deg=$THETA_XZ_DEG \
    --tla-code len=$LEN \
    --tla-code step=$STEP \
    $CFG

# convert results to bee display
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate

PAIR_ARGS=""
for a in $ANODES; do
    PAIR_ARGS="$PAIR_ARGS --pair $a clusters-apa-$a.tar.gz clusters-apa-bdf-$a.tar.gz"
done
python $BEE_CONVERT $PAIR_ARGS

deactivate

# zip -r upload data
BEE_URL=$(source "$UPLOAD" upload.zip)
echo "Bee URL: $BEE_URL"

# ==== Record this run's settings + Bee URL ====
RUN_TS=$(date +%Y%m%dT%H%M%S)
RECORD_FILE="run-${RUN_TS}.json"
cat > "$RECORD_FILE" <<EOF
{
    "timestamp": "${RUN_TS}",
    "cfg": "${CFG}",
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
