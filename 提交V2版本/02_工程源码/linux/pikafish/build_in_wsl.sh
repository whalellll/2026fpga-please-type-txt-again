#!/bin/sh
set -eu

repo=${PIKAFISH_REPO:?}
work=${PIKAFISH_WORK:?}
out=${PIKAFISH_OUT:?}
port=${PIKAFISH_PORT:?}
jobs=${PIKAFISH_BUILD_JOBS:-2}
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
cross_cc=/opt/toolchain/bin/riscv32-linux-musl-gcc

test -x "$cross"
test -x "$cross_cc"
test -f "$work/src/pikafish.nnue"
test -d "$out"
test -d "$repo/sw/xiangqi"

make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS='-DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD'
cp "$work/src/pikafish" "$out/pikafish-rv32"

make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++
cp "$work/src/pikafish" "$out/pikafish-reference-x86_64"

gui_obj_dir="$out/embedded-gui-obj"
mkdir -p "$gui_obj_dir"
gui_cflags="-std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -I$port -I$repo/sw/video -I$repo/sw/xiangqi -I$repo/linux/voice"
"$cross_cc" $gui_cflags -c "$port/xiangqi_pikafish_gui.c" \
    -o "$gui_obj_dir/xiangqi_pikafish_gui.o"
"$cross_cc" $gui_cflags -c "$port/xiangqi_fb_gui_linux.c" \
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
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL' \
    EXTRALDFLAGS="$gui_objects"
cp "$work/src/pikafish" "$out/xiangqi-pikafish-gui"

phase4_obj_dir="$out/stageb-phase4-obj"
mkdir -p "$phase4_obj_dir"
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -Os -flto \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -Wall -Wextra -Werror -pedantic \
    -iquote "$port" -iquote "$repo/sw/pikafish_mlp_stage_b" \
    -c "$port/pikafish_stageb_phase4_search.cpp" \
    -o "$phase4_obj_dir/search-rv32.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEB_ACCEL' \
    EXTRALDFLAGS="$phase4_obj_dir/search-rv32.o"
cp "$work/src/pikafish" "$out/pikafish-stageb-phase4-search"

g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
    -iquote "$port" -iquote "$repo/sw/pikafish_mlp_stage_b" \
    -c "$port/pikafish_stageb_phase4_search.cpp" \
    -o "$phase4_obj_dir/search-host.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++ \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_MAC_RUNTIME_EMULATED' \
    EXTRALDFLAGS="$phase4_obj_dir/search-host.o"
cp "$work/src/pikafish" "$out/pikafish-stageb-phase4-search-x86_64"

phase5_obj_dir="$out/stageb-phase5-obj"
mkdir -p "$phase5_obj_dir"
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -Os -flto \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -Wall -Wextra -Werror -pedantic \
    -iquote "$port" -iquote "$repo/sw/pikafish_mlp_stage_b" \
    -c "$port/pikafish_stageb_phase5_search.cpp" \
    -o "$phase5_obj_dir/search-rv32.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEB_ACCEL' \
    EXTRALDFLAGS="$phase5_obj_dir/search-rv32.o"
cp "$work/src/pikafish" "$out/pikafish-stageb-phase5-search"

g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
    -iquote "$port" -iquote "$repo/sw/pikafish_mlp_stage_b" \
    -c "$port/pikafish_stageb_phase5_search.cpp" \
    -o "$phase5_obj_dir/search-host.o"
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++ \
    EXTRACXXFLAGS='-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_MAC_RUNTIME_EMULATED' \
    EXTRALDFLAGS="$phase5_obj_dir/search-host.o"
cp "$work/src/pikafish" "$out/pikafish-stageb-phase5-search-x86_64"

"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -static -Wl,--gc-sections -Wall -Wextra -Werror \
    "$port/pikafish_devmem_copy.c" -o "$out/pikafish-devmem-copy"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-devmem-copy"

make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cross" objclean
make -C "$work/src" -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++ \
    EXTRACXXFLAGS='-DPIKAFISH_PFF1_DIRECT_VIEW'
cp "$work/src/pikafish" "$out/pikafish-view-reference-x86_64"

phase2_host_obj_dir="$out/stageb-phase2-host-obj"
mkdir -p "$phase2_host_obj_dir"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
    -iquote "$repo/sw/pikafish_mlp_stage_b" \
    -c "$repo/sw/pikafish_mlp_stage_b/pf_mlp_stage_b_ref.c" \
    -o "$phase2_host_obj_dir/pf_mlp_stage_b_ref.o"
