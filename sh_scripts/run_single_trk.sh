#!/bin/sh

# ==== Run parameters (forwarded to CFG's jsonnet TLAs) ====
# Anode indices to simulate and convert (space-separated, any subset of 0-3).
ANODES="1"

# Track definition (see wct-sim-nf-sp-img-bdf.jsonnet's function args)
THETA_XZ_DEG=45   # deg
LEN=50            # cm
X_START=150       # cm
Y_START=300       # cm
Z_START=100       # cm
CHARGE=-500       # electrons/step (negative)
STEP=0.1          # mm, for point depo use 1


CFG=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet
BEE_CONVERT=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py
UPLOAD=/nfs/data/1/yujin/wirecell-img-evaluation/wire-cell-cfg/pdhd/upload-to-bee.sh

TLA_ANODES="[$(echo $ANODES | tr ' ' ',')]"

# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14 \
    --tla-code anodes=$TLA_ANODES \
    --tla-code theta_xz_deg=$THETA_XZ_DEG \
    --tla-code len=$LEN \
    --tla-code x_start=$X_START \
    --tla-code y_start=$Y_START \
    --tla-code z_start=$Z_START \
    --tla-code charge=$CHARGE \
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
        "theta_xz_deg": ${THETA_XZ_DEG},
        "len": ${LEN},
        "x_start": ${X_START},
        "y_start": ${Y_START},
        "z_start": ${Z_START},
        "charge": ${CHARGE},
        "step": ${STEP}
    },
    "bee_url": "${BEE_URL}"
}
EOF
echo "Run record written to ${RECORD_FILE}"
