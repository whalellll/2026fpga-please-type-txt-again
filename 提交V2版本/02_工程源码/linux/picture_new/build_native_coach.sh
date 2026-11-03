#!/bin/sh
# New explicit stateless coach candidate; legacy worker builders stay unchanged.
set -eu
repo=$1;out=$2;models=$3;target=$4
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
runtime="$repo/artifacts/vision-model-20261020-adapter/runtime"
fallback="$repo/artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref"
coach="$repo/linux/picture_new"
(cd "$models" && sha256sum -c "$coach/r14-models.sha256") > "$out/model-identity.txt"
hash_inputs() {
 sha256sum "$runtime/"*.c "$runtime/"*.h "$coach/"*.c "$coach/"*.h \
  "$coach/build_native_coach.sh" "$coach/r14-models.sha256" \
  "$coach/whole_layer_fast/vision32_layer.c" "$coach/upstream/adapter/runtime/xq_int8_layer.c" \
  "$coach/upstream/adapter/runtime/xq_int8_layer.h" \
  "$repo/linux/vision/"*.c "$repo/linux/vision/"*.h \
  "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_search.h" \
  "$repo/sw/xiangqi/xiangqi_pikafish_link.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.h" \
  "$repo/sw/bootloader/crc32_fast.c" "$repo/sw/bootloader/crc32_fast.h" \
  "$repo/artifacts/vision-model-20261020/geometry/geometry_reference.c" \
  "$repo/linux/mac_accel/pango_mac_uapi.h" "$fallback/geometry_ref.c" "$fallback/geometry_ref.h" \
  "$models/"*.xqm "$models/refinement_rng.bin" "$models/native_parameters.h"
 if [ "${XQ_HWC_DETECTOR:-0}" = 1 ];then
  sha256sum "$coach/hwc_fast/adapter.c" "$coach/hwc_fast/adapter.h" \
   "$coach/hwc_fast/integer_hwc.c" "$coach/hwc_fast/integer_hwc.h" \
   "$coach/hwc_fast/input_quant.c" "$coach/hwc_fast/input_quant.h" "$models/detector.xqi"
 fi
}
hash_inputs > "$out/source-before.sha256"
cc=cc;flags='-O2 -ffp-contract=off -ffunction-sections -fdata-sections'
if [ "$target" = rv32 ]; then
 cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
 flags="$flags -static -march=rv32ima -mabi=ilp32 -mstrict-align -Wl,--strip-debug"
elif [ "$target" != host ]; then exit 2; fi
exact_enabled=${XQ_EXACT_EPILOGUE:-1}
gray_enabled=${XQ_GEOMETRY_GRAY_TABLE:-1}
row_enabled=${XQ_GEOMETRY_ROW_LOCAL:-0}
case "$exact_enabled:$gray_enabled:$row_enabled" in [01]:[01]:[01]) ;; *) exit 2;; esac
flags="$flags -DXQ_EXACT_EPILOGUE=$exact_enabled -DXQ_GEOMETRY_GRAY_TABLE=$gray_enabled -DXQ_GEOMETRY_ROW_LOCAL=$row_enabled"
geometry_fast=${XQ_GEOMETRY_FAST:-0}
geometry_arith=${XQ_GEOMETRY_ARITH:-0}
geometry_add=${XQ_GEOMETRY_ADD:-0}
case "$geometry_fast:$geometry_arith:$geometry_add" in [01]:[01]:[01]) ;; *) exit 2;; esac
if [ "$geometry_arith" = 1 ];then test "$geometry_fast" = 1;fi
if [ "$geometry_add" = 1 ];then test "$geometry_arith" = 1;fi
flags="$flags -DXQ_GEOMETRY_FAST=$geometry_fast -DXQ_GEOMETRY_ARITH=$geometry_arith -DXQ_GEOMETRY_ADD=$geometry_add"
bilinear_enabled=${XQ_FAST_FP32_BILINEAR:-0}
case "$bilinear_enabled" in 0) ;; 1) test "${XQ_INTEGER_GRAPH:-1}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_FAST_FP32_BILINEAR=$bilinear_enabled"
graph="$runtime/xq_native_graph.c"
set --
case "${XQ_INTEGER_GRAPH:-1}" in
 0) ;;
 1) graph="$coach/graph_runtime.c"
    set -- "$coach/graph_tensor.c" "$coach/graph_profile.c"
    flags="$flags -DXQ_INTEGER_CARRIER=1 -DXQ_FAST_REQUANT=1"
    case "${XQ_CLASSIFIER_S16:-1}" in
     0) ;; 1) flags="$flags -DXQ_CLASSIFIER_S16=1";set -- "$@" "$coach/graph_ops.c" ;; *) exit 2;;
    esac
    case "${XQ_GRAPH_PROFILE:-0}" in
     0) ;; 1) flags="$flags -DXQ_GRAPH_PROFILE" ;; *) exit 2;;
    esac ;;
 *) exit 2;;
