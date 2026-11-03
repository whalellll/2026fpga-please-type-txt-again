#!/bin/sh
set -eu
repo=$1
out=$2
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
adapter="$repo/artifacts/vision-model-20261020-adapter"
reference="$adapter/geometry_fallback/c_ref"
vectors="$adapter/geometry_fallback/test_vectors/vectors.tsv"
sha256sum "$reference/geometry_ref.c" "$reference/geometry_ref.h" "$reference/test_harness.c" \
 "$vectors" "$adapter/runtime/xq_piece_fit_probe.c" > "$out/source-before.sha256"
cc -O2 -ffp-contract=off -fno-fast-math -std=c11 -Wall -Wextra \
 "$adapter/runtime/xq_piece_fit_probe.c" "$reference/geometry_ref.c" -lm -o "$out/host-probe"
/opt/toolchain/bin/riscv32-linux-musl-gcc -O2 -static -s -march=rv32ima -mabi=ilp32 \
 -mstrict-align -ffp-contract=off -fno-fast-math -std=c11 -Wall -Wextra \
 "$adapter/runtime/xq_piece_fit_probe.c" "$reference/geometry_ref.c" -lm -o "$out/rv32-probe"
"$out/host-probe" "$vectors" > "$out/host-output.txt"
sha256sum "$reference/geometry_ref.c" "$reference/geometry_ref.h" "$reference/test_harness.c" \
 "$vectors" "$adapter/runtime/xq_piece_fit_probe.c" > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
/opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/rv32-probe" > "$out/elf-inspection.txt"
sha256sum "$out/host-output.txt" "$out/rv32-probe" > "$out/SHA256SUMS.txt"
tail -n 1 "$out/host-output.txt"
echo PIECE_FIT_REFERENCE_PROBE_BUILD_PASS