g++ -std=c++17 -O2 -Wall -Wextra -Werror -Wno-unused-but-set-variable \
    -pedantic -DIS_64BIT -DNO_PREFETCH \
    -I"$work/src" -iquote "$repo/sw/pikafish_mlp_stage_b" \
    "$port/pikafish_stageb_golden_test.cpp" \
    "$phase2_host_obj_dir/pf_mlp_stage_b_ref.o" \
    -o "$out/pikafish-stageb-golden-test-x86_64"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
    -iquote "$repo/sw/mac_accel" \
    -c "$repo/sw/mac_accel/mac_accel_kernel.c" \
    -o "$phase2_host_obj_dir/mac_accel_kernel.o"
phase2_host_objects="$phase2_host_obj_dir/pf_mlp_stage_b_ref.o $phase2_host_obj_dir/mac_accel_kernel.o"

make -C "$work/src" ARCH=general-64 COMP=gcc CXX=g++ objclean
make -C "$work/src" -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++ \
    EXTRACXXFLAGS="-DPIKAFISH_STAGEB_POSITION_ACCEPTANCE" \
    EXTRALDFLAGS="$phase2_host_objects"
cp "$work/src/pikafish" "$out/pikafish-stageb-position-reference-x86_64"
"$out/pikafish-stageb-position-reference-x86_64" --generate \
    "$work/src/pikafish.nnue" "$repo/linux/boot/pikafish.pff" \
    "$repo/artifacts/pikafish-stageb-mac.bin" \
    "$repo/artifacts/pikafish-stageb-position-golden.bin"

make -C "$work/src" ARCH=general-64 COMP=gcc CXX=g++ objclean
make -C "$work/src" -j"$jobs" build ARCH=general-64 COMP=gcc CXX=g++ \
    EXTRACXXFLAGS="-DPIKAFISH_STAGEB_POSITION_ACCEPTANCE -DPIKAFISH_PFF1_DIRECT_VIEW" \
    EXTRALDFLAGS="$phase2_host_objects"
cp "$work/src/pikafish" "$out/pikafish-stageb-position-view-x86_64"
"$out/pikafish-stageb-position-view-x86_64" --verify \
    "$repo/linux/boot/pikafish.pff" "$repo/linux/boot/pikafish.pff" \
    "$repo/artifacts/pikafish-stageb-mac.bin" \
    "$repo/artifacts/pikafish-stageb-position-golden.bin"

phase2_rv32_obj_dir="$out/stageb-phase2-rv32-obj"
mkdir -p "$phase2_rv32_obj_dir"
"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -Wall -Wextra -Werror \
    -iquote "$repo/sw/pikafish_mlp_stage_b" \
    -c "$repo/sw/pikafish_mlp_stage_b/pf_mlp_stage_b_ref.c" \
    -o "$phase2_rv32_obj_dir/pf_mlp_stage_b_ref.o"
"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -Wall -Wextra -Werror \
    -iquote "$repo/sw/mac_accel" \
    -c "$repo/sw/mac_accel/mac_accel_kernel.c" \
    -o "$phase2_rv32_obj_dir/mac_accel_kernel.o"
phase2_rv32_objects="$phase2_rv32_obj_dir/pf_mlp_stage_b_ref.o $phase2_rv32_obj_dir/mac_accel_kernel.o"
make -C "$work/src" ARCH=general-64 COMP=gcc CXX=g++ objclean
make -C "$work/src" -j"$jobs" build ARCH=riscv32 COMP=gcc CXX="$cross" \
    EXTRACXXFLAGS="-DPIKAFISH_STAGEB_POSITION_ACCEPTANCE -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD" \
    EXTRALDFLAGS="$phase2_rv32_objects"
cp "$work/src/pikafish" "$out/pikafish-stageb-position-accept"

