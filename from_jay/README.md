
```bash
path-prepend /exp/dune/app/users/yuhw/wct/cfg WIRECELL_PATH
path-prepend /exp/dune/app/users/yuhw/opt/lib64/ LD_LIBRARY_PATH
source /exp/dune/app/users/yuhw/wire-cell-python/wcpy/bin/activate
wire-cell -l log -L debug -c wct-sim-fans.jsonnet
python wct-img-2-bee.py clusters-apa-reco-6.tar.gz clusters-apa-bdf-6.tar.gz
./zip-upload.sh
```
