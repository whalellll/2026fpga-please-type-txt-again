#!/bin/sh
set -eu
ulimit -c 0
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
out=${1:-"$repo/build/xinyi-host-20261024/coremark-host"}
mkdir -p "$out"
gcc -std=c11 -D_POSIX_C_SOURCE=200809L -O2 -Wall -Wextra -Werror \
 -I"$repo/sw/coremark" -include "$repo/linux/xinyi/coremark/core_portme.h" \
 "$repo/linux/xinyi/coremark/benchmark.c" "$repo/linux/xinyi/coremark/test_calibration_fixture.c" \
 -o "$out/calibration-fixture"
python3 "$repo/linux/xinyi/coremark/test_calibration.py" "$out/calibration-fixture"
sh "$repo/linux/xinyi/coremark/build.sh" "$out"
gcc -std=c11 -O2 -Wall -Wextra -Werror -I"$repo/sw/xiangqi" \
 "$repo/linux/xinyi/coremark/process.c" "$repo/linux/xinyi/coremark/test_process.c" \
 "$repo/linux/xinyi/xinyi_product.c" "$repo/sw/xiangqi/xiangqi_search.c" \
 -o "$out/test-process"
"$out/test-process" "$out/xinyi-coremark" --cancel-only
gcc -std=c11 -O2 -Wall -Wextra -Werror -I"$repo/sw/xiangqi" \
 "$repo/linux/xinyi/coremark/process.c" "$repo/linux/xinyi/coremark/test_output.c" \
 "$repo/linux/xinyi/xinyi_product.c" "$repo/sw/xiangqi/xiangqi_search.c" \
 -o "$out/test-output"
"$out/test-output"
"$out/test-process" "$out/xinyi-coremark"
