#!/bin/sh
set -eu

cross=/opt/toolchain/bin/riscv32-linux-musl
rv32=/artifacts/pikafish-rv32
native=/artifacts/pikafish-reference-x86_64
gui=/artifacts/xiangqi-pikafish-gui
input_test=/artifacts/xiangqi-input-test

g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
    -I/port /port/test_portable_u128.cpp -o /tmp/test_portable_u128
/tmp/test_portable_u128

file "$rv32" | grep -q 'ELF 32-bit.*RISC-V.*statically linked'
"$cross-readelf" -h "$rv32" | grep -q 'Class:.*ELF32'
"$cross-readelf" -h "$rv32" | grep -q 'Machine:.*RISC-V'
if "$cross-readelf" -h "$rv32" | grep -Eq 'single-float ABI|double-float ABI|quad-float ABI'; then
    echo 'RV32 binary unexpectedly uses a hard-float ABI' >&2
    exit 1
fi
"$cross-readelf" -A "$rv32" | grep -q 'Tag_RISCV_arch:.*rv32i.*m.*a'
if "$cross-readelf" -l "$rv32" | grep -q 'INTERP'; then
    echo 'RV32 binary unexpectedly has a dynamic interpreter' >&2
    exit 1
fi

file "$gui" | grep -q 'ELF 32-bit.*RISC-V.*statically linked'
"$cross-readelf" -A "$gui" | grep -q 'Tag_RISCV_arch:.*rv32i.*m.*a'
if "$cross-readelf" -l "$gui" | grep -q 'INTERP'; then
    echo 'RV32 GUI unexpectedly has a dynamic interpreter' >&2
    exit 1
fi
file "$input_test" | grep -q 'ELF 32-bit.*RISC-V.*statically linked'
"$cross-readelf" -A "$input_test" | grep -q 'Tag_RISCV_arch:.*rv32i.*m.*a'
if "$cross-readelf" -l "$input_test" | grep -q 'INTERP'; then
    echo 'RV32 input test unexpectedly has a dynamic interpreter' >&2
    exit 1
fi
set +e
gui_output=$(qemu-riscv32 "$gui" 2>&1)
gui_status=$?
set -e
test "$gui_status" -eq 3
printf '%s\n' "$gui_output" | grep -q 'framebuffer/HID initialization failed'

set +e
input_output=$(qemu-riscv32 "$input_test" 2>&1)
input_status=$?
set -e
test "$input_status" -eq 3
printf '%s\n' "$input_output" | grep -q 'SOFTWARE_SELFTEST_PASS'
printf '%s\n' "$input_output" | grep -q 'open /dev/mem'

python3 /port/uci_regression.py \
    --native "$native" \
    --rv32 "$rv32" \
    --model /model/pikafish.nnue \
    --log-dir /artifacts \
    --nodes "${PIKAFISH_TEST_NODES:-1000}" \
    --timeout "${PIKAFISH_TEST_TIMEOUT:-300}"

echo PIKAFISH_RV32_REGRESSION_PASS
