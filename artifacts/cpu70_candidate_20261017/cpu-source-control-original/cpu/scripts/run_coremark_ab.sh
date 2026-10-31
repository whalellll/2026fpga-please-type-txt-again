#!/usr/bin/env bash
# Historical filename retained for handoff scripts. The current CPU is IMA-only.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != ima ) ]]; then
  echo 'Usage: run_coremark_ab.sh [ima]; C-extension comparisons are archived evidence.' >&2
  exit 2
fi
vlt="${VERILATOR:-verilator}"
core_sv="${CORE_TEST_SV:-$root/generated/sim/CoreTop.sv}"
source="${COREMARK_FIRMWARE_ROOT:-$root/coremark_test_soc/sim/coremark_ima}"
output_root="${COREMARK_RESULT_ROOT:-$root/work/coremark-ima}"
build_root="${COREMARK_BUILD_ROOT:-$root/work/verilator-coremark-ima}"
host_cxx_flags="${COREMARK_HOST_CXX_FLAGS:--Os}"
case "$host_cxx_flags" in
  -Os|-O3) ;;
  *) echo 'COREMARK_HOST_CXX_FLAGS must be -Os or -O3; it affects only the host simulator.' >&2; exit 2 ;;
esac
test -s "$core_sv"
python3 scripts/verify_generated.py check --simulation "$core_sv"
python3 scripts/verify_firmware.py "$source"
cpu_hz=$(python3 - "$source" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
m = json.loads((root / 'manifest.json').read_text())
if (m['isa'], m['march'], m['abi'], m['compressed_instructions']) != (
        'rv32ima', 'rv32ima_zicsr_zifencei', 'ilp32', 0):
    raise SystemExit('This IMA-only CPU requires RV32IMA/Zicsr/Zifencei, ILP32 firmware without C.')
expected_gcc = os.environ.get('COREMARK_EXPECTED_GCC', '16.2.0')
if (m.get('compiler_target'), m.get('compiler_version')) != ('riscv32-unknown-elf', expected_gcc):
    raise SystemExit('Expected genuine riscv32-unknown-elf GCC ' + expected_gcc)
if m.get('coremark_upstream') != 'cfa9ab377835911f23d9b0831c7be302ed1f58de':
    raise SystemExit('Expected the immutable official CoreMark 1.0 source set.')
if not isinstance(m['cpu_hz'], int) or not 0 < m['cpu_hz'] <= 1000000000:
    raise SystemExit('Invalid firmware CPU frequency')
print(m['cpu_hz'])
PY
)
evidence_class=$(python3 - "$source" <<'PY'
import json, sys
from pathlib import Path
print(json.loads((Path(sys.argv[1]) / 'manifest.json').read_text())['evidence_class'])
PY
)
case "${COREMARK_VALIDATION:-auto}" in
  auto)
    if [[ "$evidence_class" == calibration ]]; then validation_mode=calibration
    else validation_mode=timed; fi ;;
  calibration|timed) validation_mode="$COREMARK_VALIDATION" ;;
  *) echo 'COREMARK_VALIDATION must be auto, calibration or timed' >&2; exit 2 ;;
esac
if [[ ( "$evidence_class" == calibration && "$validation_mode" != calibration ) ||
      ( "$evidence_class" == formal_candidate && "$validation_mode" != timed ) ]]; then
  echo 'CoreMark evidence class and requested checker mode differ' >&2
  exit 2
fi
if [[ "$evidence_class" != calibration && "$evidence_class" != formal_candidate ]]; then
  echo 'Unexpected CoreMark evidence class' >&2
  exit 2
fi
if [[ "$validation_mode" == timed ]]; then default_max_cycles=800000000
else default_max_cycles=20000000; fi
max_cycles="${COREMARK_MAX_CYCLES:-$default_max_cycles}"
mkdir -p "$output_root/scripts" "$build_root"
rtl=("$core_sv" "$root/coremark_test_soc/rtl/axi_bram_uart.v"
  "$root/coremark_test_soc/rtl/uart_tx_fifo.v"
  "$root/coremark_test_soc/rtl/coremark_soc_top.v"
  "$root/coremark_test_soc/sim/tb_coremark_soc.v")
sha256sum "${rtl[@]}" "$root"/scripts/meminit/*.hex >"$output_root/rtl-inputs.sha256"
"$vlt" --version >"$output_root/simulator-version.txt"
echo "CoreMark IMA: $validation_mode RTL simulation; host C++ flags $host_cxx_flags; limit $max_cycles cycles."
group_args=()
vlt_help=$("$vlt" --help 2>/dev/null || true)
if [[ "$vlt_help" == *--output-groups* ]]; then group_args=(--output-groups 0); fi
"$vlt" --binary --timing --assert "${group_args[@]}" -CFLAGS "$host_cxx_flags" -j "${COREMARK_JOBS:-2}" -Wno-fatal \
  --top-module tb_coremark_soc -GCPU_HZ="$cpu_hz" --Mdir "$build_root" \
  "${rtl[@]}" >"$output_root/build.log" 2>&1
simulator="$build_root/Vtb_coremark_soc"
if [[ ! -x "$simulator" && -x "$simulator.exe" ]]; then simulator="$simulator.exe"; fi
test -x "$simulator"
# Simulation owns copies; checked-in firmware inputs never receive run artifacts.
cp "$source"/{coremark.elf,coremark.bin,ram.hex,macros.txt,manifest.json,coremark_build_config.h} "$output_root/"
cp -R scripts/meminit "$output_root/scripts/"
if [[ "${COREMARK_BUILD_ONLY:-0}" == 1 ]]; then
  echo "COREMARK_MODEL_READY simulator=$simulator"
  exit 0
fi
python3 - "$simulator" "$output_root" "$max_cycles" "$host_cxx_flags" <<'PY'
import hashlib, json, subprocess, sys, time
from pathlib import Path
simulator, output, limit, host_cxx_flags = sys.argv[1:]
root = Path(output)
simulator_file = Path(simulator)
if not simulator_file.is_file() and simulator_file.with_suffix('.exe').is_file():
    simulator_file = simulator_file.with_suffix('.exe')
if not simulator_file.is_file():
    raise SystemExit('Compiled simulator executable is missing')
start = time.perf_counter()
with (root / 'run.log').open('w') as log:
    run = subprocess.run([simulator, '+max_cycles=' + str(int(limit))], cwd=root,
                         stdout=log, stderr=subprocess.STDOUT)
(root / 'runtime.json').write_text(json.dumps({
    'simulation_wall_seconds': time.perf_counter() - start,
    'max_cycles': int(limit), 'exit_code': run.returncode,
    'host_cxx_flags': host_cxx_flags,
    'simulator_sha256': hashlib.sha256(simulator_file.read_bytes()).hexdigest(),
}, indent=2) + '\n')
sys.exit(run.returncode)
PY
validation=()
case "$validation_mode" in
  calibration) validation=(--calibration) ;;
  timed) ;;
esac
python3 scripts/check_timed_coremark.py "$output_root" "${validation[@]}" >"$output_root/validation.txt"
cat "$output_root/result.json"
