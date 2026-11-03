#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
core="${1:-rtl/mac_accel/MacAccelCore.v}"
temporary="$(mktemp -d /tmp/mac-pe-hold.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
python3 - "$temporary/reference.v" <<'PY'
import gzip,hashlib,json,re,sys
from pathlib import Path
path=Path('sim/reference/mac_pe_hold_reference.v.gz')
receipt=json.loads(path.with_suffix('.json').read_text())
raw=gzip.decompress(path.read_bytes())
assert hashlib.sha256(raw).hexdigest()==receipt['raw_sha256']
assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['gzip_sha256']
text=raw.decode()
names=re.findall(r'^module\s+(\w+)',text,re.M)
text=re.sub(r'\b(?:'+'|'.join(map(re.escape,names))+r')\b',lambda m:'Baseline'+m[0],text)
Path(sys.argv[1]).write_text(text)
PY
for bank in full word; do
    definitions=()
    if [[ "$bank" == word ]]; then definitions=(-DWORD_BIAS); fi
    if ! iverilog -g2012 "${definitions[@]}" -s tb_mac_pe_hold -o "$temporary/$bank.vvp" \
      "$core" "$temporary/reference.v" sim/gtp_apm_e2_perf_sim.v sim/tb_mac_pe_hold.sv 2>"$temporary/compile.log"; then
        cat "$temporary/compile.log" >&2; exit 1
    fi
    cat "$temporary/compile.log" >&2
    if grep -q 'warning:' "$temporary/compile.log"; then exit 1; fi
    vvp "$temporary/$bank.vvp"
done
echo MAC_PE_HOLD_DIFFERENTIAL_PASS bank_profiles=2 cases=128 reset_phases=22
