#!/bin/sh
# Rebuild GUI units and force one link using this candidate's existing engine objects.
# Never run against the production or shared prepared engine directory.
set -eu
repo=$(realpath "${1:?repository path}")
built=$(realpath "${2:?previous candidate GUI build directory}")
out=${3:?new output directory}
theme=${4:-light}
case "$theme" in dark) theme_flags=-DXQ_GUI_DARK_THEME;; light) theme_flags=;; *) echo 'Unknown GUI theme' >&2; exit 1;; esac
case "$built/" in "$repo"/build/*) ;; *) echo 'Engine build must belong to this candidate' >&2; exit 1;; esac
test -f "$built/engine-src/pikafish_embedded.o"
test ! -e "$out"
mkdir -p "$out/obj"
out=$(realpath "$out")
case "$out/" in "$repo"/build/*) ;; *) echo 'Output must belong to this candidate' >&2; exit 1;; esac
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
port="$repo/linux/pikafish"
flags="-include $port/gui1080_config.h -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -I$port -I$repo/sw/video -I$repo/sw/xiangqi -I$repo/linux/voice"
objects=""
flags="$flags $theme_flags"
for group in "$port:xiangqi_pikafish_gui,xiangqi_fb_gui_1080" "$repo/sw/xiangqi:xiangqi_mouse_input,xiangqi_pikafish_link,xiangqi_gui_command,xiangqi_search" "$repo/linux/voice:xqvoice_protocol,xqvoice_gui_ipc"; do
    directory=${group%%:*}
    names=$(printf '%s' "${group#*:}" | tr ',' ' ')
    for name in $names; do
        "$cc" $flags -c "$directory/$name.c" -o "$out/obj/$name.o"
        objects="$objects $out/obj/$name.o"
    done
done
make -C "$built/engine-src" -j2 ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL' \
    EXTRALDFLAGS="$objects" --eval='.PHONY: gui_display_relink' \
    --eval='pikafish: gui_display_relink' pikafish
cp "$built/engine-src/pikafish" "$out/xiangqi-pikafish-gui-display"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/xiangqi-pikafish-gui-display"
file "$out/xiangqi-pikafish-gui-display"
sha256sum "$out/xiangqi-pikafish-gui-display"
echo GUI1080_RV32_RELINK_PASS_NOT_BOARD
