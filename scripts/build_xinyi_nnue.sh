#!/bin/sh
# Build a new dedicated NNUE engine/search/latency worksite; never build a GUI
# or replace published boot/artifacts. The prepared official source is read-only.
set -eu
repo=${1:?repository}
baseline=${2:?prepared pinned engine source}
out=${3:?new output directory}
test ! -e "$out"
test -f "$baseline/src/Makefile"
. "$repo/scripts/xinyi_build_paths.sh"
xinyi_build_path "$repo" "$out"
mkdir -p "$out/obj"
out=$(realpath "$out")
work="$out/source"
mkdir "$work" "$out/tmp"
export TMPDIR="$out/tmp" TMP="$out/tmp" TEMP="$out/tmp"
printf '%s\n' "$work" > "$out/source-root.txt"
cp -a "$baseline/src" "$work/src"
cp -a "$baseline/scripts" "$work/scripts"
port="$repo/linux/pikafish"
for name in pikafish_mac_runtime.cpp pikafish_mac_runtime.h pikafish_stagea_accel.cpp pikafish_stagea_accel.h pikafish_stageb_accel.cpp pikafish_stageb_accel.h pikafish_mmio_shadow.h pikafish_mac_backend_policy.h pikafish_feature_updates.h; do
 cp "$port/$name" "$work/src/$name"
done
cp "$repo/linux/mac_accel/pango_mac_uapi.h" "$work/src/pango_mac_uapi.h"
python3 "$port/apply_nnue_pipeline.py" "$work" "$port/pikafish-pipeline.patch" "$out/pipeline-integration.json"
python3 "$port/apply_feature_updates.py" "$work" "$out/feature-updates-integration.json"
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
flags='-DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL'
jobs=${XINYI_NNUE_BUILD_JOBS:-2}
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" EXTRACXXFLAGS="$flags"
cp "$work/src/pikafish" "$out/pikafish-rv32"
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -O2 -flto -Wall -Wextra -Werror \
 -iquote "$port" -iquote "$repo/sw/pikafish_mlp_stage_b" \
 -c "$port/pikafish_pipeline_search.cpp" -o "$out/obj/search.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS="$flags -DPIKAFISH_EMBEDDED_GUI" EXTRALDFLAGS="$out/obj/search.o"
cp "$work/src/pikafish" "$out/pikafish-pipeline-search"
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -Os -flto -Wall -Wextra -Werror -Wno-unused-but-set-variable \
 -iquote "$work/src" -iquote "$port" -DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_PORTABLE_U128 \
 -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DNO_PREFETCH -c "$port/pikafish_nnue_pipeline_latency.cpp" -o "$out/obj/latency.o"
"$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -flto -Wall -Wextra -Werror \
 -c "$port/nnue_clint_clock.c" -o "$out/obj/clint.o"
make -C "$work/src" -j"$jobs" ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS="$flags -DPIKAFISH_EMBEDDED_GUI" \
 EXTRALDFLAGS="$out/obj/latency.o $out/obj/clint.o -Wl,--wrap=clock_gettime,--wrap=clock_getres" \
 --eval='.PHONY: xinyi_pipeline_latency_relink' --eval='pikafish: xinyi_pipeline_latency_relink' pikafish
cp "$work/src/pikafish" "$out/pikafish-nnue-pipeline-latency"
for name in pikafish-rv32 pikafish-pipeline-search pikafish-nnue-pipeline-latency; do
 /opt/toolchain/bin/riscv32-linux-musl-readelf -h -A "$out/$name" > "$out/$name.elf.txt"
done
printf '%s\n' XINYI_NNUE_ENGINE_SEARCH_LATENCY_RV32_BUILD_PASS_NOT_BOARD
