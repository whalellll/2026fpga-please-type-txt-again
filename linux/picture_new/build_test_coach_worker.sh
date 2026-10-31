#!/bin/sh
# Isolated cancellation test. No model arithmetic, real driver or board access.
set -eu
repo=$1;out=$2;models=$3;target=$4
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
board_exposure=${XQ_BOARD_EXPOSURE_R27:-0}
case "$board_exposure:${XQ_GRID_RECOVERY:-0}:${XQ_HWC_RGB8_DIRECT:-0}" in
 0:*) ;;
 1:1:1) ;;
 *) echo XQ_BOARD_EXPOSURE_R27_invalid_configuration >&2;exit 2;;
esac
exposure_retry=${XQ_EXPOSURE_RETRY_R29:-0}
case "$exposure_retry:$board_exposure" in
 0:*) ;; 1:1) ;; *) echo XQ_EXPOSURE_RETRY_R29_invalid_configuration >&2;exit 2;;
esac
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
exact_word_input=${XQ_EXACT_WORD_INPUT:-0}
case "$exact_word_input" in 0) ;; 1) test "$exact_enabled" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_EXACT_WORD_INPUT=$exact_word_input"
exact_word_output=${XQ_EXACT_WORD_OUTPUT:-0}
case "$exact_word_output" in 0) ;; 1) test "$exact_enabled" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_EXACT_WORD_OUTPUT=$exact_word_output"
geometry_fast=${XQ_GEOMETRY_FAST:-0}
geometry_arith=${XQ_GEOMETRY_ARITH:-0}
geometry_add=${XQ_GEOMETRY_ADD:-0}
case "$geometry_fast:$geometry_arith:$geometry_add" in [01]:[01]:[01]) ;; *) exit 2;; esac
if [ "$geometry_arith" = 1 ];then test "$geometry_fast" = 1;fi
if [ "$geometry_add" = 1 ];then test "$geometry_arith" = 1;fi
flags="$flags -DXQ_GEOMETRY_FAST=$geometry_fast -DXQ_GEOMETRY_ARITH=$geometry_arith -DXQ_GEOMETRY_ADD=$geometry_add"
geometry_compact=${XQ_GEOMETRY_COMPACT:-0}
geometry_selective=${XQ_GEOMETRY_SELECTIVE:-0}
case "$geometry_compact:$geometry_selective" in [01]:[01]) ;; *) exit 2;; esac
if [ "$geometry_compact" = 1 ];then test "$geometry_fast" = 1;fi
if [ "$geometry_selective" = 1 ];then test "$geometry_arith" = 1;fi
flags="$flags -DXQ_GEOMETRY_COMPACT=$geometry_compact -DXQ_GEOMETRY_SELECTIVE=$geometry_selective"
geometry_seed_bound=${XQ_GEOMETRY_SEED_BOUND:-0}
case "$geometry_seed_bound" in 0) ;; 1) test "$geometry_fast" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_GEOMETRY_SEED_BOUND=$geometry_seed_bound"
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
word_input_enabled=${XQ_HWC_WORD_INPUT:-0}
case "$word_input_enabled" in 0) ;; 1) test "${XQ_HWC_DETECTOR:-0}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_WORD_INPUT=$word_input_enabled"
tile_export_enabled=${XQ_HWC_TILE_EXPORT:-0}
case "$tile_export_enabled" in 0) ;; 1) test "${XQ_HWC_DETECTOR:-0}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_TILE_EXPORT=$tile_export_enabled"
tail_columns_enabled=${XQ_HWC_TAIL_COLUMNS:-0}
case "$tail_columns_enabled" in 0) ;; 1) test "${XQ_HWC_DETECTOR:-0}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_TAIL_COLUMNS=$tail_columns_enabled"
concat_view_enabled=${XQ_HWC_CONCAT_VIEW:-0}
case "$concat_view_enabled" in 0) ;; 1) test "${XQ_HWC_DETECTOR:-0}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_CONCAT_VIEW=$concat_view_enabled"
rgb8_direct_enabled=${XQ_HWC_RGB8_DIRECT:-0}
case "$rgb8_direct_enabled" in 0) ;; 1) test "${XQ_HWC_DETECTOR:-0}" = 1 ;; *) exit 2;; esac
flags="$flags -DXQ_HWC_RGB8_DIRECT=$rgb8_direct_enabled"
lazy_box_enabled=${XQ_DETECTOR_LAZY_BOX:-0}
corner_table_enabled=${XQ_BOARD_CORNER_TABLE:-0}
case "$lazy_box_enabled:$corner_table_enabled" in [01]:[01]) ;; *) exit 2;; esac
if [ "$corner_table_enabled" = 1 ];then test "${XQ_INTEGER_GRAPH:-1}" = 1;fi
flags="$flags -DXQ_DETECTOR_LAZY_BOX=$lazy_box_enabled -DXQ_BOARD_CORNER_TABLE=$corner_table_enabled"
case "${XQ_HWC_DETECTOR:-0}" in
 0) ;;
 1) test "${XQ_INTEGER_GRAPH:-1}" = 1
    test -f "$models/detector.xqi"
    flags="$flags -DXQ_HWC_DETECTOR=1"
    set -- "$@" "$coach/hwc_fast/adapter.c" "$runtime/xq_sha256.c" ;;
 *) exit 2 ;;
