#!/bin/sh
# Private software candidate only. Does not replace a boot/rootfs payload.
set -eu
repo=$1
out=$2
models=$3
target=$4
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
adapter="$repo/artifacts/vision-model-20261020-adapter"
runtime="$adapter/runtime"
v321="$repo/linux/picture_new"
mkdir -p "$out"
# Pack format/version is not a model identity. All three exact r14 packs must
# match together before building or packaging a candidate.
(cd "$models" && sha256sum -c "$v321/r14-models.sha256") > "$out/model-identity.txt"
hash_inputs() {
 sha256sum "$runtime/"*.c "$runtime/"*.h "$v321/"*.c "$v321/"*.h \
  "$v321/build_native_v321.sh" "$v321/r14-models.sha256" \
  "$v321/whole_layer_fast/vision32_layer.c" "$v321/upstream/adapter/runtime/xq_int8_layer.c" \
  "$v321/upstream/adapter/runtime/xq_int8_layer.h" \
  "$repo/linux/vision/"*.c "$repo/linux/vision/"*.h \
  "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_search.h" \
  "$repo/sw/xiangqi/xiangqi_pikafish_link.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.h" \
  "$repo/sw/bootloader/crc32_fast.c" "$repo/sw/bootloader/crc32_fast.h" \
  "$repo/linux/mac_accel/pango_mac_uapi.h" "$adapter/geometry_fallback/c_ref/geometry_ref.c" \
  "$adapter/geometry_fallback/c_ref/geometry_ref.h" "$models/"*.xqm \
  "$models/refinement_rng.bin" "$models/native_parameters.h"
}
hash_inputs > "$out/source-before.sha256"
cc=cc
flags="-O2 -ffp-contract=off -ffunction-sections -fdata-sections"
if [ "$target" = rv32 ]; then
 cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
 flags="$flags -static -march=rv32ima -mabi=ilp32 -mstrict-align -Wl,--strip-debug"
elif [ "$target" != host ]; then exit 2; fi
timing_flag=""
if [ "${XQ_NATIVE_TIMING:-0}" = 1 ]; then timing_flag="-DXQ_NATIVE_TIMING"; fi
printf 'target=%s\nbackend=vision32\ndense_pin=0\nno_fallback=1\ncounter_timing=%s\n' \
 "$target" "${XQ_NATIVE_TIMING:-0}" > "$out/runtime-config.txt"
"$cc" $flags $timing_flag -DXQ_NATIVE_VISION32 -std=c11 -Wall -Wextra -Werror \
 -I"$models" -I"$runtime" -I"$v321" -I"$repo/linux/vision" -I"$repo/linux/mac_accel" \
 -I"$repo/sw/xiangqi" -I"$repo/sw/bootloader" \
 "$runtime/xq_native_worker.c" "$runtime/xq_native_graph.c" "$runtime/xq_native_post.c" \
 "$runtime/xq_native_geometry.c" "$adapter/geometry_fallback/c_ref/geometry_ref.c" \
 "$v321/vision32_backend.c" "$v321/vision32_layer.c" \
 "$repo/linux/vision/xq_roi.c" "$repo/linux/vision/xq_grid.c" "$repo/linux/vision/xq_vision.c" \
 "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.c" \
 "$repo/sw/bootloader/crc32_fast.c" -Wl,--gc-sections -lm -o "$out/xq-native-worker"
# The unused legacy graph pin API is discarded by section GC. Neither the
# legacy resident implementation nor the legacy dense transport is linked.
"$cc" --version > "$out/compiler.txt"
sha256sum "$out/xq-native-worker" "$models/"*.xqm "$models/refinement_rng.bin" \
 "$models/native_parameters.h" > "$out/SHA256SUMS.txt"
hash_inputs > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
if [ "$target" = rv32 ]; then
 /opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/xq-native-worker" > "$out/elf-inspection.txt"
fi
echo V321_NATIVE_WORKER_BUILD_PASS "$target"
