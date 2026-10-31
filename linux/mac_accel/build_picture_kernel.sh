#!/bin/sh
# Isolated software candidate; no boot-media or FPGA programming operations.
set -eu
repo=$1
archive=$2
out=$3
work=$4
test ! -e "$out"
test ! -e "$work"
mkdir -p "$out/inputs" "$work/source"
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
cp "$repo/linux/soc.dts" "$out/inputs/"
cp "$repo/linux/picture_roi.dts" "$out/inputs/"
patch -s -d "$tree" -p1 < "$repo/linux/mac_accel/linux-5.14-conv-integration.patch"
"$tree/scripts/extract-ikconfig" "$repo/linux/boot/Image" > "$out/base.config"
test -s "$out/base.config"
cp "$out/base.config" "$tree/.config"
"$tree/scripts/config" --file "$tree/.config" --enable MISC_DEVICES --enable PANGO_MAC_ACCEL --enable PANGO_AUDIO_CAPTURE
make -s -C "$tree" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
make -s -C "$tree" -j4 ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- Image
cp "$tree/arch/riscv/boot/Image" "$out/Image"
cp "$tree/.config" "$out/kernel.config"
"$tree/scripts/dtc/dtc" -i "$out/inputs" -I dts -O dtb -o "$out/soc.dtb" "$out/inputs/picture_roi.dts"
"$tree/scripts/diffconfig" "$out/base.config" "$out/kernel.config" > "$out/config.diff"
grep -q '^CONFIG_32BIT=y$' "$out/kernel.config"
grep -q '^# CONFIG_RISCV_ISA_C is not set$' "$out/kernel.config"
grep -q '^# CONFIG_FPU is not set$' "$out/kernel.config"
grep -q '^CONFIG_PANGO_MAC_ACCEL=y$' "$out/kernel.config"
test "$(wc -c < "$out/Image")" -le "$(($(wc -c < "$repo/linux/boot/Image") + 1048576))"
riscv64-linux-gnu-gcc --version > "$out/compiler.txt"
sha256sum "$out/Image" "$out/soc.dtb" "$out/kernel.config" "$out/inputs/"* > "$out/SHA256SUMS.txt"
printf '%s\n' PICTURE_ROI_KERNEL_BUILD_PASS
