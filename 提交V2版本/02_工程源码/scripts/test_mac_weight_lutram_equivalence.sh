#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=$(mktemp /tmp/mac-weight-equivalence.XXXXXX.vvp)
trap 'rm -f "$image"' EXIT
for depth in 4 27 32; do
 aw=5
 if [ "$depth" = 4 ]; then aw=2; fi
 iverilog -g2012 -s tb_mac_weight_lutram_equivalence \
  -Ptb_mac_weight_lutram_equivalence.DEPTH="$depth" \
  -Ptb_mac_weight_lutram_equivalence.AW="$aw" -o "$image" \
  sim/reference/mac_weight_double_buffer_cpu80.v \
  rtl/mac_accel/mac_weight_double_buffer.v sim/tb_mac_weight_lutram_equivalence.sv
 vvp "$image"
done
