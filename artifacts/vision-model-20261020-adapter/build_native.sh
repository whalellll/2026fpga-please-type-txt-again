#!/bin/sh
set -eu
repo=$1
out=$2
models=$3
target=$4
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
adapter="$repo/artifacts/vision-model-20261020-adapter"
hash_inputs() {
 sha256sum "$adapter"/runtime/*.c "$adapter"/runtime/*.h "$adapter/build_native.sh" \
  "$repo"/linux/vision/xq_mac.h "$repo"/linux/vision/xq_mac_linux.c \
  "$repo"/linux/vision/xq_roi.c "$repo"/linux/vision/xq_roi.h "$repo"/linux/vision/xq_grid.c \
  "$repo"/linux/vision/xq_grid.h "$repo"/linux/vision/xq_vision.c "$repo"/linux/vision/xq_vision.h \
  "$repo"/sw/xiangqi/xiangqi_search.c "$repo"/sw/xiangqi/xiangqi_search.h \
  "$repo"/sw/xiangqi/xiangqi_pikafish_link.c "$repo"/sw/xiangqi/xiangqi_pikafish_link.h \
  "$repo"/linux/mac_accel/pango_mac_uapi.h "$repo"/sw/bootloader/crc32_fast.c \
  "$repo"/sw/bootloader/crc32_fast.h "$repo"/artifacts/vision-model-20261020/geometry/geometry_reference.c \
  "$adapter/geometry_fallback/c_ref/geometry_ref.c" "$adapter/geometry_fallback/c_ref/geometry_ref.h" \
  "$models/native_parameters.h"
}
hash_inputs > "$out/source-before.sha256"
cc=cc
flags="-O3 -ffp-contract=off"
if [ "$target" = rv32 ]; then
 cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
 flags="-O2 -static -march=rv32ima -mabi=ilp32 -mstrict-align -ffp-contract=off -Wl,--strip-debug"
elif [ "$target" != host ]; then exit 2; fi
timing_flag=""
if [ "${XQ_NATIVE_TIMING:-0}" = 1 ]; then timing_flag="-DXQ_NATIVE_TIMING"; fi
printf 'target=%s\ncounter_timing=%s\n' "$target" "${XQ_NATIVE_TIMING:-0}" > "$out/runtime-config.txt"
"$cc" $flags $timing_flag -DXQ_NATIVE_DIRECT_PACK -Dxqm_matrix=xqn_resident_matrix -std=c11 -Wall -Wextra -Werror -I"$models" -I"$repo/linux/vision" \
 -I"$repo/linux/mac_accel" -I"$repo/sw/xiangqi" -I"$repo/sw/bootloader" \
 "$adapter/runtime/xq_native_worker.c" "$adapter/runtime/xq_native_graph.c" \
 "$adapter/runtime/xq_native_post.c" "$adapter/runtime/xq_int8_layer.c" \
 "$adapter/runtime/xq_native_geometry.c" "$adapter/geometry_fallback/c_ref/geometry_ref.c" \
 "$adapter/runtime/xq_resident_matrix.c" "$repo/linux/vision/xq_mac_linux.c" \
 "$repo/linux/vision/xq_roi.c" "$repo/linux/vision/xq_grid.c" "$repo/linux/vision/xq_vision.c" \
 "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.c" \
 "$repo/sw/bootloader/crc32_fast.c" -lm -o "$out/xq-native-worker"
sha256sum "$out/xq-native-worker" "$models/"*.xqm "$models/refinement_rng.bin" "$models/native_parameters.h" > "$out/SHA256SUMS.txt"
"$cc" --version > "$out/compiler.txt"
hash_inputs > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
if [ "$target" = rv32 ]; then
 /opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/xq-native-worker" > "$out/elf-inspection.txt"
fi
echo NATIVE_WORKER_BUILD_PASS "$target"
