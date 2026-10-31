#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp /tmp/mac-conv-array.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
python3 sim/gen_yolo_conv_compute_vectors.py
iverilog -g2012 -s tb_mac_conv_compute_core \
  -Ptb_mac_conv_compute_core.MAX_FIRST_KERNEL_CYCLES=3500 \
  -o "$output" rtl/mac_accel/mac_conv_compute_core.v \
  sim/tb_mac_conv_compute_core.sv
vvp "$output"
