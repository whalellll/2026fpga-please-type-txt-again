#!/usr/bin/env bash
set -euo pipefail
cd /g/fpga/build/pds25-cpu120-20261101-03/cpu-source/cpu
root="$PWD"
core_sv="${CORE_TEST_SV:-$root/generated/sim/CoreTop.sv}"
# Overrides select a copy of the current recorded simulation export, never an
# untracked older CPU. Historical result directories remain read-only evidence.
python3 scripts/verify_generated.py check --simulation "$core_sv"
python3 "${CPU_TEST_GENERATOR:-scripts/generate_cpu_test.py}"
out="$root/work/cpu-test"
mkdir -p "$out/scripts" work/logs
cp -R scripts/meminit "$out/scripts/"
prefix="${RISCV_PREFIX:-riscv32-unknown-elf-}"
if ! command -v "${prefix}gcc" >/dev/null; then prefix="$HOME/.local/bin/riscv32-unknown-elf-"; fi
test "$("${prefix}gcc" -dumpmachine)" = riscv32-unknown-elf || { echo 'Expected compiler target riscv32-unknown-elf.' >&2; exit 1; }
test "$("${prefix}gcc" -dumpfullversion)" = 16.2.0 || { echo 'Expected GCC 16.2.0.' >&2; exit 1; }
"${prefix}gcc" -march="${CPU_TEST_MARCH:-rv32ima_zicsr_zifencei}" -mabi=ilp32 -mno-relax -nostdlib -nostartfiles \
  -Wl,--build-id=none -T coremark_test_soc/sw/link.ld "$out/test.S" -o "$out/test.elf"
"${prefix}objcopy" -O binary "$out/test.elf" "$out/test.bin"
python3 - "$out" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); b=(p/'test.bin').read_bytes()
assert len(b)<65536
b=b.ljust(131072,b'\0')
(p/'ram.hex').write_text(''.join(f'{int.from_bytes(b[i:i+4],"little"):08x}\n' for i in range(0,len(b),4)))
PY
vlt="${VERILATOR:-verilator}"
if ! command -v "$vlt" >/dev/null; then vlt="$HOME/.local/bin/verilator"; fi
# Recent Verilator versions group C++ files according to -j. Keep smaller
# translation units on this bounded-memory native build; older versions omit it.
group_args=()
vlt_help=$("$vlt" --help 2>/dev/null || true)
if [[ "$vlt_help" == *--output-groups* ]]; then group_args=(--output-groups 0); fi
"$vlt" --binary --timing --assert "${group_args[@]}" -j "${CPU_TEST_JOBS:-2}" -Wno-fatal --top-module tb_cpu_architecture \
  --Mdir "$root/work/verilator-cpu-test-${CPU_TEST_CASE_ID}" "$core_sv" \
  "$root/coremark_test_soc/rtl/axi_bram_uart.v" "$root/coremark_test_soc/rtl/uart_tx_fifo.v" \
  "${CPU_TEST_SOC_RTL:-$root/coremark_test_soc/rtl/coremark_soc_top.v}" "$out/tb_cpu_architecture.v" >work/logs/cpu-test-build.log 2>&1
(cd "$out"; "$root/work/verilator-cpu-test-${CPU_TEST_CASE_ID}/Vtb_cpu_architecture" +max_cycles=3000000 >run.log 2>&1)
grep 'TB_CPU_ARCHITECTURE_PASS' "$out/run.log"
if grep -q 'FAIL\|Error\|fatal' "$out/run.log"; then cat "$out/run.log"; exit 1; fi
