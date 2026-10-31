#!/bin/sh
set -eu
repo=$1
out=$2
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
"$cc" -O2 -static -march=rv32ima -mabi=ilp32 -mstrict-align -std=c11 -Wall -Wextra -Werror \
 -I"$repo/linux/vision" -I"$repo/sw/xiangqi" -I"$repo/sw/bootloader" \
 "$repo/artifacts/vision-model-20261020-adapter/runtime/xq_camera_exec.c" \
 "$repo/linux/vision/xq_camera.c" "$repo/linux/vision/xq_camera_linux.c" \
 "$repo/linux/vision/xq_camera_retry.c" -o "$out/xq-camera-exec"
sha256sum "$out/xq-camera-exec" > "$out/SHA256SUMS.txt"
/opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/xq-camera-exec" > "$out/elf-inspection.txt"
echo NATIVE_CAMERA_EXEC_BUILD_PASS
