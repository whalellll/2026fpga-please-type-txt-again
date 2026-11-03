#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=${1:-"$repo/build/xinyi-host-20261024/rv32"}
cc=${CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
mkdir -p "$out/obj"
flags="-std=c11 -D_POSIX_C_SOURCE=200809L -march=rv32ima -mabi=ilp32 -mstrict-align -O2 -Wall -Wextra -Werror -I$repo/linux/xinyi -I$repo/sw/xiangqi"
for source in xinyi_product xinyi_render; do
 "$cc" $flags -c "$repo/linux/xinyi/$source.c" -o "$out/obj/$source.o"
done
"$cc" $flags -DVIDEO_FB_LINUX_MMAP -I"$repo/linux/pikafish" \
 -I"$repo/linux/pikafish/include" -I"$repo/linux/voice" \
 -include "$repo/linux/pikafish/gui1080_config.h" \
 -c "$repo/linux/xinyi/xinyi_fb.c" -o "$out/obj/xinyi_fb.o"
"$cc" $flags -c "$repo/linux/xinyi/coremark/process.c" -o "$out/obj/coremark_process.o"
CC="$cc" CFLAGS="-march=rv32ima -mabi=ilp32 -mstrict-align -static" sh "$repo/linux/xinyi/coremark/build.sh" "$out/coremark"
file "$out/coremark/xinyi-coremark"
"$(dirname "$cc")/riscv32-linux-musl-readelf" -h "$out/coremark/xinyi-coremark"
echo XINYI_PRODUCT_RV32_OBJECTS_AND_COREMARK_ELF_PASS
