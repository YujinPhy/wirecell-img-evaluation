#!/bin/bash
#
# Compile a Wire-Cell Toolkit jsonnet config into JSON and/or render its
# pipeline graph as a PDF. Output files are written next to the input
# jsonnet file (same directory, same base name).
#
# Usage:
#   ./js.sh <json|pdf|all> <path/to/config.jsonnet> [dotify extra args]
#
# Examples:
#   ./js.sh json pdhd/wct-sim-nf-sp-img-bdf.jsonnet
#       -> writes pdhd/wct-sim-nf-sp-img-bdf.json
#   ./js.sh pdf pdhd/wct-sim-nf-sp-img-bdf.jsonnet
#       -> writes pdhd/wct-sim-nf-sp-img-bdf.pdf (requires the .json to already exist)
#   ./js.sh all pdhd/wct-sim-nf-sp-img-bdf.jsonnet
#       -> does both of the above in sequence
#
# Requires $WIRECELL_PATH to be set (colon-separated jsonnet search dirs).

name=$2
base_name="${name%.jsonnet}"


# Split $WIRECELL_PATH on colon into an array of directories
IFS=':' read -ra cfg_dirs <<< "$WIRECELL_PATH"

# Build the -J arguments from the array
J_ARGS=""
for (( idx=${#cfg_dirs[@]}-1; idx>=0; idx-- )); do
    J_ARGS="$J_ARGS -J ${cfg_dirs[$idx]}"
done
# Print the generated J_ARGS for debugging purposes
# echo "J_ARGS: $J_ARGS"

if [[ $1 == "json" || $1 == "all" ]]; then
    jsonnet \
      --ext-code DL=4.0 \
      --ext-code DT=8.8 \
      --ext-code lifetime=10.4 \
      --ext-code driftSpeed=1.60563 \
      --ext-str detector="uboone" \
      --ext-str input="orig-bl.root" \
      --ext-code evt=0 \
      --ext-code elecGain=14 \
      --ext-str output="orig-bl-nf-sp.root" \
      --ext-str reality="reality" \
      --ext-str signal_output_form="signal_output_form" \
      --ext-str raw_input_label="raw_input_lable" \
      --ext-str use_magnify="use_magnify" \
      $J_ARGS \
      ${base_name}.jsonnet \
      -o "${base_name}.json"
fi

if [[ $1 == "pdf" || $1 == "all" ]]; then
    # wirecell-pgraph dotify --jpath -1 --no-services --no-params ${base_name}.json ${base_name}.pdf
    wirecell-pgraph dotify --jpath -1 --no-params ${3} "${base_name}.json" "${base_name}.pdf"
fi
