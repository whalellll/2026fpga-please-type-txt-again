#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
kernel="${1:-rtl/mac_accel/mac_accel_dma_kernel.v}"
output="$(mktemp /tmp/mac-dma-output.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_mac_dma_output_stream -o "$output" \
  "$kernel" sim/tb_mac_dma_output_stream.sv
vvp "$output"
