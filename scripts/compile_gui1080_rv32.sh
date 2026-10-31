#!/bin/sh
# Compile the actual display/interaction units for the deployed RV32 ABI.
# This produces objects and a DTB; the full engine link remains in build_voice_display_gui.sh.
set -eu
repo=${1:?repository path}
out=${2:?new output directory}
cc=${CC_RV32:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
theme=${3:-light}
case "$theme" in dark) theme_flags=-DXQ_GUI_DARK_THEME;; light) theme_flags=;; *) echo 'Unknown GUI theme' >&2; exit 1;; esac
test ! -e "$out"
mkdir -p "$out"
port="$repo/linux/pikafish"
flags="-include $port/gui1080_config.h -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -ffunction-sections -fdata-sections -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -I$port -I$repo/sw/video -I$repo/sw/xiangqi -I$repo/linux/voice"
flags="$flags $theme_flags"
for name in xiangqi_pikafish_gui xiangqi_fb_gui_1080; do
    "$cc" $flags -c "$port/$name.c" -o "$out/$name.o"
done
for name in xiangqi_mouse_input xiangqi_pikafish_link xiangqi_gui_command xiangqi_search; do
    "$cc" $flags -c "$repo/sw/xiangqi/$name.c" -o "$out/$name.o"
done
for name in xqvoice_protocol xqvoice_gui_ipc; do
    "$cc" $flags -c "$repo/linux/voice/$name.c" -o "$out/$name.o"
done
dtc -I dts -O dtb -o "$out/soc.dtb" "$repo/linux/soc.dts"
"${cc%gcc}readelf" -h "$out/xiangqi_fb_gui_1080.o"
sha256sum "$out"/*.o "$out/soc.dtb"
echo GUI1080_RV32_OBJECTS_AND_DTB_PASS_NOT_LINKED_OR_BOARD
