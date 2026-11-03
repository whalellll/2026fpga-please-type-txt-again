#!/bin/sh
set -eu
repo=${1:?candidate repository}
baseline=${2:?prepared pinned source root}
out=${3:?new output directory}
test ! -e "$out"
mkdir -p "$out/obj"
out=$(realpath "$out")
case "$out" in /mnt/g/fpga/*) ;; *) echo "Build must remain in workspace" >&2; exit 2;; esac
work="$out/source"
mkdir "$work" "$out/tmp"
export TMPDIR="$out/tmp" TMP="$out/tmp" TEMP="$out/tmp"
printf 'PIKAFISH75_BUILD_WORK=%s\n' "$work"
cp -a "$baseline/src" "$work/src"
cp -a "$baseline/scripts" "$work/scripts"
port="$repo/linux/pikafish"
for name in pikafish_mac_runtime.cpp pikafish_mac_runtime.h pikafish_stagea_accel.cpp pikafish_stagea_accel.h pikafish_feature_updates.h pikafish_mmio_shadow.h pikafish_mac_backend_policy.h pikafish_stageb_accel.cpp pikafish_stageb_accel.h; do
 cp "$port/$name" "$work/src/$name"
done
python3 "$port/apply_nnue_pipeline.py" "$work" "$port/pikafish-pipeline.patch" "$out/pipeline-integration.json"
python3 "$port/apply_feature_updates.py" "$work" "$out/feature-updates-integration.json"
cp "$repo/linux/mac_accel/pango_mac_uapi.h" "$work/src/pango_mac_uapi.h"
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
engine_flags='-DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL'
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j4 build ARCH=riscv32 COMP=gcc CXX="$cross" EXTRACXXFLAGS="$engine_flags"
cp "$work/src/pikafish" "$out/pikafish-rv32"
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -O2 -flto -Wall -Wextra -Werror \
 -iquote "$port" -iquote "$repo/sw/pikafish_mlp_stage_b" \
 -c "$port/pikafish_pipeline_search.cpp" -o "$out/obj/search.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j4 build ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS="$engine_flags -DPIKAFISH_EMBEDDED_GUI" EXTRALDFLAGS="$out/obj/search.o"
cp "$work/src/pikafish" "$out/pikafish-pipeline-search"
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -Os -flto -Wall -Wextra -Werror -Wno-unused-but-set-variable \
 -iquote "$work/src" -iquote "$port" -DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_PORTABLE_U128 \
 -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DNO_PREFETCH -c "$port/pikafish_nnue_pipeline_latency.cpp" -o "$out/obj/latency.o"
"$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -flto -Wall -Wextra -Werror \
 -c "$port/nnue_clint_clock.c" -o "$out/obj/clint.o"
make -C "$work/src" -j4 ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS="$engine_flags -DPIKAFISH_EMBEDDED_GUI" \
 EXTRALDFLAGS="$out/obj/latency.o $out/obj/clint.o -Wl,--wrap=clock_gettime,--wrap=clock_getres" \
 --eval='.PHONY: pipeline_latency_relink' --eval='pikafish: pipeline_latency_relink' pikafish
cp "$work/src/pikafish" "$out/pikafish-nnue-pipeline-latency"
flags="-include $port/gui1080_config.h -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -I$port -I$repo/sw/video -I$repo/sw/xiangqi -I$repo/linux/voice"
test -r "$repo/linux/voice/xqvoice_display.h"
objects=""
for group in "$port:xiangqi_pikafish_gui,xiangqi_fb_gui_1080" "$repo/sw/xiangqi:xiangqi_mouse_input,xiangqi_pikafish_link,xiangqi_gui_command,xiangqi_search" "$repo/linux/voice:xqvoice_protocol,xqvoice_gui_ipc"; do
 directory=${group%%:*}
 names=$(printf '%s' "${group#*:}" | tr ',' ' ')
 for name in $names; do
  "$cc" $flags -c "$directory/$name.c" -o "$out/obj/$name.o"
  objects="$objects $out/obj/$name.o"
 done
done
make -C "$work/src" -j4 ARCH=riscv32 COMP=gcc CXX="$cross" \
 EXTRACXXFLAGS="$engine_flags -DPIKAFISH_EMBEDDED_GUI" EXTRALDFLAGS="$objects" \
 --eval='.PHONY: pipeline_gui_relink' --eval='pikafish: pipeline_gui_relink' pikafish
cp "$work/src/pikafish" "$out/xiangqi-pikafish-gui-display"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-rv32" "$out/pikafish-pipeline-search" "$out/xiangqi-pikafish-gui-display" "$out/pikafish-nnue-pipeline-latency"
sha256sum "$out/pikafish-rv32" "$out/pikafish-pipeline-search" "$out/xiangqi-pikafish-gui-display" "$out/pikafish-nnue-pipeline-latency"
printf '%s\n' PIKAFISH75_PIPELINE_SEARCH_AND_GUI_RV32_BUILD_PASS_NOT_BOARD
