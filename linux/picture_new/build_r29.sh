#!/bin/sh
# Assemble committed, unchanged engineering inputs; no cache or board access.
set -eu
if [ "$#" -ne 2 ];then echo 'Usage: build_r29.sh ABS_REPO ABS_REPO/build/NEW_OUTPUT' >&2;exit 2;fi
repo=$1
out=$2
case "$repo:$out" in *'/../'*|*'/./'*|*'//'*) echo 'Use normalized absolute paths' >&2;exit 2;;esac
case "$repo" in /*) ;; *) exit 2;;esac
case "$out" in "$repo"/build/*) ;; *) echo 'Output must be a new repository build directory' >&2;exit 2;;esac
test ! -e "$out"
test ! -L "$out"
command -v sha256sum >/dev/null
command -v realpath >/dev/null
physical_repo=$(cd "$repo" && pwd -P)
physical_out=$(realpath -m "$out")
case "$physical_out" in "$physical_repo"/build/*) ;; *) echo 'Output resolves outside repository build directory' >&2;exit 2;;esac
test -x /opt/toolchain/bin/riscv32-linux-musl-gcc
test -x /opt/toolchain/bin/riscv32-linux-musl-strip
mkdir -p "$out/models"
for name in board.xqm detector.xqm classifier.xqm;do
 cp "$repo/artifacts/main70_20261027/model-source/native_int8/$name" "$out/models/$name"
done
for name in detector.xqi refinement_rng.bin native_parameters.h;do
 cp "$repo/prebuilt/picture-r29-inputs/$name" "$out/models/$name"
done
(cd "$out/models" && sha256sum -c "$repo/prebuilt/picture-r29-inputs/SHA256SUMS.txt")
export XQ_EXACT_WORD_INPUT=1
export XQ_EXACT_WORD_OUTPUT=1
export XQ_GEOMETRY_FUSED=1
export XQ_GEOMETRY_CANCEL=1
export XQ_HWC_CONCAT_VIEW=1
export XQ_HWC_DETECTOR=1
export XQ_HWC_TAIL_COLUMNS=1
export XQ_GRID_RECOVERY=1
export XQ_GRID_PLAN_FAST=1
export XQ_GRID_MODEL_GUARD=1
export XQ_FAST_FP32_BILINEAR=1
export XQ_GEOMETRY_FAST=1
export XQ_GEOMETRY_ARITH=1
export XQ_GEOMETRY_COMPACT=1
export XQ_GEOMETRY_SELECTIVE=1
export XQ_GEOMETRY_SEED_BOUND=1
export XQ_HWC_WORD_INPUT=1
export XQ_BOARD_CORNER_TABLE=1
export XQ_HWC_RGB8_DIRECT=1
export XQ_GRID_DOT_CACHE=1
export XQ_GEOMETRY_MIN_BITS=1
export XQ_BOARD_EXPOSURE_R27=1
export XQ_EXPOSURE_RETRY_R29=1
sh "$repo/linux/picture_new/build_native_coach.sh" "$repo" "$out/worker" "$out/models" rv32
/opt/toolchain/bin/riscv32-linux-musl-strip --strip-all -o "$out/worker/r29-worker.elf" "$out/worker/xq-coach-worker"
sha256sum "$out/worker/r29-worker.elf" >"$out/worker/r29-worker.sha256"
printf 'R29_BUILD_COMPLETE %s\n' "$out/worker/r29-worker.elf"
