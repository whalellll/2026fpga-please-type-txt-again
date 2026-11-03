#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo"
out="$repo/build/picture-host-linux"
mkdir -p "$out"
cc=${CC:-gcc}
shared='linux/vision/xq_picture.c linux/vision/xq_vision.c linux/vision/xq_grid.c linux/vision/xq_speech.c sw/xiangqi/xiangqi_pikafish_link.c sw/xiangqi/xiangqi_search.c'
for name in picture picture_hid grid speech; do
    "$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/xiangqi \
        "linux/vision/test_$name.c" $shared -o "$out/$name"
    "$out/$name"
done
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/xiangqi \
    linux/vision/test_geometry.c linux/vision/xq_geometry.c -o "$out/geometry"
"$out/geometry"
"$cc" -std=c11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Ilinux/mac_accel \
    linux/vision/test_mac_tiles.c linux/vision/xq_mac.c -o "$out/mac-tiles"
"$out/mac-tiles"
for name in roi roi_pipeline; do
    "$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/xiangqi \
        "linux/vision/test_$name.c" linux/vision/xq_roi.c linux/vision/xq_roi_pipeline.c \
        linux/vision/xq_grid.c linux/vision/xq_vision.c sw/xiangqi/xiangqi_search.c \
        sw/xiangqi/xiangqi_pikafish_link.c -lm -o "$out/$name"
    "$out/$name"
done
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/xiangqi \
    linux/vision/test_speech_linux.c -Wl,--wrap=read,--wrap=write -o "$out/speech-linux"
"$out/speech-linux"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/xiangqi -Isw/bootloader \
    linux/vision/test_camera.c linux/vision/xq_camera.c -o "$out/camera"
"$out/camera"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/bootloader \
    linux/vision/test_boot_preinit.c sw/bootloader/crc32_fast.c -o "$out/preinit"
"$out/preinit"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Ilinux/vision -Isw/bootloader -Isw/xiangqi \
    linux/vision/test_camera_retry.c linux/vision/xq_camera_retry.c -o "$out/camera-retry"
"$out/camera-retry"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Isw/video -Isw/xiangqi \
    linux/vision/test_picture_renderer.c -o "$out/renderer"
"$out/renderer"
"$cc" -std=gnu11 -O2 -pthread -Wall -Wextra -Werror -Ilinux/vision -Isw/xiangqi -Isw/video -Isw/bootloader \
    linux/vision/test_picture_gui.c linux/vision/xq_roi.c sw/bootloader/crc32_fast.c sw/xiangqi/xiangqi_mouse_input.c $shared -lm -o "$out/gui"
"$out/gui" "$out/gui.stub"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -Isw/bootloader \
    linux/vision/test_picture_png.c sw/bootloader/png_rgb565.c sw/bootloader/crc32_fast.c -o "$out/png"
"$out/png" "$out/synthetic.png"
python3 -B scripts/test_picture_png.py "$out/synthetic.png"
python3 -B scripts/test_picture_model.py
python3 -B scripts/test_picture_three_model.py
python3 -B scripts/test_picture_speech_assets.py
echo PICTURE_LINUX_HOST_TEST_PASS
