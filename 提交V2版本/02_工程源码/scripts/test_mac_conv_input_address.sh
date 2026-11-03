#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
dma="${1:-rtl/mac_accel/mac_conv_input_dma.v}"
output="$(mktemp /tmp/mac-conv-address.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_mac_conv_input_dma_address -o "$output" \
  "$dma" rtl/mac_accel/mac_conv_window.v sim/tb_mac_conv_input_dma_address.sv
vvp "$output"
