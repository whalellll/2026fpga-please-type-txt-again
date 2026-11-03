#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
core="${1:-rtl/mac_accel/mac_conv_compute_core.v}"
baseline="${2:?provide frozen baseline core}"
temporary="$(mktemp -d /tmp/mac-conv-restart.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
python3 - "$baseline" "$temporary/baseline.v" <<'PY'
import re,sys
from pathlib import Path
text=Path(sys.argv[1]).read_text()
text=re.sub(r'\bmac_conv_compute_core\b','BaselineConvCore',text)
Path(sys.argv[2]).write_text(text)
PY
iverilog -g2012 -s tb_mac_conv_restart -o "$temporary/probe.vvp" \
  "$core" "$temporary/baseline.v" sim/tb_mac_conv_restart.sv
vvp "$temporary/probe.vvp"