esac
worker="$runtime/xq_native_worker.c"
grid_plan_fast=${XQ_GRID_PLAN_FAST:-0}
grid_model_guard=${XQ_GRID_MODEL_GUARD:-0}
case "$grid_plan_fast:$grid_model_guard" in [01]:[01]) ;; *) exit 2;; esac
if [ "$grid_plan_fast:$grid_model_guard" != 0:0 ];then test "${XQ_GRID_RECOVERY:-0}" = 1;fi
flags="$flags -DXQ_GRID_PLAN_FAST=$grid_plan_fast -DXQ_GRID_MODEL_GUARD=$grid_model_guard"
case "${XQ_GRID_RECOVERY:-0}" in
 0) ;;
 1) worker="$coach/coach_grid_worker.c";set -- "$@" "$coach/board_grid_recovery.c" ;;
 *) exit 2;;
esac
if [ "${XQ_GRID_RECOVERY:-0}" = 0 ] && [ "$lazy_box_enabled:$rgb8_direct_enabled" != 0:0 ];then worker="$coach/coach_decode_worker.c";fi
geometry_cancel=${XQ_GEOMETRY_CANCEL:-0}
case "$geometry_cancel" in
 0) ;;
 1) test "${XQ_GRID_RECOVERY:-0}:$geometry_fast:$geometry_arith:$geometry_compact:$geometry_selective" = 1:1:1:1:1
    python3 "$repo/scripts/generate_picture_geometry_cancel.py" --output "$out/geometry-cancellable.c"
    set -- "$@" "-DXQ_GEOMETRY_CANCEL_SOURCE=\"$out/geometry-cancellable.c\"" ;;
 *) exit 2;;
esac
flags="$flags -DXQ_GEOMETRY_CANCEL=$geometry_cancel"
geometry_fused=${XQ_GEOMETRY_FUSED:-0}
case "$geometry_fused" in
 0) ;;
 1) test "${XQ_GRID_RECOVERY:-0}:$geometry_fast:$geometry_arith:$geometry_compact:$geometry_selective" = 1:1:1:1:1
    geometry_input="$coach/geometry_locality.c"
    if [ "$geometry_cancel" = 1 ];then geometry_input="$out/geometry-cancellable.c";fi
    python3 "$repo/scripts/generate_picture_geometry_fused.py" --input "$geometry_input" --output "$out/geometry-fused.c"
    set -- "$@" "-DXQ_GEOMETRY_FUSED_SOURCE=\"$out/geometry-fused.c\"" ;;
 *) exit 2;;
esac
flags="$flags -DXQ_GEOMETRY_FUSED=$geometry_fused"
if [ "$board_exposure" = 1 ];then set -- "$@" "$coach/board_exposure.c";fi
flags="$flags -DXQ_BOARD_EXPOSURE_R27=$board_exposure"
flags="$flags -DXQ_EXPOSURE_RETRY_R29=$exposure_retry"
"$cc" $flags -std=c11 -Wall -Wextra -Werror -DXQ_NATIVE_COACH -DXQ_NATIVE_VISION32 \
 -I"$models" -I"$runtime" -I"$coach" -I"$repo/linux/vision" -I"$repo/linux/mac_accel" \
 -I"$repo/sw/xiangqi" -I"$repo/sw/bootloader" \
 "$worker" "$graph" "$@" "$runtime/xq_native_geometry.c" \
 "$repo/artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref/geometry_ref.c" \
 "$coach/coach_geometry.c" "$coach/coach_model_guard.c" "$coach/coach_protocol.c" "$coach/coach_driver_guard.c" \
 "$coach/coach_lifecycle_mock.c" "$coach/vision32_backend.c" "$coach/vision32_layer.c" \
 "$repo/linux/vision/xq_roi.c" "$repo/linux/vision/xq_grid.c" "$repo/linux/vision/xq_vision.c" \
 "$repo/sw/xiangqi/xiangqi_search.c" "$repo/sw/xiangqi/xiangqi_pikafish_link.c" \
 "$repo/sw/bootloader/crc32_fast.c" -Wl,--wrap=ioctl -Wl,--wrap=xqn_run \
 -Wl,--wrap=xqm_linux_open -Wl,--wrap=xqm_linux_close -Wl,--gc-sections -lm \
 -o "$out/xq-coach-worker-hostmock"
echo XQCOACH_LIFECYCLE_HOSTMOCK_BUILD_PASS "$target"
