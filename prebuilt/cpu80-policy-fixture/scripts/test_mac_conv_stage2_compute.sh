#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 sim/gen_yolo_conv_compute_vectors.py
python3 -m unittest sim.test_yolo_stage2_reference sim.test_yolo_stage2_traffic
python3 vision/stage2_traffic_report.py \
  --measurements vision/stage2_window_board_measurements.json
gcc -std=gnu11 -Wall -Wextra -Werror \
  linux/mac_accel/pango_mac_conv_compute_test.c \
  -o /tmp/pango_mac_conv_compute_test
/tmp/pango_mac_conv_compute_test --oracle-only
gcc -std=c11 -O2 -Wall -Wextra -Werror \
  sim/gen_yolo_first_layer_board_crc.c \
  -o /tmp/gen_yolo_first_layer_board_crc
/tmp/gen_yolo_first_layer_board_crc
output="$(mktemp /tmp/mac-conv-compute.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
for bench in tb_mac_conv_compute_core tb_mac_conv_compact_packer \
             tb_mac_conv_compact_writer tb_mac_conv_rw_arbiter2; do
  iverilog -g2012 -s "$bench" -o "$output" \
    rtl/mac_accel/mac_conv_*.v rtl/mac_accel/mac_weight_double_buffer.v \
    "sim/$bench.sv"
  vvp "$output"
done
for case_id in 0 1 2 3 4; do
  iverilog -g2012 -s tb_mac_conv_mmio_compute \
    -Ptb_mac_conv_mmio_compute.CASE_ID="$case_id" -o "$output" \
    rtl/mac_accel/mac_conv_*.v rtl/mac_accel/mac_weight_double_buffer.v \
    sim/tb_mac_conv_mmio_compute.sv
  vvp "$output"
done
