#!/bin/sh
# Software candidate only; never writes boot files, SD or hardware settings.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=${1:?new output directory}
cc=${CC_RV32:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
battle=${XINYI_BATTLE_R17:-0}
case "$battle" in 0|1) ;; *) echo 'Invalid voice utterance timing option' >&2; exit 2;; esac
test ! -e "$out"
mkdir -p "$out"
src="$repo/linux/voice_ctc"
hash_sources() {
    for input in build.sh xqvoice_runtime.c xqvoice_frontend.c xqvoice_frontend.h \
        xqvoice_decode.c xqvoice_decode.h xqvoice_capture.c xqvoice_capture.h \
        xqvoice_profile.c xqvoice_profile.h voice_small_backend.c xqvoice_mac.h \
        xqvoice_stream.inc xqvoice_worker.inc xqvoice_tables.h pango_audio_uapi.h; do
        sha256sum "$src/$input"
    done
    sha256sum "$repo/linux/voice_accel/pango_voice_uapi.h"
}
hash_sources > "$out/source-before.sha256"
printf 'battle_r17=%s\nhop_samples=320\nctc_beam=8\n' "$battle" > "$out/voice-config.txt"
"$cc" -std=gnu11 -O2 -fwrapv -Wall -Wextra -Werror -march=rv32ima -mabi=ilp32 \
    -static -pthread -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 -DXINYI_BATTLE_R17="$battle" \
    "$src/xqvoice_runtime.c" "$src/xqvoice_frontend.c" "$src/xqvoice_decode.c" \
    "$src/xqvoice_capture.c" "$src/xqvoice_profile.c" "$src/voice_small_backend.c" \
    -o "$out/xqvoice-small-cnn"
hash_sources > "$out/source-after.sha256"
cmp "$out/source-before.sha256" "$out/source-after.sha256"
"$cc" --version > "$out/compiler.txt"
"${cc%gcc}readelf" -h -A "$out/xqvoice-small-cnn"
sha256sum "$out/xqvoice-small-cnn" "$src/balanced24.bin"
echo XINYI_VOICE_RV32_BUILD_PASS_NOT_BOARD
