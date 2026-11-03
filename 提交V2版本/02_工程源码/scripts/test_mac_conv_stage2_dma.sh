#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp /tmp/mac-conv-stage2.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT

gcc -std=c11 -Wall -Wextra -Werror sim/test_pango_mac_conv_uapi.c \
  -o /tmp/test_pango_mac_conv_uapi
/tmp/test_pango_mac_conv_uapi
gcc -std=gnu11 -Wall -Wextra -Werror -fsyntax-only \
  linux/mac_accel/pango_mac_conv_window_test.c
iverilog -g2012 -Wall -s tb_mac_conv_descriptor_guard -o "$output" \
  rtl/mac_accel/mac_conv_descriptor_guard.v \
  sim/tb_mac_conv_descriptor_guard.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_conv_input_dma -o "$output" \
  rtl/mac_accel/mac_conv_window.v rtl/mac_accel/mac_conv_input_dma.v \
  sim/tb_mac_conv_input_dma.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_conv_input_dma_max_pixels -o "$output" \
  rtl/mac_accel/mac_conv_window.v rtl/mac_accel/mac_conv_input_dma.v \
  sim/tb_mac_conv_input_dma_max_pixels.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_conv_weight_dma -o "$output" \
  rtl/mac_accel/mac_weight_double_buffer.v \
  rtl/mac_accel/mac_conv_weight_dma.v sim/tb_mac_conv_weight_dma.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_conv_read_arbiter2 -o "$output" \
  rtl/mac_accel/mac_conv_read_arbiter2.v \
  sim/tb_mac_conv_read_arbiter2.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_conv_dma_concurrent -o "$output" \
  rtl/mac_accel/mac_conv_window.v \
  rtl/mac_accel/mac_conv_input_dma.v \
  rtl/mac_accel/mac_weight_double_buffer.v \
  rtl/mac_accel/mac_conv_weight_dma.v \
  rtl/mac_accel/mac_conv_read_arbiter2.v \
  sim/tb_mac_conv_dma_concurrent.sv
vvp "$output"
iverilog -g2012 -Wall -s tb_mac_conv_mmio_frontend -o "$output" \
  rtl/mac_accel/mac_conv_descriptor_guard.v \
  rtl/mac_accel/mac_conv_window.v \
  rtl/mac_accel/mac_conv_input_dma.v \
  rtl/mac_accel/mac_weight_double_buffer.v \
  rtl/mac_accel/mac_conv_weight_dma.v \
  rtl/mac_accel/mac_conv_read_arbiter2.v \
  rtl/mac_accel/mac_conv_compute_core.v \
  rtl/mac_accel/mac_conv_compact_packer.v \
  rtl/mac_accel/mac_conv_compact_writer.v \
  rtl/mac_accel/mac_conv_rw_arbiter2.v \
  rtl/mac_accel/mac_conv_mmio_frontend.v \
  sim/tb_mac_conv_mmio_frontend.sv
vvp "$output"
bash scripts/test_mac_weight_double_buffer.sh
bash scripts/test_mac_conv_input_address.sh
