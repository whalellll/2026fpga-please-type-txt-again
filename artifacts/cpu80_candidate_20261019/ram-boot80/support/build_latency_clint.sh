#!/bin/sh
set -eu
repo=/mnt/g/fpga/performance_soc_voice_hw
out="$repo/build/cpu75-20261018"
work="$repo/build/pikafish-rv32/source"
/opt/toolchain/bin/riscv32-linux-musl-gcc -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -Wall -Wextra -Werror \
 -c "$repo/linux/pikafish/nnue_clint_clock.c" -o "$out/nnue-clint-clock.o"
make -C "$work/src" -W main.o -j2 all ARCH=riscv32 COMP=gcc CXX=/opt/toolchain/bin/riscv32-linux-musl-g++ \
 EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL' \
 EXTRALDFLAGS="$out/latency-rv32.o $out/nnue-clint-clock.o -Wl,--wrap=clock_gettime,--wrap=clock_getres"
cp "$work/src/pikafish" "$out/pikafish-nnue-latency-clint"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-nnue-latency-clint"
test "$(sha256sum "$out/pikafish-nnue-latency-clint" | cut -d' ' -f1)" != "$(sha256sum "$out/pikafish-nnue-latency" | cut -d' ' -f1)"
strings "$out/pikafish-nnue-latency-clint" | grep 'NNUE_CLOCK_SOURCE source=clint'
sha256sum "$out/pikafish-nnue-latency-clint"
echo CLINT_NNUE_LATENCY_BINARY_BUILT
