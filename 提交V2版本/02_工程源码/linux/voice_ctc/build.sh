#!/bin/sh
# Software candidate only; never writes boot files, SD or hardware settings.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=${1:?new output directory}
cc=${CC_RV32:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
test ! -e "$out"
mkdir -p "$out"
src="$repo/linux/voice_ctc"
"$cc" -std=gnu11 -O2 -fwrapv -Wall -Wextra -Werror -march=rv32ima -mabi=ilp32 \
    -static -pthread -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 \
    "$src/xqvoice_runtime.c" "$src/xqvoice_frontend.c" "$src/xqvoice_decode.c" \
    "$src/xqvoice_capture.c" "$src/xqvoice_profile.c" "$src/voice_small_backend.c" \
    -o "$out/xqvoice-small-cnn"
"${cc%gcc}readelf" -h -A "$out/xqvoice-small-cnn"
sha256sum "$out/xqvoice-small-cnn" "$src/balanced24.bin"
echo XINYI_VOICE_RV32_BUILD_PASS_NOT_BOARD
