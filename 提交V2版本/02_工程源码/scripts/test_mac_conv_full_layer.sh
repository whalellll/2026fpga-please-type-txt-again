#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp /tmp/mac-conv-full-layer.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_soc_mac_conv_full_layer -o "$output" \
  rtl/mac_accel/mac_accel_dma_kernel.v \
  rtl/mac_accel/mac_accel_axi_master32.v \
  rtl/mac_accel/xiangqi_sparse_eval.v \
  rtl/mac_accel/mac_accel_ddr_kernel_top.v \
  rtl/mac_accel/mac_conv_*.v \
  rtl/mac_accel/mac_weight_double_buffer.v \
  rtl/mac_accel/MacAccelCore.v \
  sim/gtp_apm_e2_perf_sim.v sim/axi_shared_ram.sv \
  sim/tb_soc_mac_conv_full_layer.sv
vvp "$output"
