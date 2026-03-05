cfg1=/dune/data/users/wgu/opt_dunesw/localProducts_larsoft_v09_79_00_e26_prof/dunereco/v09_79_00d02/wire-cell-cfg
cfg2=/cvmfs/larsoft.opensciencegrid.org/products/wirecell/v0_24_3/Linux64bit+3.10-2.17-e26-prof/share/wirecell
cfg3=/cvmfs/dune.opensciencegrid.org/products/dune/dune_pardata/v01_84_00/WireCellData

name=$2

if [[ $1 == "json" || $1 == "all" ]]; then
jsonnet \
--ext-code DL=4.0 \
--ext-code DT=8.8 \
--ext-code lifetime=10.4 \
--ext-code driftSpeed=1.60563 \
--ext-str detector="uboone" \
--ext-str input="orig-bl.root" \
--ext-code evt=0 \
--ext-str output="orig-bl-nf-sp.root" \
-J $cfg3 \
-J $cfg2 \
-J $cfg1 \
${name}.jsonnet \
-o ${name}.json
fi

if [[ $1 == "pdf" || $1 == "all" ]]; then
    wirecell-pgraph dotify --jpath -1 --no-services --no-params ${name}.json ${name}.pdf
    #wirecell-pgraph dotify --no-services --jpath -1 ${name}.json ${name}.pdf
fi
