#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
core="${1:-rtl/mac_accel/MacAccelCore.v}"
baseline="${2:?provide the frozen baseline core}"
temporary="$(mktemp -d /tmp/mac-post-pipeline.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
python3 - "$baseline" "$temporary/baseline.v" <<'PY'
import re,sys
from pathlib import Path
text=Path(sys.argv[1]).read_text()
names=re.findall(r'^module\s+(\w+)',text,re.M)
pattern=r'\b(?:'+'|'.join(map(re.escape,names))+r')\b'
text=re.sub(pattern,lambda m:'Baseline'+m[0],text)
Path(sys.argv[2]).write_text(text)
PY
iverilog -g2012 -s tb_mac_post_pipeline -o "$temporary/probe.vvp" \
  "$core" "$temporary/baseline.v" sim/gtp_apm_e2_perf_sim.v sim/tb_mac_post_pipeline.sv
vvp "$temporary/probe.vvp"
