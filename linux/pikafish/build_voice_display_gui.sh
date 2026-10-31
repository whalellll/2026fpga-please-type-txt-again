#!/bin/sh
# Isolated Linux GUI candidate; engine sources/model and FPGA inputs unchanged.
set -eu
repo=${1:?repository path}
baseline=${2:?prepared pinned Pikafish source directory}
out=${3:?new output directory}
theme=${4:-light}
case "$theme" in dark) theme_flags=-DXQ_GUI_DARK_THEME;; light) theme_flags=;; *) echo 'Unknown GUI theme' >&2; exit 1;; esac
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
test -x "$cross"
test -f "$baseline/src/Makefile"
test ! -e "$out"
mkdir -p "$out/obj"
cp -a "$baseline/src" "$out/engine-src"
cp -a "$baseline/scripts" "$out/scripts"
port="$repo/linux/pikafish"
flags="-include $port/gui1080_config.h -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -I$port -I$repo/sw/video -I$repo/sw/xiangqi -I$repo/linux/voice"
objects=""
flags="$flags $theme_flags"
for name in xiangqi_pikafish_gui xiangqi_fb_gui_1080; do
 "$cc" $flags -c "$port/$name.c" -o "$out/obj/$name.o"
 objects="$objects $out/obj/$name.o"
done
for name in xiangqi_mouse_input xiangqi_pikafish_link xiangqi_gui_command xiangqi_search; do
 "$cc" $flags -c "$repo/sw/xiangqi/$name.c" -o "$out/obj/$name.o"
 objects="$objects $out/obj/$name.o"
done
for name in xqvoice_protocol xqvoice_gui_ipc; do
 "$cc" $flags -c "$repo/linux/voice/$name.c" -o "$out/obj/$name.o"
 objects="$objects $out/obj/$name.o"
done
make -C "$out/engine-src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$out/engine-src" -j2 build ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL' \
 EXTRALDFLAGS="$objects"
cp "$out/engine-src/pikafish" "$out/xiangqi-pikafish-gui-display"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/xiangqi-pikafish-gui-display"
file "$out/xiangqi-pikafish-gui-display"
sha256sum "$out/xiangqi-pikafish-gui-display"
echo VOICE_DISPLAY_GUI_RV32_BUILD_PASS
