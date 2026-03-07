#!/bin/sh

export CFG=/nfs/data/1/yujin/img_BlobDepoFill/wct-sim/wct-sim-nf-sp-img-bdf.jsonnet

# export BEE_CONVERT=/nfs/data/1/yujin/img_BlobDepoFill/wct-sim/wct-img-2-bee-hd.py
export BEE_CONVERT=/nfs/data/1/yujin/img_BlobDepoFill/wct-sim/wct-img-2-bee-hd-bdf.py
# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14  $CFG

# convert results to bee display
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate

# process only reco data
# python $BEE_CONVERT clusters-apa-0.tar.gz clusters-apa-1.tar.gz clusters-apa-2.tar.gz clusters-apa-3.tar.gz
python $BEE_CONVERT clusters-apa-1.tar.gz clusters-apa-bdf-1.tar.gz
# python /nfs/data/1/yujin/img_BlobDepoFill/wct-sim/charge_debug.py clusters-apa-1.tar.gz clusters-apa-bdf-1.tar.gz


deactivate

# zip -r upload data

source /nfs/data/1/yujin/img_BlobDepoFill/wct-sim/upload-to-bee.sh /nfs/data/1/yujin/img_BlobDepoFill/wct-sim/test/upload.zip