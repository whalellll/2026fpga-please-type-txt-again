#!/bin/sh
# Build a private CPU60 software candidate; never overwrite linux/boot.
set -eu
repo=$1
archive=$2
base_config=$3
out=$4
work=$5
case "$out" in "$repo"/build/*) ;; *) exit 2;; esac
case "$work" in /var/tmp/xinyi-kernel-*) ;; *) exit 2;; esac
test ! -e "$out"
test ! -e "$work"
mkdir -p "$out/inputs" "$work/source"
echo '7e068b5e0d26a62b10e5320b25dce57588cbbc6f781c090442138c9c9c3271b2  '"$archive" | sha256sum -c -
tar -xJf "$archive" --strip-components=1 -C "$work/source"
tree="$work/source"
for name in pango_mac.c pango_mac_copy_chunks.h pango_mac_io32.h pango_vision_io_modes.h; do
 cp "$repo/linux/mac_accel/kernel/$name" "$tree/drivers/misc/$name"
 cp "$repo/linux/mac_accel/kernel/$name" "$out/inputs/$name"
done
cp "$repo/linux/mac_accel/pango_mac_uapi.h" "$tree/include/uapi/linux/pango_mac.h"
cp "$repo/linux/mac_accel/pango_mac_uapi.h" "$out/inputs/"
cp "$repo/linux/audio/kernel/pango_audio.c" "$tree/drivers/misc/"
cp "$repo/linux/audio/pango_audio_uapi.h" "$tree/include/uapi/linux/pango_audio.h"
cp "$repo/linux/voice_accel/kernel/pango_voice.c" "$tree/drivers/misc/"
cp "$repo/linux/voice_accel/pango_voice_uapi.h" "$tree/include/uapi/linux/pango_voice.h"
cp "$repo/linux/voice_accel/kernel/pango_voice.c" "$repo/linux/voice_accel/pango_voice_uapi.h" "$out/inputs/"
cp "$repo/linux/picture_new/platform/cpu60.dts" "$out/inputs/"
cp "$repo/linux/picture_new/platform/display.json" "$out/inputs/"
patch -s -d "$tree" -p1 < "$repo/linux/mac_accel/linux-5.14-conv-integration.patch"
cat "$repo/linux/voice_accel/kernel/Kconfig" >> "$tree/drivers/misc/Kconfig"
cat "$repo/linux/voice_accel/kernel/Makefile" >> "$tree/drivers/misc/Makefile"
cp "$base_config" "$out/base.config"
cp "$base_config" "$tree/.config"
"$tree/scripts/config" --file "$tree/.config" --enable MISC_DEVICES \
 --enable PANGO_MAC_ACCEL --enable PANGO_AUDIO_CAPTURE --enable PANGO_VOICE_ACCEL
make -s -C "$tree" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
make -s -C "$tree" -j4 ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- Image
cp "$tree/arch/riscv/boot/Image" "$out/Image"
cp "$tree/.config" "$out/kernel.config"
# Template only: initrd bounds must be rebound to the final private rootfs
# before deployment. The compiled display/memory contract is checked here.
"$tree/scripts/dtc/dtc" -I dts -O dtb -o "$out/contract.dtb" "$out/inputs/cpu60.dts"
"$tree/scripts/dtc/dtc" -I dtb -O dts -o "$out/contract.roundtrip.dts" "$out/contract.dtb"
"$tree/scripts/diffconfig" "$out/base.config" "$out/kernel.config" > "$out/config.diff"
grep -q '^CONFIG_32BIT=y$' "$out/kernel.config"
grep -q '^# CONFIG_RISCV_ISA_C is not set$' "$out/kernel.config"
grep -q '^# CONFIG_FPU is not set$' "$out/kernel.config"
for symbol in PANGO_MAC_ACCEL PANGO_AUDIO_CAPTURE PANGO_VOICE_ACCEL; do
 grep -q "^CONFIG_${symbol}=y$" "$out/kernel.config"
done
riscv64-linux-gnu-gcc --version > "$out/compiler.txt"
sha256sum "$out/Image" "$out/contract.dtb" "$out/kernel.config" "$out/inputs/"* > "$out/SHA256SUMS.txt"
echo XINYI_CPU60_PRIVATE_KERNEL_BUILD_PASS_NOT_BOARD
