#!/bin/sh
set -eu
repo=/mnt/g/fpga/performance_soc_main_latest
src=$repo/sw/bootloader
out=$repo/build/pikafish_sd_loader
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
objcopy=/opt/toolchain/bin/riscv32-linux-musl-objcopy
common='-march=rv32ima -mabi=ilp32 -mcmodel=medany -mno-relax -msmall-data-limit=0 -mstrict-align -ffreestanding -fno-builtin -fno-common -ffunction-sections -fdata-sections -Os -Wall -Wextra -Werror'
if [ "${SD_LOADER_VARIANT:-probe}" = bridge-release ]; then
  common="$common -DSD_LOADER_BRIDGE_RELEASE_BOOT=1"
  output=loader-bridge-release.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = bridge-nonblock ]; then
  common="$common -DSD_LOADER_BRIDGE_NONBLOCK_BOOT=1"
  output=loader-bridge-nonblock.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = old ]; then
  common="$common -DSD_LOADER_OLD_BOOT=1"
  output=loader-old.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = old-standalone ]; then
  common="$common -DSD_LOADER_OLD_BOOT=1 -DSD_LOADER_STANDALONE_DIAG=1"
  output=loader-old-standalone.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = fix ]; then
  common="$common -DSD_LOADER_GUI_FIX_BOOT=1"
  output=loader-fix.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = compact ]; then
  common="$common -DSD_LOADER_COMPACT_GUI_BOOT=1"
  output=loader-compact.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = standalone ]; then
  common="$common -DSD_LOADER_COMPACT_GUI_BOOT=1 -DSD_LOADER_STANDALONE_DIAG=1"
  output=loader-standalone.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min ]; then
  common="$common -DSD_LOADER_MIN_GUI_BOOT=1"
  output=loader-min.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-standalone ]; then
  common="$common -DSD_LOADER_MIN_GUI_BOOT=1 -DSD_LOADER_STANDALONE_DIAG=1"
  output=loader-min-standalone.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1"
  output=loader-min-shadow.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow-standalone ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1 -DSD_LOADER_STANDALONE_DIAG=1"
  output=loader-min-shadow-standalone.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow-auto ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1 -DSD_LOADER_GUI_AUTOMOVE=1 -DSD_LOADER_SYNC_INITRD=1"
  output=loader-min-shadow-auto.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow-timerhw ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1 -DSD_LOADER_GUI_AUTOMOVE=1 -DSD_LOADER_TIMER_HW_PROBE=1"
  output=loader-min-shadow-timerhw.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow-smode-timer ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1 -DSD_LOADER_SMODE_TIMER_PROBE=1"
  output=loader-min-shadow-smode-timer.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow-smode-bridge ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1 -DSD_LOADER_SMODE_TIMER_PROBE=1 -DSD_LOADER_SBI_TIMER_BRIDGE=1"
  output=loader-min-shadow-smode-bridge.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = min-shadow-gui-bridge ]; then
  common="$common -DSD_LOADER_MIN_SHADOW_BOOT=1 -DSD_LOADER_SBI_TIMER_BRIDGE=1 -DSD_LOADER_GUI_AUTOMOVE=1 -DSD_LOADER_SYNC_INITRD=1"
  output=loader-min-shadow-gui-bridge.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = nofs ]; then
  common="$common -DSD_LOADER_NO_SCRIPTS_BOOT=1"
  output=loader-nofs.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = nofs-sync ]; then
  common="$common -DSD_LOADER_NO_SCRIPTS_BOOT=1 -DSD_LOADER_SYNC_INITRD=1"
  output=loader-nofs-sync.bin
elif [ "${SD_LOADER_VARIANT:-probe}" = pad ]; then
  common="$common -DSD_LOADER_PAD_BOOT=1"
  output=loader-pad.bin
else
  output=loader.bin
fi
"$cc" $common -I "$src" -c "$out/start.S" -o "$out/start.o"
for item in runtime.c sd_native.c fat_ro.c crc32_fast.c; do
  "$cc" $common -I "$src" -c "$src/$item" -o "$out/${item%.*}.o"
done
"$cc" $common -I "$src" -c "$out/loader.c" -o "$out/loader.o"
"$cc" -march=rv32ima -mabi=ilp32 -nostdlib -static -Wl,--gc-sections,--no-relax -Wl,-T,"$out/link.ld" -Wl,-Map,"$out/loader.map" \
  "$out/start.o" "$out/runtime.o" "$out/sd_native.o" "$out/fat_ro.o" "$out/crc32_fast.o" "$out/loader.o" -lgcc -o "$out/loader.elf"
"$objcopy" -O binary "$out/loader.elf" "$out/$output"
file "$out/loader.elf"
wc -c "$out/$output"
