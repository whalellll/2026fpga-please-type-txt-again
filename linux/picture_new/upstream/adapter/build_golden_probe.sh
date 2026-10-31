#!/bin/sh
set -eu
repo=$1
out=$2
target=$3
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
adapter="$repo/artifacts/vision-model-20261020-adapter/runtime"
cc=cc
flags='-O3 -ffp-contract=off'
if [ "$target" = rv32 ]; then
 cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
 flags='-O2 -static -march=rv32ima -mabi=ilp32 -mstrict-align -ffp-contract=off -Wl,--strip-debug'
fi
"$cc" $flags -Dxqm_matrix=xqn_resident_matrix -std=c11 -Wall -Wextra -Werror \
 -I"$repo/linux/vision" -I"$repo/linux/mac_accel" -I"$repo/sw/bootloader" \
 "$adapter/xq_golden_probe.c" "$adapter/xq_native_graph.c" "$adapter/xq_int8_layer.c" "$adapter/xq_sha256.c" \
 "$adapter/xq_resident_matrix.c" "$repo/linux/vision/xq_mac_linux.c" "$repo/sw/bootloader/crc32_fast.c" \
 -lm -o "$out/xq-golden-probe"
sha256sum "$adapter/"*.[ch] "$out/xq-golden-probe" > "$out/SHA256SUMS.txt"
echo GOLDEN_PROBE_BUILD_PASS "$target"
