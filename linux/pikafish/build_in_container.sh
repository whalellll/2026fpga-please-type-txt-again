#!/bin/sh
set -eu

jobs=${PIKAFISH_BUILD_JOBS:-2}
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
cross_cc=/opt/toolchain/bin/riscv32-linux-musl-gcc

test -x "$cross"
test -x "$cross_cc"
test -f /work/src/pikafish.nnue
test -d /out
test -d /repo/sw/xiangqi

make -C /work/src -j"$jobs" build \
    ARCH=riscv32 COMP=gcc CXX="$cross"
cp /work/src/pikafish /out/pikafish-rv32

make -C /work/src ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C /work/src -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++
cp /work/src/pikafish /out/pikafish-reference-x86_64

chmod 0755 /out/pikafish-rv32 /out/pikafish-reference-x86_64
/opt/toolchain/bin/riscv32-linux-musl-strip /out/pikafish-rv32
strip /out/pikafish-reference-x86_64

"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -static -Wl,--gc-sections -Wall -Wextra -Werror \
    -DVIDEO_FB_LINUX_MMAP \
    -I/repo/sw/video -I/repo/sw/xiangqi -I/repo/linux/voice \
    /port/xiangqi_pikafish_gui.c \
    /repo/linux/pikafish/xiangqi_fb_gui_linux.c \
    /repo/sw/xiangqi/xiangqi_mouse_input.c \
    /repo/sw/xiangqi/xiangqi_pikafish_link.c \
    /repo/sw/xiangqi/xiangqi_gui_command.c \
    /repo/linux/voice/xqvoice_protocol.c \
    /repo/linux/voice/xqvoice_notation.c \
    /repo/linux/voice/xqvoice_gui_ipc.c \
    /repo/sw/xiangqi/xiangqi_search.c \
    -o /out/xiangqi-pikafish-gui
/opt/toolchain/bin/riscv32-linux-musl-strip /out/xiangqi-pikafish-gui

"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -static -Wl,--gc-sections -Wall -Wextra -Werror \
    -DVIDEO_FB_LINUX_MMAP \
    -I/repo/sw/video -I/repo/sw/xiangqi \
    /port/xiangqi_input_test.c \
    /repo/linux/pikafish/xiangqi_fb_gui_linux.c \
    /repo/sw/xiangqi/xiangqi_mouse_input.c \
    /repo/sw/xiangqi/xiangqi_search.c \
    -o /out/xiangqi-input-test
/opt/toolchain/bin/riscv32-linux-musl-strip /out/xiangqi-input-test

"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -static -Wl,--gc-sections -Wall -Wextra -Werror \
    /port/pff1_linux_probe.c -o /out/pff1-linux-probe
/opt/toolchain/bin/riscv32-linux-musl-strip /out/pff1-linux-probe
