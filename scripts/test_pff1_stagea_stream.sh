#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(mktemp /tmp/pff1-stream.XXXXXX.vvp)"
trap 'rm -f "$out"' EXIT
iverilog -g2012 -s tb_pff1_stagea_stream -o "$out" \
  rtl/mac_accel/pff1_stagea_gather.v sim/tb_pff1_stagea_stream.sv
vvp "$out"
