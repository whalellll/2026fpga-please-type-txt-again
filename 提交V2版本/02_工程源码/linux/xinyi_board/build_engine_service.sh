#!/bin/sh
# Reuse T1's prepared, pipeline-patched private objects. No old GUI build.
set -eu
repo=$1
source=$2
out=$3
case "$(realpath "$source")" in /mnt/g/fpga/*/src) ;; *) exit 2;; esac
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
test -f "$source/main.o"
mkdir -p "$out"
hash_sources() {
 sha256sum "$repo/linux/xinyi_board/engine_service.cpp" "$repo/linux/xinyi_board/build_engine_service.sh" \
  "$repo/linux/pikafish/pikafish_mac_runtime.cpp" "$repo/linux/pikafish/pikafish_mac_runtime.h" \
  "$repo/linux/pikafish/pikafish_mac_backend_policy.h" "$repo/linux/mac_accel/pango_mac_uapi.h"
 find "$source" -type f \( -name '*.cpp' -o -name '*.h' -o -name '*.inc' -o -name 'Makefile' \) \
  -exec sha256sum {} \; | LC_ALL=C sort
}
hash_sources > "$out/source-before.sha256"
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -O2 -flto -Wall -Wextra -Werror \
 -iquote "$repo/linux/pikafish" -iquote "$repo/sw/pikafish_mlp_stage_b" \
 -c "$repo/linux/xinyi_board/engine_service.cpp" -o "$out/service.o"
flags='-DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_EMBEDDED_GUI'
make -s -C "$source" -j2 ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS="$flags" EXTRALDFLAGS="$out/service.o" \
 --eval='.PHONY: xinyi_engine_service_relink' --eval='pikafish: xinyi_engine_service_relink' pikafish
cp "$source/pikafish" "$out/xinyi-engine.debug"
/opt/toolchain/bin/riscv32-linux-musl-strip -o "$out/xinyi-engine" "$out/xinyi-engine.debug"
/opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/xinyi-engine" > "$out/elf.txt"
sha256sum -c "$out/source-before.sha256" > "$out/source-stable.txt"
hash_sources > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
sha256sum "$out/xinyi-engine" "$out/xinyi-engine.debug" > "$out/SHA256SUMS.txt"
echo XINYI_DEDICATED_ENGINE_SERVICE_RV32_BUILD_PASS_NOT_BOARD
