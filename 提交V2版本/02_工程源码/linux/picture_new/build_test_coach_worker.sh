#!/bin/sh
# Isolated cancellation test. No model arithmetic, real driver or board access.
set -eu
repo=$1;out=$2;models=$3;target=$4
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out";mkdir -p "$out"
runtime="$repo/artifacts/vision-model-20261020-adapter/runtime"
coach="$repo/linux/picture_new"
cc=gcc;flags='-O2 -ffp-contract=off -ffunction-sections -fdata-sections'
if [ "$target" = rv32 ];then
 cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
 flags="$flags -static -march=rv32ima -mabi=ilp32 -mstrict-align"
elif [ "$target" != host ];then exit 2;fi
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
 0) ;; 1) graph="$coach/graph_runtime.c"
         set -- "$coach/graph_tensor.c"
         flags="$flags -DXQ_INTEGER_CARRIER=1 -DXQ_FAST_REQUANT=1"
         case "${XQ_CLASSIFIER_S16:-1}" in
          0) ;; 1) flags="$flags -DXQ_CLASSIFIER_S16=1";set -- "$@" "$coach/graph_ops.c" ;; *) exit 2;;
         esac ;;
 *) exit 2;;
esac
rgb_quant_enabled=${XQ_HWC_RGB_QUANT:-0}
case "$rgb_quant_enabled" in 0) ;; 1) test "${XQ_HWC_DETECTOR:-0}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_RGB_QUANT=$rgb_quant_enabled"
case "${XQ_HWC_DETECTOR:-0}" in
 0) ;;
 1) test "${XQ_INTEGER_GRAPH:-1}" = 1
    test -f "$models/detector.xqi"
    flags="$flags -DXQ_HWC_DETECTOR=1"
    set -- "$@" "$coach/hwc_fast/adapter.c" "$runtime/xq_sha256.c" ;;
 *) exit 2 ;;
esac
worker="$runtime/xq_native_worker.c"
case "${XQ_GRID_RECOVERY:-0}" in
 0) ;;
 1) worker="$coach/coach_grid_worker.c";set -- "$@" "$coach/board_grid_recovery.c" ;;
 *) exit 2;;
esac
"$cc" $flags -std=c11 -Wall -Wextra -Werror -DXQ_NATIVE_COACH -DXQ_NATIVE_VISION32 \
 -I"$models" -I"$runtime" -I"$coach" -I"$repo/linux/vision" -I"$repo/linux/mac_accel" \
 -I"$repo/sw/xiangqi" -I"$repo/sw/bootloader" \
 "$worker" "$graph" "$@" "$runtime/xq_native_geometry.c" \
 "$repo/artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref/geometry_ref.c" \
 "$coach/coach_geometry.c" "$coach/coach_protocol.c" "$coach/coach_driver_guard.c" \
 "$coach/coach_lifecycle_mock.c" "$coach/vision32_backend.c" "$coach/vision32_layer.c" \
 "$repo/linux/vision/xq_roi.c" "$repo/linux/vision/xq_grid.c" "$repo/linux/vision/xq_vision.c" \
 "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.c" \
 "$repo/sw/bootloader/crc32_fast.c" -Wl,--wrap=ioctl -Wl,--wrap=xqn_run \
 -Wl,--wrap=xqm_linux_open -Wl,--wrap=xqm_linux_close -Wl,--gc-sections -lm \
 -o "$out/xq-coach-worker-hostmock"
echo XQCOACH_LIFECYCLE_HOSTMOCK_BUILD_PASS "$target"
