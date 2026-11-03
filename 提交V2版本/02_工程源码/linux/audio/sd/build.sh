#!/bin/sh
# Build isolated user-space SD candidate, preserving bootloader/kernel/RTL.
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$src/../../.." && pwd)
output=${1:?output directory required}
mkdir -p "$output"
output=$(CDPATH= cd -- "$output" && pwd)
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
common="-std=gnu11 -march=rv32ima -mabi=ilp32 -O2 -flto -ffunction-sections -fdata-sections -Wall -Wextra -Werror"
"$cc" $common -DSOC_H -include "$src/sd_linux_port.h" -I"$project/sw/bootloader" \
  -c "$project/sw/bootloader/sd_native.c" -o "$output/sd_native.o"
"$cc" $common -static -Wl,--gc-sections -I"$src" -I"$project/sw/bootloader" \
  "$src/xqvoice_sd.c" "$src/voice_sd_backend.c" "$src/fat_voice.c" \
  "$project/sw/bootloader/fat_ro.c" "$project/sw/bootloader/crc32_fast.c" \
  "$output/sd_native.o" -o "$output/xqvoice-sd"
/opt/toolchain/bin/riscv32-linux-musl-strip "$output/xqvoice-sd"
"$cc" $common -static -Wl,--gc-sections "$project/linux/audio/xqaudio_capture.c" -o "$output/xqaudio-capture"
/opt/toolchain/bin/riscv32-linux-musl-strip "$output/xqaudio-capture"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -DVOICE_SD_IMAGE_TEST \
  -I"$src" -I"$project/sw/bootloader" \
  "$src/xqvoice_sd.c" "$src/voice_sd_backend.c" "$src/fat_voice.c" \
  "$project/sw/bootloader/fat_ro.c" "$project/sw/bootloader/crc32_fast.c" \
  -o "$output/xqvoice-sd-image-test"
file "$output/xqvoice-sd"
sha256sum "$output/xqvoice-sd"
printf '%s\n' VOICE_SD_RV32_BUILD_PASS
