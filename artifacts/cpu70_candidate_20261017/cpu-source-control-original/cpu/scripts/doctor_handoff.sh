#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for dep in python3 make g++ sha256sum; do command -v "$dep"; done
vlt="${VERILATOR:-verilator}"
prefix="${RISCV_PREFIX:-riscv32-unknown-elf-}"
command -v "$vlt"
"$vlt" --binary --timing --version
command -v "${prefix}gcc"
command -v "${prefix}objcopy"
"${prefix}gcc" --version | head -n 1
test "$("${prefix}gcc" -dumpmachine)" = riscv32-unknown-elf || { echo 'Expected a real riscv32-unknown-elf compiler target.' >&2; exit 1; }
test "$("${prefix}gcc" -dumpfullversion)" = 16.2.0 || { echo 'Expected GCC 16.2.0 for the recorded contest build.' >&2; exit 1; }
"${prefix}gcc" -march=rv32ima_zicsr_zifencei -mabi=ilp32 -nostdlib -x c -c /dev/null -o /dev/null
for file in work/coremark-ima/coremark.elf work/coremark-ima/ram.hex; do test -s "$file"; done
test -d scripts/meminit
python3 --version
printf 'HANDOFF_DOCTOR_PASS: simulation prerequisites found; run Emit to check Chisel/firtool.\n'
