#!/bin/sh
set -eu

port=${PIKAFISH_PORT:?}
artifacts=${PIKAFISH_ARTIFACTS:?}
log_dir=${PIKAFISH_LOG_DIR:?}
model=${PIKAFISH_MODEL:?}
reference_model=${PIKAFISH_REFERENCE_MODEL:?}
attacks=${PIKAFISH_ATTACKS:?}
cross=/opt/toolchain/bin/riscv32-linux-musl
rv32="$artifacts/pikafish-rv32"
native="$artifacts/pikafish-reference-x86_64"
view_native="$artifacts/pikafish-view-reference-x86_64"
gui="$artifacts/xiangqi-pikafish-gui"
input_test="$artifacts/xiangqi-input-test"

g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
    -I"$port" "$port/test_portable_u128.cpp" -o /tmp/test_portable_u128
/tmp/test_portable_u128
"$artifacts/pikafish-stagea-pack-test-x86_64"
qemu-riscv32 "$artifacts/pikafish-stagea-pack-test-rv32"
"$artifacts/pikafish-attacks-test-x86_64" "$attacks"
qemu-riscv32 "$artifacts/pikafish-attacks-test-rv32" "$attacks"

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
strings "$rv32" | grep -q 'PIKAFISH_STAGEA_ACCEL_ACTIVE'
strings "$rv32" | grep -q 'PIKAFISH_STAGEB_ACCEL_ACTIVE'

file "$gui" | grep -q 'ELF 32-bit.*RISC-V.*statically linked'
"$cross-readelf" -A "$gui" | grep -q 'Tag_RISCV_arch:.*rv32i.*m.*a'
if "$cross-readelf" -l "$gui" | grep -q 'INTERP'; then
    echo 'RV32 GUI unexpectedly has a dynamic interpreter' >&2
    exit 1
fi
strings "$gui" | grep -q 'PIKAFISH_STAGEA_ACCEL_ACTIVE'
strings "$gui" | grep -q 'PIKAFISH_STAGEB_ACCEL_ACTIVE'
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

python3 "$port/uci_regression.py" \
    --native "$native" \
    --rv32 "$rv32" \
    --model "$model" \
    --reference-model "$reference_model" \
    --log-dir "$log_dir" \
    --nodes "${PIKAFISH_TEST_NODES:-1000}" \
    --timeout "${PIKAFISH_TEST_TIMEOUT:-300}"

python3 "$port/uci_regression.py" \
    --native "$view_native" \
    --rv32 "$rv32" \
    --model "$model" \
    --log-dir "$log_dir/direct-view" \
    --nodes "${PIKAFISH_TEST_NODES:-1000}" \
    --timeout "${PIKAFISH_TEST_TIMEOUT:-300}"

grep -q 'PIKAFISH_PFF1_VIEW_READY direct_bytes=67548352 mlp_direct_bytes=563264' \
    "$log_dir/direct-view/pikafish-native-uci.log"
grep -q 'PIKAFISH_PFF1_MLPS_STACK_READY stack=15 bytes=563264' \
    "$log_dir/direct-view/pikafish-native-uci.log"

echo PIKAFISH_RV32_REGRESSION_PASS
