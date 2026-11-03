#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
stage="$repo/build/pikafish-rv32/source/src"
compiler=/opt/toolchain/bin/riscv32-linux-musl-g++
test -x "$compiler"
test -f "$stage/pikafish_mmio_shadow.h"
make -C "$stage" -j"${PIKAFISH_BUILD_JOBS:-2}" build ARCH=riscv32 COMP=gcc \
  CXX="$compiler" \
  EXTRACXXFLAGS='-DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD'
file "$stage/pikafish"
"${compiler%g++}readelf" -h "$stage/pikafish" | grep -E 'Class:|Machine:|Flags:'
echo "PIKAFISH_ACCEL_ELF_CROSS_BUILD_PASS path=$stage/pikafish"
