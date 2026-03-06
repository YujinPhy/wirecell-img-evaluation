#!/bin/sh

export CFG=/nfs/data/1/yujin/img_BlobDepoFill/wct-sim/wct-sim-nf-sp-img-bdf.jsonnet

# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14  $CFG

# #convert results to bee display
# export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
# source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate


# python /nfs/data/1/yujin/img_test/pdhd/wct-img-2-bee-hd.py clusters-apa-apa0.tar.gz clusters-apa-apa1.tar.gz clusters-apa-apa2.tar.gz clusters-apa-apa3.tar.gz
# deactivate

# zip -r upload data

# source /nfs/data/1/yujin/img_test/pdhd/upload-to-bee.sh upload.zip