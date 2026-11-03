#!/bin/sh
set -eu
repo=${1:?repository}; work="$repo/build/pikafish-rv32/source"; out="$repo/build/nnue10ms/pikafish"; port="$repo/linux/pikafish"
jobs=${2:-4}; cross=/opt/toolchain/bin/riscv32-linux-musl-g++; cross_cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
mkdir -p "$out"
gui_obj_dir="$out/embedded-gui-obj"
mkdir -p "$gui_obj_dir"
gui_cflags="-std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -I$port -I$repo/sw/video -I$repo/sw/xiangqi -I$repo/linux/voice"
"$cross_cc" $gui_cflags -c "$port/xiangqi_pikafish_gui.c" \
    -o "$gui_obj_dir/xiangqi_pikafish_gui.o"
"$cross_cc" $gui_cflags -c "$repo/sw/xiangqi/xiangqi_fb_gui.c" \
    -o "$gui_obj_dir/xiangqi_fb_gui.o"
"$cross_cc" $gui_cflags -c "$repo/sw/xiangqi/xiangqi_mouse_input.c" \
    -o "$gui_obj_dir/xiangqi_mouse_input.o"
"$cross_cc" $gui_cflags -c "$repo/sw/xiangqi/xiangqi_pikafish_link.c" \
    -o "$gui_obj_dir/xiangqi_pikafish_link.o"
"$cross_cc" $gui_cflags -c "$repo/sw/xiangqi/xiangqi_gui_command.c" \
    -o "$gui_obj_dir/xiangqi_gui_command.o"
"$cross_cc" $gui_cflags -c "$repo/sw/xiangqi/xiangqi_search.c" \
    -o "$gui_obj_dir/xiangqi_search.o"
"$cross_cc" $gui_cflags -c "$repo/linux/voice/xqvoice_protocol.c" \
    -o "$gui_obj_dir/xqvoice_protocol.o"
"$cross_cc" $gui_cflags -c "$repo/linux/voice/xqvoice_notation.c" \
    -o "$gui_obj_dir/xqvoice_notation.o"
"$cross_cc" $gui_cflags -c "$repo/linux/voice/xqvoice_gui_ipc.c" \
    -o "$gui_obj_dir/xqvoice_gui_ipc.o"
gui_objects="$gui_obj_dir/xiangqi_pikafish_gui.o $gui_obj_dir/xiangqi_fb_gui.o $gui_obj_dir/xiangqi_mouse_input.o $gui_obj_dir/xiangqi_pikafish_link.o $gui_obj_dir/xiangqi_gui_command.o $gui_obj_dir/xiangqi_search.o $gui_obj_dir/xqvoice_protocol.o $gui_obj_dir/xqvoice_notation.o $gui_obj_dir/xqvoice_gui_ipc.o"

make -C "$work/src" ARCH=general-64 COMP=gcc CXX=g++ objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEB_ACCEL' \
    EXTRALDFLAGS="$gui_objects"
cp "$work/src/pikafish" "$out/xiangqi-pikafish-gui"


"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -Os -flto -Wall -Wextra -Werror -Wno-unused-but-set-variable \
    -iquote "$work/src" -iquote "$port" -DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_PORTABLE_U128 \
    -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DNO_PREFETCH -c "$port/pikafish_nnue_latency.cpp" -o "$out/latency-rv32.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEB_ACCEL' \
    EXTRALDFLAGS="$out/latency-rv32.o"
cp "$work/src/pikafish" "$out/pikafish-nnue-latency"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/xiangqi-pikafish-gui" "$out/pikafish-nnue-latency"
file "$out/xiangqi-pikafish-gui" "$out/pikafish-nnue-latency"
echo NNUE10MS_CANDIDATE_BUILD_PASS
