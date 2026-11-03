#!/bin/sh
set -eu
repo=$1
out=$2
engine=$3
case "$out" in "$repo"/build/*) ;; *) echo 'output must be in build/' >&2; exit 1;; esac
test ! -e "$out"
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
cxx=/opt/toolchain/bin/riscv32-linux-musl-g++
timing_flag=""
if [ "${XQ_PICTURE_LATENCY_TIMING:-0}" = 1 ]; then timing_flag="-DXQ_PICTURE_LATENCY_TIMING"; fi
mkdir -p "$out/gui-obj"
sha256sum "$engine/"*.o > "$out/engine-objects-before.sha256"
objects=""
for source in linux/pikafish/xiangqi_pikafish_gui.c linux/pikafish/xiangqi_fb_gui_linux.c \
 sw/xiangqi/xiangqi_mouse_input.c sw/xiangqi/xiangqi_pikafish_link.c sw/xiangqi/xiangqi_gui_command.c \
 sw/xiangqi/xiangqi_search.c linux/voice/xqvoice_protocol.c linux/voice/xqvoice_notation.c \
 linux/voice/xqvoice_gui_ipc.c linux/vision/xq_vision.c linux/vision/xq_picture.c \
 linux/vision/xq_grid.c linux/vision/xq_roi.c linux/vision/xq_roi_pipeline.c \
 linux/vision/xq_mac.c linux/vision/xq_mac_linux.c \
  linux/vision/xq_speech.c linux/vision/xq_speech_linux.c linux/vision/xq_camera.c linux/vision/xq_camera_linux.c linux/vision/xq_camera_capture_retry.c \
  sw/bootloader/crc32_fast.c; do
 name=$(basename "$source" .c)
 "$cc" -std=gnu11 -O2 -pthread -march=rv32ima -mabi=ilp32 -mstrict-align $timing_flag \
  -ffunction-sections -fdata-sections -Wall -Wextra -Werror \
  -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -DXQ_PICTURE_INPUT \
  -I"$repo/linux/pikafish" -I"$repo/sw/video" -I"$repo/sw/xiangqi" \
  -I"$repo/linux/voice" -I"$repo/sw/bootloader" -I"$repo/linux/vision" -I"$repo/linux/mac_accel" \
  -c "$repo/$source" -o "$out/gui-obj/$name.o"
 objects="$objects $out/gui-obj/$name.o"
done
"$cxx" -std=c++17 -O3 -DNDEBUG -pthread -march=rv32ima -mabi=ilp32 -mstrict-align \
 -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -I"$repo/linux/mac_accel" -I"$engine" \
 -c "$repo/linux/pikafish/pikafish_mac_runtime.cpp" -o "$out/pikafish_mac_runtime.o"
for object in "$engine/"*.o; do
 case "$object" in */pikafish_mac_runtime.o) ;; *) objects="$objects $object";; esac
done
"$cxx" -o "$out/xiangqi-pikafish-gui" "$out/pikafish_mac_runtime.o" $objects \
 -march=rv32ima -mabi=ilp32 -static -Wl,--strip-debug -latomic -lpthread
"$cc" -std=gnu11 -O2 -march=rv32ima -mabi=ilp32 -mstrict-align -static -Wl,--strip-debug \
 -Wall -Wextra -Werror -I"$repo/sw/bootloader" -I"$repo/sw/xiangqi" -I"$repo/linux/vision" \
 "$repo/linux/vision/xq_camera_capture.c" "$repo/linux/vision/xq_camera.c" "$repo/linux/vision/xq_camera_linux.c" "$repo/linux/vision/xq_camera_capture_retry.c" \
 "$repo/sw/bootloader/png_rgb565.c" "$repo/sw/bootloader/crc32_fast.c" -o "$out/xq-camera-capture"
/opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/xiangqi-pikafish-gui" > "$out/elf-inspection.txt"
echo PICTURE_ROI_GUI_BUILD_PASS
sha256sum "$engine/"*.o > "$out/engine-objects-after.sha256"
cmp "$out/engine-objects-before.sha256" "$out/engine-objects-after.sha256"
