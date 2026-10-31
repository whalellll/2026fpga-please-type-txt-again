#!/bin/sh
set -eu
# GCC Linux/musl compiler; bare-metal loader uses the separate 16.2.0 helper.
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cc=${XQ_LINUX_CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
march=${XQ_LINUX_MARCH:-rv32ima_zicsr_zifencei}
out=${XQ_PICTURE_OUT:-"$repo/build/picture-candidate"}
mkdir -p "$out"
"$cc" -std=gnu11 -O2 -march="$march" -mabi=ilp32 \
    -mstrict-align -static -Wl,--strip-debug -Wall -Wextra -Werror \
    -I"$repo/sw/bootloader" -I"$repo/sw/xiangqi" -I"$repo/linux/vision" \
    "$repo/linux/vision/xq_camera_capture.c" \
    "$repo/linux/vision/xq_camera.c" "$repo/linux/vision/xq_camera_linux.c" "$repo/linux/vision/xq_camera_capture_retry.c" \
    "$repo/sw/bootloader/png_rgb565.c" "$repo/sw/bootloader/crc32_fast.c" \
    -o "$out/xq-camera-capture"
echo 'PICTURE_CAPTURE_BUILD_PASS board_validated=false'
