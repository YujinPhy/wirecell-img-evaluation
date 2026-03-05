#!/bin/sh

# wire-cell commands
wire-cell -L debug -l stdout --ext-code elecGain=14  $PDHD/for_img/wct-sim-nf-sp-img-blobdepofill.jsonnet

# convert results to bee display
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate

# python wct-img-2-bee-hd.py clusters-apa-apa0-ms-active.tar.gz clusters-apa-apa1-ms-active.tar.gz clusters-apa-apa2-ms-active.tar.gz clusters-apa-apa3-ms-active.tar.gz
python /nfs/data/1/yujin/img_test/pdhd/wct-img-2-bee-hd.py blobs-filled-apa0.tar.gz blobs-filled-apa1.tar.gz blobs-filled-apa2.tar.gz blobs-filled-apa3
deactivate

zip -r upload data

source /nfs/data/1/yujin/img_test/pdhd/upload-to-bee.sh upload.zip