chmod 0755 "$out/pikafish-rv32" "$out/pikafish-reference-x86_64" \
    "$out/pikafish-view-reference-x86_64" \
    "$out/pikafish-stageb-golden-test-x86_64" \
    "$out/pikafish-stageb-position-reference-x86_64" \
    "$out/pikafish-stageb-position-view-x86_64" \
    "$out/pikafish-stageb-position-accept" \
    "$out/pikafish-stageb-phase4-search" \
    "$out/pikafish-stageb-phase4-search-x86_64" \
    "$out/pikafish-stageb-phase5-search" \
    "$out/pikafish-stageb-phase5-search-x86_64" \
    "$out/pikafish-devmem-copy" \
    "$out/xiangqi-pikafish-gui"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-rv32"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/xiangqi-pikafish-gui"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-stageb-position-accept"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-stageb-phase4-search"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-stageb-phase5-search"
strip "$out/pikafish-reference-x86_64"
strip "$out/pikafish-view-reference-x86_64"
strip "$out/pikafish-stageb-golden-test-x86_64"
strip "$out/pikafish-stageb-position-reference-x86_64"
strip "$out/pikafish-stageb-position-view-x86_64"
strip "$out/pikafish-stageb-phase4-search-x86_64"
strip "$out/pikafish-stageb-phase5-search-x86_64"

"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -flto \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -static -Wl,--gc-sections -Wall -Wextra -Werror \
    -DVIDEO_FB_LINUX_MMAP \
    -I"$repo/sw/video" -I"$repo/sw/xiangqi" \
    "$port/xiangqi_input_test.c" \
    "$port/xiangqi_fb_gui_linux.c" \
    "$repo/sw/xiangqi/xiangqi_mouse_input.c" \
    "$repo/sw/xiangqi/xiangqi_search.c" \
    -o "$out/xiangqi-input-test"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/xiangqi-input-test"

"$cross_cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -O2 \
    -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables \
    -static -Wl,--gc-sections -Wall -Wextra -Werror \
    "$port/pff1_linux_probe.c" -o "$out/pff1-linux-probe"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pff1-linux-probe"

g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -I"$port" \
    "$port/pikafish_stagea_accel.cpp" "$port/pikafish_stagea_pack_test.cpp" \
    -o "$out/pikafish-stagea-pack-test-x86_64"
"$cross" -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
    -march=rv32ima -mabi=ilp32 -static -I"$port" \
    "$port/pikafish_stagea_accel.cpp" "$port/pikafish_stagea_pack_test.cpp" \
    -o "$out/pikafish-stagea-pack-test-rv32"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-stagea-pack-test-rv32"

g++ -std=c++17 -O2 -Wall -Wextra -Werror -Wno-unused-but-set-variable -pedantic \
    -DIS_64BIT -DNO_PREFETCH -DPIKAFISH_EMBEDDED_SINGLE_THREAD \
    -I"$work/src" "$port/pikafish_history_zero_test.cpp" "$work/src/memory.cpp" \
    -o "$out/pikafish-history-zero-test-x86_64"
"$out/pikafish-history-zero-test-x86_64"
"$cross" -std=c++17 -O2 -Wall -Wextra -Werror -Wno-unused-but-set-variable -pedantic \
    -march=rv32ima -mabi=ilp32 -static -DPIKAFISH_PORTABLE_U128 \
    -DNO_PREFETCH -DPIKAFISH_EMBEDDED_SINGLE_THREAD \
    -I"$work/src" "$port/pikafish_history_zero_test.cpp" "$work/src/memory.cpp" \
    -o "$out/pikafish-history-zero-test-rv32"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-history-zero-test-rv32"

g++ -std=c++17 -O2 -DNDEBUG -DIS_64BIT -DNO_PREFETCH \
    -Wall -Wextra -Werror -Wno-unused-but-set-variable -pedantic \
    -I"$work/src" \
    "$work/src/attacks.cpp" "$work/src/pikafish_attack_tables.cpp" \
    "$port/test_precomputed_attacks.cpp" \
    -o "$out/pikafish-attacks-test-x86_64"
"$cross" -std=c++17 -O2 -DNDEBUG -DPIKAFISH_PORTABLE_U128 -DNO_PREFETCH \
    -march=rv32ima -mabi=ilp32 -static \
    -Wall -Wextra -Werror -Wno-unused-but-set-variable -pedantic \
    -I"$work/src" \
    "$work/src/attacks.cpp" "$work/src/pikafish_attack_tables.cpp" \
    "$port/test_precomputed_attacks.cpp" \
    -o "$out/pikafish-attacks-test-rv32"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/pikafish-attacks-test-rv32"

echo PIKAFISH_RV32_WSL_BUILD_PASS
