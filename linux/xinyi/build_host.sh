#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
out=${1:-"$repo/build/xinyi-host-20261024/native"}
mkdir -p "$out"
cc=${CC:-gcc}
common="-std=c11 -D_POSIX_C_SOURCE=200809L -O2 -Wall -Wextra -Werror -I$repo/linux/xinyi -I$repo/sw/xiangqi"
sources="$repo/linux/xinyi/xinyi_product.c $repo/linux/xinyi/xinyi_render.c $repo/sw/xiangqi/xiangqi_search.c"
"$cc" $common $sources "$repo/linux/xinyi/test_product.c" -lm -o "$out/test-product"
"$out/test-product"
gui="$common -DVIDEO_FB_LINUX_MMAP -DXINYI_HOST_PREVIEW -I$repo/linux/pikafish -I$repo/linux/pikafish/include -I$repo/linux/voice -include $repo/linux/pikafish/gui1080_config.h"
"$cc" $gui -fPIC -shared $sources "$repo/linux/xinyi/xinyi_host.c" \
    "$repo/linux/xinyi/xinyi_fb.c" "$repo/linux/voice/xqvoice_protocol.c" \
    -lm -o "$out/libxinyi.so"
"$cc" $gui $sources "$repo/linux/xinyi/test_fb.c" \
    "$repo/linux/voice/xqvoice_protocol.c" -lm -o "$out/test-fb"
"$out/test-fb" "$out"
printf '%s\n' 'XINYI_HOST_BUILD_PASS native_controller actual_GUI1080_renderer synthetic_only'
