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
case "$cpu_hz" in 60000000|70000000|75000000) ;; *) echo 'Unreviewed Xinyi CPU clock' >&2; exit 2;; esac
printf '%s\n' "$cpu_hz" > "$out/cpu-hz.txt"
flags="-std=c11 -D_POSIX_C_SOURCE=200809L -DXINYI_CPU_HZ=$cpu_hz -ffile-prefix-map=$repo=. -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections"
gui_double=${XINYI_GUI_DOUBLE_BUFFER:-0}
case "$gui_double" in 0|1) ;; *) echo 'Invalid GUI buffering option' >&2; exit 2;; esac
flags="$flags -DXINYI_GUI_DOUBLE_BUFFER=$gui_double"
printf 'gui_double_buffer=%s\n' "$gui_double" > "$out/gui-config.txt"
ram_render=${XINYI_GUI_RAM_RENDER:-0}
case "$ram_render" in 0) ;; 1) test "$gui_double" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_RAM_RENDER=$ram_render"
printf 'gui_ram_render=%s\n' "$ram_render" >> "$out/gui-config.txt"
feedback=${XINYI_UI_FEEDBACK:-0}
case "$feedback" in 0|1) ;; *) echo 'Invalid UI feedback option' >&2; exit 2;; esac
flags="$flags -DXINYI_UI_FEEDBACK=$feedback"
printf 'ui_feedback=%s\n' "$feedback" >> "$out/gui-config.txt"
move_audio=${XINYI_COACH_MOVE_AUDIO:-0}
case "$move_audio" in 0|1) ;; *) echo 'Invalid move audio option' >&2; exit 2;; esac
flags="$flags -DXINYI_COACH_MOVE_AUDIO=$move_audio"
printf 'coach_move_audio=%s\n' "$move_audio" >> "$out/gui-config.txt"
home_r13=${XINYI_HOME_R13:-0}
case "$home_r13" in 0) ;; 1) test "$gui_double:$feedback" = 1:1 ;; *) exit 2;; esac
flags="$flags -DXINYI_HOME_R13=$home_r13"
printf 'home_r13=%s\n' "$home_r13" >> "$out/gui-config.txt"
home_r15=${XINYI_HOME_R15:-0}
case "$home_r15" in 0) ;; 1) test "$home_r13" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_HOME_R15=$home_r15"
printf 'home_r15=%s\n' "$home_r15" >> "$out/gui-config.txt"
page_deltas=${XINYI_GUI_PAGE_DELTAS:-0}
case "$page_deltas" in 0) ;; 1) test "$home_r15:$gui_double:$cpu_hz:$ram_render" = 1:1:60000000:0 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_PAGE_DELTAS=$page_deltas"
printf 'gui_page_deltas=%s\n' "$page_deltas" >> "$out/gui-config.txt"
pair_deltas=${XINYI_GUI_PAIR_DELTAS:-0}
case "$pair_deltas" in 0) ;; 1) test "$page_deltas" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_PAIR_DELTAS=$pair_deltas"
printf 'gui_pair_deltas=%s\n' "$pair_deltas" >> "$out/gui-config.txt"
nav_diag=${XINYI_UI_NAV_DIAG:-0}
case "$nav_diag" in 0) ;; 1) test "$home_r13" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_UI_NAV_DIAG=$nav_diag"
printf 'ui_nav_diag=%s\n' "$nav_diag" >> "$out/gui-config.txt"
battle_r17=${XINYI_BATTLE_R17:-0}
case "$battle_r17" in 0) ;; 1) test "$home_r15:$gui_double:$feedback:$move_audio" = 1:1:1:1 ;; *) exit 2;; esac
flags="$flags -DXINYI_BATTLE_R17=$battle_r17"
printf 'battle_r17=%s\n' "$battle_r17" >> "$out/gui-config.txt"
asr_voice4=${XINYI_ASR_VOICE4:-0}
case "$asr_voice4" in 0) ;; 1) test "$battle_r17" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_ASR_VOICE4=$asr_voice4"
printf 'asr_voice4=%s\n' "$asr_voice4" >> "$out/gui-config.txt"
metric_deltas=${XINYI_GUI_METRIC_DELTAS:-0}
case "$metric_deltas" in 0) ;; 1) test "$battle_r17:$pair_deltas:$cpu_hz" = 1:1:60000000 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_METRIC_DELTAS=$metric_deltas"
printf 'gui_metric_deltas=%s\n' "$metric_deltas" >> "$out/gui-config.txt"
preview_retry=${XINYI_PREVIEW_RETRY_R19:-0}
case "$preview_retry" in 0) ;; 1) test "$home_r13" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_PREVIEW_RETRY_R19=$preview_retry"
printf 'preview_retry_r19=%s\n' "$preview_retry" >> "$out/gui-config.txt"
fast_nav=${XINYI_GUI_FAST_NAV_R21:-0}
case "$fast_nav" in 0) ;; 1) test "$battle_r17:$gui_double:$metric_deltas:$asr_voice4" = 1:1:1:0 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_FAST_NAV_R21=$fast_nav"
printf 'gui_fast_nav_r21=%s\n' "$fast_nav" >> "$out/gui-config.txt"

