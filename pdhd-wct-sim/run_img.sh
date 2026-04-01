#!/bin/sh

export CFG=/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/wct-sim-nf-sp-img-bdf.jsonnet
export BEE_CONVERT=/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/wct-img-2-bee-hd-bdf.py
export UPLOAD=/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/upload-to-bee.sh

# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14  $CFG

# convert results to bee display
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate

# process only reco data
# python $BEE_CONVERT clusters-apa-0.tar.gz clusters-apa-1.tar.gz clusters-apa-2.tar.gz clusters-apa-3.tar.gz

python $BEE_CONVERT clusters-apa-1.tar.gz clusters-apa-bdf-1.tar.gz
# python $BEE_CONVERT clusters-apa-0.tar.gz clusters-apa-bdf-0.tar.gz


deactivate

# zip -r upload data
source $UPLOAD upload.zip