#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
core="${1:-rtl/mac_accel/MacAccelCore.v}"
output="$(mktemp /tmp/mac-lane-select.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_mac_lane_select -o "$output" \
  "$core" sim/gtp_apm_e2_perf_sim.v sim/tb_mac_lane_select.sv
vvp "$output"
