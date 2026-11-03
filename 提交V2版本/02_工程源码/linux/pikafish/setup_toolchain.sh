#!/bin/sh
set -eu

repo=/build/musl-cross-make
commit=227df8b99103f9c59f6570babf892978e293082f
jobs=${TOOLCHAIN_BUILD_JOBS:-2}
cross=/opt/toolchain/bin/riscv32-linux-musl

validate_toolchain() {
    tmp=/tmp/pikafish-toolchain-check.$$
    trap 'rm -f "$tmp"' EXIT HUP INT TERM
    "$cross-gcc" -march=rv32ima -mabi=ilp32 -static /port/toolchain_smoke.c -o "$tmp"
    "$cross-readelf" -h "$tmp" | grep -q 'Class:.*ELF32'
    if "$cross-readelf" -h "$tmp" | grep -Eq 'single-float ABI|double-float ABI|quad-float ABI'; then
        echo 'toolchain produced a hard-float ELF' >&2
        return 1
    fi
    qemu-riscv32 "$tmp"
    rm -f "$tmp"
    trap - EXIT HUP INT TERM
}

if [ -x "$cross-g++" ] && validate_toolchain; then
    echo 'RV32IMA ilp32 musl toolchain already prepared'
    exit 0
fi

mkdir -p /build /opt/toolchain
if [ ! -d "$repo/.git" ]; then
    rm -rf "$repo"
    mkdir -p "$repo"
    git -C "$repo" init
    git -C "$repo" remote add origin https://github.com/richfelker/musl-cross-make.git
    git -C "$repo" fetch --depth 1 origin "$commit"
    git -C "$repo" checkout --detach FETCH_HEAD
fi

actual_commit=$(git -C "$repo" rev-parse HEAD)
if [ "$actual_commit" != "$commit" ]; then
    echo "musl-cross-make commit mismatch: $actual_commit" >&2
    exit 1
fi

config_id=rv32ima-ilp32-static-v1
config_stamp=/build/.pikafish-toolchain-config
if [ ! -f "$config_stamp" ] || [ "$(cat "$config_stamp")" != "$config_id" ]; then
    target_build="$repo/build/local/riscv32-linux-musl"
    case "$target_build" in
        /build/musl-cross-make/build/local/riscv32-linux-musl) ;;
        *) echo "unsafe toolchain build path: $target_build" >&2; exit 1 ;;
    esac
    rm -rf "$target_build/obj_gcc" "$target_build/obj_musl" "$target_build/obj_sysroot"
    printf '%s\n' "$config_id" > "$config_stamp"
fi

cat > "$repo/config.mak" <<'EOF'
TARGET = riscv32-linux-musl
OUTPUT = /opt/toolchain
DL_CMD = python3 /port/download.py
GNU_SITE = https://ftp.gnu.org/gnu
GCC_CONFIG += --with-arch=rv32ima --with-abi=ilp32
COMMON_CONFIG += --disable-nls
GCC_CONFIG += --disable-shared --disable-libquadmath --disable-decimal-float --disable-libitm --disable-fixed-point
EOF

make -C "$repo" -j"$jobs"
make -C "$repo" install

test -x "$cross-g++"
validate_toolchain
echo 'RV32IMA ilp32 musl toolchain prepared'
