#!/bin/sh
# Build the board diagnostic against the exact production GUI objects.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=$1
gui=$2
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
test "$(cat "$gui/cpu-hz.txt")" = 75000000
cmp "$gui/source-before.sha256" "$gui/source-after.sha256"
test "$(sha256sum "$gui/xinyi-one-stripped" | cut -d' ' -f1)" = f50801c5636560a159a91b87b4664f1d9cc5b45bb42e32a71c071bfddd77d23d
mkdir -p "$out"
cc=${CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
cd "$repo"
"$cc" -std=c11 -DXINYI_CPU_HZ=75000000 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -march=rv32ima -mabi=ilp32 -mstrict-align -static -Ilinux/xinyi_board -Ilinux/xinyi -Ilinux/vision -Ilinux/voice_ctc -Ilinux/voice_speech -Ilinux/mac_accel -Ilinux/picture_new -Ilinux/voice -Ilinux/pikafish -Isw/xiangqi -Isw/bootloader -c linux/xinyi_board/mouse_board_smoke_strict.c -o "$out/main.o"
set -- "$out/main.o"
for object in "$gui"/obj/*.o; do
 case "$object" in */0.o|*/renderer.o) continue;; esac
 set -- "$@" "$object"
done
"$cc" -static -march=rv32ima -mabi=ilp32 -mstrict-align -pthread "$@" -Wl,--gc-sections -lm -o "$out/smoke"
/opt/toolchain/bin/riscv32-linux-musl-strip --strip-unneeded "$out/smoke"
sha256sum "$out/smoke" linux/xinyi_board/mouse_board_smoke_strict.c
