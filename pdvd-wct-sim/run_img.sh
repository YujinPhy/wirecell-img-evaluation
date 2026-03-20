#!/bin/sh

export CFG=/nfs/data/1/yujin/img_BlobDepoFill/pdvd-wct-sim/wct-sim-nf-sp-img-bdf.jsonnet
export BEE_CONVERT=/nfs/data/1/yujin/img_BlobDepoFill/pdvd-wct-sim/wct-img-2-bee.py
export UPLOAD=/nfs/data/1/yujin/img_BlobDepoFill/pdvd-wct-sim/upload-to-bee.sh

# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14  $CFG

# convert results to bee display
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate

# process only reco data
# python $BEE_CONVERT clusters-apa-0.tar.gz clusters-apa-1.tar.gz clusters-apa-2.tar.gz clusters-apa-3.tar.gz clusters-apa-4.tar.gz clusters-apa-5.tar.gz clusters-apa-6.tar.gz clusters-apa-7.tar.gz

python $BEE_CONVERT clusters-apa-0.tar.gz clusters-apa-bdf-0.tar.gz
# python $BEE_CONVERT clusters-apa-1.tar.gz clusters-apa-bdf-1.tar.gz


deactivate

# zip -r upload data
source $UPLOAD upload.zip