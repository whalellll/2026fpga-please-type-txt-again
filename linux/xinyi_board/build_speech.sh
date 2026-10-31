#!/bin/sh
# Standalone speech helper only. Never install or touch audio hardware here.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=$1
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
cc=${CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
move=${XINYI_COACH_MOVE_AUDIO:-0}
case "$move" in 0|1) ;; *) exit 2;; esac
flags="-std=gnu11 -O2 -Wall -Wextra -Werror -ffile-prefix-map=$repo=. -DXINYI_COACH_MOVE_AUDIO=$move"
battle=${XINYI_BATTLE_R17:-0}
case "$battle" in 0) ;; 1) test "$move" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_BATTLE_R17=$battle"
rt_candidate=${XINYI_SPEECH_RT_CANDIDATE:-0}
case "$rt_candidate" in 0) ;; 1) test "$battle" = 1 ;; *) exit 2;; esac
flags="$flags -DXINYI_SPEECH_RT_CANDIDATE=$rt_candidate"
target=${TARGET_FLAGS:--march=rv32ima -mabi=ilp32 -mstrict-align -static}
sources='linux/xinyi_board/speech_worker.c linux/voice_speech/xq_speech.c linux/voice_speech/xq_speech_linux.c sw/xiangqi/xiangqi_search.c sw/xiangqi/xiangqi_pikafish_link.c'
headers='linux/xinyi_board/speech_task.h linux/xinyi_board/gui_options.h linux/voice_speech/xq_speech.h linux/voice_speech/xq_move_speech.h linux/voice_speech/xq_whole_speech.h sw/xiangqi/xiangqi_search.h sw/xiangqi/xiangqi_pikafish_link.h'
if test "$battle" = 1; then
 sources="$sources linux/voice_speech/xq_whole_bank.c"
 headers="$headers linux/voice_speech/xq_whole_bank.h"
fi
candidate_inputs=''
if test "$rt_candidate" = 1; then
 candidate_inputs='linux/voice_speech/xq_speech_linux_candidate.inc linux/voice_speech/xq_whole_bank_candidate.inc'
fi
hash_sources(){ for source in $sources $headers $candidate_inputs linux/xinyi_board/build_speech.sh; do sha256sum "$repo/$source"; done; }
hash_sources > "$out/source-before.sha256"
set --
for source in $sources; do set -- "$@" "$repo/$source"; done
"$cc" $flags $target -I"$repo/linux/xinyi_board" -I"$repo/linux/voice_speech" -I"$repo/sw/xiangqi" -MM "$@" > "$out/source-dependencies.d"
"$cc" $flags $target -I"$repo/linux/xinyi_board" -I"$repo/linux/voice_speech" -I"$repo/sw/xiangqi" "$@" -o "$out/xinyi-speech-worker"
hash_sources > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
printf 'coach_move_audio=%s\n' "$move" > "$out/speech-config.txt"
printf 'battle_r17=%s\n' "$battle" >> "$out/speech-config.txt"
printf 'speech_rt_candidate=%s\n' "$rt_candidate" >> "$out/speech-config.txt"
"$cc" --version > "$out/compiler.txt"
echo XINYI_SPEECH_BUILD_PASS_NOT_BOARD
