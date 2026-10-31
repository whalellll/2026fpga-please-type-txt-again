#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(mktemp /tmp/mac-output-layout.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_mac_output_layout -o "$output" \
  rtl/mac_accel/MacAccelCore.v sim/gtp_apm_e2_perf_sim.v sim/tb_mac_output_layout.sv
vvp "$output"
