#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp /tmp/mac-weight-double-buffer.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -Wall -s tb_mac_weight_double_buffer -o "$output" \
  rtl/mac_accel/mac_weight_double_buffer.v \
  sim/tb_mac_weight_double_buffer.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_weight_depth27 -o "$output" \
  rtl/mac_accel/mac_weight_double_buffer.v \
  sim/tb_mac_weight_depth27.sv
vvp "$output"
