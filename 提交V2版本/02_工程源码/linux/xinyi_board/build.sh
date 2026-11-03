#!/bin/sh
# Product executable only. No public boot payload, SD or FPGA mutation.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=$1
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out/obj"
cc=${CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
cpu_hz=${XINYI_CPU_HZ:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cpu_hz"])' "$repo/config/clocks.json")}
case "$cpu_hz" in 60000000|70000000|75000000|80000000) ;; *) echo 'Unreviewed Xinyi CPU clock' >&2; exit 2;; esac
printf '%s\n' "$cpu_hz" > "$out/cpu-hz.txt"
flags="-std=c11 -D_POSIX_C_SOURCE=200809L -DXINYI_CPU_HZ=$cpu_hz -ffile-prefix-map=$repo=. -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections"
target=${TARGET_FLAGS:--march=rv32ima -mabi=ilp32 -mstrict-align -static}
includes="-I$repo/linux/xinyi_board -I$repo/linux/xinyi -I$repo/linux/pikafish -I$repo/linux/vision -I$repo/linux/voice_ctc -I$repo/linux/voice_speech -I$repo/linux/voice -I$repo/linux/mac_accel -I$repo/linux/picture_new -I$repo/sw/xiangqi -I$repo/sw/bootloader"
sources='linux/xinyi_board/main.c linux/xinyi_board/runtime.c linux/xinyi_board/platform.c linux/xinyi_board/accelerator_idle.c linux/xinyi_board/coach_task.c linux/xinyi_board/engine_bridge.c linux/xinyi_board/voice_bridge.c linux/xinyi_board/voice_notation.c linux/xinyi_board/speech_task.c linux/xinyi/xinyi_product.c linux/xinyi/coremark/process.c linux/picture_new/coach_protocol.c linux/voice_speech/xq_speech.c linux/voice_ctc/xqvoice_session.c linux/vision/xq_camera.c linux/vision/xq_camera_capture_retry.c linux/vision/xq_picture.c linux/vision/xq_vision.c sw/xiangqi/xiangqi_search.c sw/xiangqi/xiangqi_pikafish_link.c sw/bootloader/crc32_fast.c'
hash_sources() {
 for source in $sources; do sha256sum "$repo/$source"; done
 for directory in linux/xinyi_board linux/xinyi linux/pikafish linux/vision linux/voice_ctc linux/voice_speech linux/voice linux/mac_accel linux/picture_new sw/xiangqi sw/bootloader; do
  find "$repo/$directory" -name '*.h' -type f -exec sha256sum {} \;
 done
 sha256sum "$repo/config/clocks.json"
 sha256sum "$repo/linux/xinyi/xinyi_fb.c" "$repo/linux/pikafish/xiangqi_fb_gui_1080.c" "$repo/linux/pikafish/gui1080_config.h" "$repo/linux/mac_accel/pango_mac_uapi.h" "$repo/linux/xinyi_board/build.sh"
}
hash_sources > "$out/source-before.sha256"
i=0
for source in $sources; do
 "$cc" $flags $target $includes -pthread -c "$repo/$source" -o "$out/obj/$i.o"
 i=$((i+1))
done
"$cc" $flags $target $includes -DVIDEO_FB_LINUX_MMAP -I"$repo/linux/pikafish/include" \
 -include "$repo/linux/pikafish/gui1080_config.h" \
 -c "$repo/linux/xinyi/xinyi_fb.c" -o "$out/obj/renderer.o"
"$cc" $target -pthread "$out/obj/"*.o -Wl,--gc-sections -lm -o "$out/xinyi-one"
hash_sources > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
"$cc" --version > "$out/compiler.txt"
sha256sum "$out/xinyi-one" > "$out/SHA256SUMS.txt"
echo XINYI_REAL_PRODUCT_BUILD_PASS_NOT_BOARD
