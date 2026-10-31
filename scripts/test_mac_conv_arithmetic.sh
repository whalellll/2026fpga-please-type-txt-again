#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
core="${1:-rtl/mac_accel/mac_conv_compute_core.v}"
output="$(mktemp /tmp/mac-conv-arithmetic.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_mac_conv_arithmetic -o "$output" \
  "$core" sim/tb_mac_conv_arithmetic.sv
vvp "$output"
