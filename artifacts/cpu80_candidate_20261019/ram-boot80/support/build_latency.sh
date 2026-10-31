#!/bin/sh
set -eu
repo=/mnt/g/fpga/performance_soc_voice_hw
out="$repo/build/cpu75-20261018"
work="$repo/build/pikafish-rv32/source"
port="$repo/linux/pikafish"
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -Os -flto -Wall -Wextra -Werror -Wno-unused-but-set-variable \
 -iquote "$work/src" -iquote "$port" -DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW \
 -DPIKAFISH_PORTABLE_U128 -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DNO_PREFETCH \
 -c "$port/pikafish_nnue_latency.cpp" -o "$out/latency-rv32.o"
make -C "$work/src" -j2 build ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL' \
 EXTRALDFLAGS="$out/latency-rv32.o"
cp "$work/src/pikafish" "$out/pikafish-nnue-latency"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-nnue-latency"
/opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/pikafish-nnue-latency"
sha256sum "$out/pikafish-nnue-latency"
echo CPU75_NNUE_LATENCY_BINARY_BUILT
