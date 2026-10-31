#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
out=${1:?fresh output directory}
cc=${CC:-gcc}
mkdir -p "$out/obj"
flags="-std=c11 -D_POSIX_C_SOURCE=200809L -O2 -Wall -Wextra ${CFLAGS:-} -I$repo/sw/coremark -include $repo/linux/xinyi/coremark/core_portme.h"
objects=""
for name in core_main core_list_join core_matrix core_state core_util; do
 extra=""
 if [ "$name" = core_main ]; then extra="-Dmain=xy_cm_upstream_main"; fi
 "$cc" $flags $extra -c "$repo/sw/coremark/$name.c" -o "$out/obj/$name.o"
 objects="$objects $out/obj/$name.o"
done
"$cc" $flags "$repo/linux/xinyi/coremark/benchmark.c" $objects -o "$out/xinyi-coremark"
echo XINYI_COREMARK_BUILD_PASS