spans=${XINYI_GUI_SPANS_R21:-0}
case "$spans" in 0) ;; 1) test "$fast_nav" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_SPANS_R21=$spans"
printf 'gui_spans_r21=%s\n' "$spans" >> "$out/gui-config.txt"
gui_cache=${XINYI_GUI_CACHE_R21:-0}
case "$gui_cache" in 0) ;; 1) test "$fast_nav:$gui_double:$spans:$cpu_hz" = 1:1:0:60000000 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_CACHE_R21=$gui_cache"
printf 'gui_cache_r21=%s\n' "$gui_cache" >> "$out/gui-config.txt"
linear=${XINYI_GUI_LINEAR_R21:-0}
case "$linear" in 0) ;; 1) test "$gui_cache:$fast_nav:$spans" = 1:1:0 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_LINEAR_R21=$linear"
printf 'gui_linear_r21=%s\n' "$linear" >> "$out/gui-config.txt"
commands=${XINYI_GUI_COMMANDS_R21:-0}
case "$commands" in 0) ;; 1) test "$gui_cache:$fast_nav:$spans:$linear" = 1:1:0:0 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_COMMANDS_R21=$commands"
printf 'gui_commands_r21=%s\n' "$commands" >> "$out/gui-config.txt"
load8=${XINYI_GUI_LOAD8_R21:-0}
case "$load8" in 0) ;; 1) test "$commands:$gui_cache" = 1:1 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_LOAD8_R21=$load8"
printf 'gui_load8_r21=%s\n' "$load8" >> "$out/gui-config.txt"
palette=${XINYI_GUI_PALETTE_R21:-0}
case "$palette" in 0) ;; 1) test "$gui_cache:$fast_nav:$spans:$linear:$commands:$load8" = 1:1:0:0:0:0 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_PALETTE_R21=$palette"
printf 'gui_palette_r21=%s\n' "$palette" >> "$out/gui-config.txt"
row_nav=${XINYI_GUI_ROW_NAV_R22:-0}
case "$row_nav" in 0) ;; 1) test "$fast_nav:$gui_cache:$spans:$linear:$commands:$load8:$palette" = 1:1:0:0:0:0:0 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_ROW_NAV_R22=$row_nav"
printf 'gui_row_nav_r22=%s\n' "$row_nav" >> "$out/gui-config.txt"
row_scalar=${XINYI_GUI_ROW_SCALAR_R23:-0}
case "$row_scalar" in 0) ;; 1) test "$row_nav" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_GUI_ROW_SCALAR_R23=$row_scalar"
printf 'gui_row_scalar_r23=%s\n' "$row_scalar" >> "$out/gui-config.txt"

target=${TARGET_FLAGS:--march=rv32ima -mabi=ilp32 -mstrict-align -static}
includes="-I$repo/linux/xinyi_board -I$repo/linux/xinyi -I$repo/linux/pikafish -I$repo/linux/vision -I$repo/linux/voice_ctc -I$repo/linux/voice_speech -I$repo/linux/voice -I$repo/linux/mac_accel -I$repo/linux/picture_new -I$repo/sw/xiangqi -I$repo/sw/bootloader"
sources='linux/xinyi_board/main.c linux/xinyi_board/runtime.c linux/xinyi_board/platform.c linux/xinyi_board/accelerator_idle.c linux/xinyi_board/coach_task.c linux/xinyi_board/engine_bridge.c linux/xinyi_board/voice_bridge.c linux/xinyi_board/voice_notation.c linux/xinyi_board/speech_task.c linux/xinyi/xinyi_product.c linux/xinyi/coremark/process.c linux/picture_new/coach_protocol.c linux/voice_speech/xq_speech.c linux/voice_ctc/xqvoice_session.c linux/vision/xq_camera.c linux/vision/xq_camera_capture_retry.c linux/vision/xq_picture.c linux/vision/xq_vision.c sw/xiangqi/xiangqi_search.c sw/xiangqi/xiangqi_pikafish_link.c sw/bootloader/crc32_fast.c'
if test "$preview_retry" = 1;then sources="$sources linux/vision/xq_camera_retry.c";fi
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