esac
hwc_enabled=${XQ_HWC_DETECTOR:-0}
rgb_quant_enabled=${XQ_HWC_RGB_QUANT:-0}
case "$rgb_quant_enabled" in 0) ;; 1) test "$hwc_enabled" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_RGB_QUANT=$rgb_quant_enabled"
case "$hwc_enabled" in
 0) ;;
 1) test "${XQ_INTEGER_GRAPH:-1}" = 1
    test -f "$models/detector.xqi"
    flags="$flags -DXQ_HWC_DETECTOR=1"
    set -- "$@" "$coach/hwc_fast/adapter.c" "$runtime/xq_sha256.c"
    sha256sum "$models/detector.xqi" > "$out/hwc-model-before.sha256" ;;
 *) exit 2;;
esac
worker="$runtime/xq_native_worker.c"
grid_enabled=${XQ_GRID_RECOVERY:-0}
case "$grid_enabled" in
 0) ;;
 1) worker="$coach/coach_grid_worker.c";set -- "$@" "$coach/board_grid_recovery.c" ;;
 *) exit 2;;
esac
"$cc" $flags -DXQ_NATIVE_VISION32 -DXQ_NATIVE_COACH -DXQ_NATIVE_TIMING -std=c11 -Wall -Wextra -Werror \
 -I"$models" -I"$runtime" -I"$coach" -I"$repo/linux/vision" -I"$repo/linux/mac_accel" \
 -I"$repo/sw/xiangqi" -I"$repo/sw/bootloader" \
 "$worker" "$graph" "$@" \
 "$runtime/xq_native_geometry.c" "$fallback/geometry_ref.c" \
 "$coach/coach_geometry.c" "$coach/coach_protocol.c" "$coach/coach_driver_guard.c" \
 "$coach/vision32_backend.c" "$coach/vision32_layer.c" \
 "$repo/linux/vision/xq_roi.c" "$repo/linux/vision/xq_grid.c" "$repo/linux/vision/xq_vision.c" \
 "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.c" \
 "$repo/sw/bootloader/crc32_fast.c" -Wl,--wrap=ioctl -Wl,--gc-sections -lm -o "$out/xq-coach-worker"
printf 'target=%s\nbackend=rv32-v321-coach\nprotocol=XQ_COACH_RESULT_V1\nstateless=1\nmanual=0\ndense_pin=0\nno_fallback=1\n' "$target" > "$out/runtime-config.txt"
printf 'integer_carrier=%s\nnonconv_fp32=1\ninteger_spec_ready=1\ngraph_profile=%s\n' \
 "${XQ_INTEGER_GRAPH:-1}" "${XQ_GRAPH_PROFILE:-0}" >> "$out/runtime-config.txt"
classifier_enabled=0
if [ "${XQ_INTEGER_GRAPH:-1}" = 1 ];then classifier_enabled=${XQ_CLASSIFIER_S16:-1};fi
printf 'classifier_s16_gap=%s\ndetector_integer_graph=%s\ndetector_hwc_candidate=%s\nboard_integer_graph=0\n' "$classifier_enabled" "$hwc_enabled" "$hwc_enabled" >> "$out/runtime-config.txt"
printf 'exact_epilogue=%s\ngeometry_gray_table=%s\ngeometry_row_local=%s\n' "$exact_enabled" "$gray_enabled" "$row_enabled" >> "$out/runtime-config.txt"
printf 'grid_recovery_candidate=%s\n' "$grid_enabled" >> "$out/runtime-config.txt"
printf 'exact_fp32_bilinear_candidate=%s\n' "$bilinear_enabled" >> "$out/runtime-config.txt"
printf 'hwc_rgb_quant_candidate=%s\n' "$rgb_quant_enabled" >> "$out/runtime-config.txt"
printf 'geometry_fast=%s\ngeometry_arith=%s\ngeometry_add=%s\n' "$geometry_fast" "$geometry_arith" "$geometry_add" >> "$out/runtime-config.txt"
if [ "$hwc_enabled" = 1 ];then
 sha256sum "$models/detector.xqi" > "$out/hwc-model-after.sha256"
 cmp "$out/hwc-model-before.sha256" "$out/hwc-model-after.sha256"
fi
"$cc" --version > "$out/compiler.txt"
hash_inputs > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
if [ "$target" = rv32 ]; then
 /opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/xq-coach-worker" > "$out/elf-inspection.txt"
fi
sha256sum "$out/xq-coach-worker" > "$out/SHA256SUMS.txt"
echo V321_STATELESS_COACH_WORKER_BUILD_PASS "$target"
