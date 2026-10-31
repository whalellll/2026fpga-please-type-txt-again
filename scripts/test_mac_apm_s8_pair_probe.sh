#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
vendor_model="${PDS_APM_MODEL:-/mnt/g/fpga/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation/GTP_APM_E2.v}"
test -f "$vendor_model"
output="$(mktemp /tmp/mac-apm-s8-pair.XXXXXX.vvp)"
trap 'rm -f "$output"' EXIT
iverilog -g2012 -s tb_mac_apm_s8_pair_probe -o "$output" \
  "$vendor_model" sim/mac_apm_s8_pair_probe.sv sim/tb_mac_apm_s8_pair_probe.sv
vvp "$output"
