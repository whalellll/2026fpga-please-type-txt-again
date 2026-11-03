#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source_archive="$repo_root/linux/sources/opensbi-1.3.1.tar.gz"
bridge_patch="$repo_root/linux/opensbi/0001-pg2l-time-cycle-bridge.patch"
work_root="$repo_root/build/opensbi_timer_bridge"
mkdir -p "$work_root"
printf '%s  %s\n' \
  ee5be2c582f9a837e9db88368220758e014dd694b566bb6c8efe1e50cfad0004 \
  "$source_archive" | sha256sum -c -

build_dir=$(mktemp -d "$work_root/source.XXXXXXXX")
tar -xzf "$source_archive" -C "$build_dir"
source_dir="$build_dir/opensbi-1.3.1"
patch -d "$source_dir" -p1 < "$bridge_patch"

make -C "$source_dir" -j4 \
  PLATFORM=generic \
  FW_TEXT_START=0x18000000 \
  FW_JUMP_ADDR=0x00400000 \
  FW_JUMP_FDT_ADDR=0x1a000000 \
  CROSS_COMPILE=riscv64-linux-gnu- \
  PLATFORM_RISCV_XLEN=32 \
  PLATFORM_RISCV_ISA=rv32ima_zicsr_zifencei \
  PLATFORM_RISCV_ABI=ilp32 \
  > "$work_root/build.log" 2>&1

firmware="$source_dir/build/platform/generic/firmware/fw_jump.bin"
firmware_elf="$source_dir/build/platform/generic/firmware/fw_jump.elf"
firmware_size=$(wc -c < "$firmware")
if (( firmware_size < 200000 || firmware_size > 327680 )); then
  echo "Unexpected OpenSBI size: $firmware_size" >&2
  exit 1
fi
riscv64-linux-gnu-readelf -h "$firmware_elf" > "$work_root/fw_jump.elf.header.txt"
grep -q 'Class: *ELF32' "$work_root/fw_jump.elf.header.txt"
grep -q 'Machine: *RISC-V' "$work_root/fw_jump.elf.header.txt"

cp "$firmware" "$work_root/fw_jump.bin"
sha256sum "$work_root/fw_jump.bin"
printf 'OPEN_SBI_TIMER_BRIDGE_BUILD_PASS bytes=%s output=%s\n' \
  "$firmware_size" "$work_root/fw_jump.bin"
