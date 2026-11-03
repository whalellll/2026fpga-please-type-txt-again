#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp /tmp/mac-conv-window.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -Wall -s tb_mac_conv_window -o "$output" \
  rtl/mac_accel/mac_conv_window.v sim/tb_mac_conv_window.sv
vvp "$output"
python3 sim/gen_yolo_window_board_vectors.py
iverilog -g2012 -Wall -s tb_mac_conv_window_board_top -o "$output" \
  rtl/mac_accel/mac_conv_window.v sim/mac_conv_window_board_top.v \
  sim/tb_mac_conv_window_board_top.sv
vvp "$output"
vvp "$output" +CORRUPT_EXPECTED
python3 sim/gen_yolo_window_vectors.py
iverilog -g2012 -Wall -s tb_mac_conv_window_vectors -o "$output" \
  rtl/mac_accel/mac_conv_window.v sim/tb_mac_conv_window_vectors.sv
vvp "$output"
