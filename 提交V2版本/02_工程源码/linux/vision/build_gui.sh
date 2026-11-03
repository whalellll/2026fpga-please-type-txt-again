#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work=${PIKAFISH_WORK:?first run build_pikafish_rv32.ps1 -PrepareOnly on the pinned source}
out=${XQ_PICTURE_OUT:-"$repo/build/picture-candidate"}
cc=${XQ_LINUX_CC:-/opt/toolchain/bin/riscv32-linux-musl-gcc}
cxx=${XQ_LINUX_CXX:-/opt/toolchain/bin/riscv32-linux-musl-g++}
march=${XQ_LINUX_MARCH:-rv32ima_zicsr_zifencei}
net_option=""
model_flags=""
if [ "${XQ_PICTURE_ENGINE_MODEL:-compressed-nnue}" = release-pff1 ]; then
    test -f "$work/picture_source_provenance.json"
    python3 - "$repo" "$work" <<'PY'
import hashlib,json,sys
from pathlib import Path
repo,work=map(Path,sys.argv[1:])
p=json.loads((work/'picture_source_provenance.json').read_text())
expected='de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260'
assert p['commit']=='56be6f65c21c6a3c7f9b884a976fc85d31d03287' and p['model_source']=='release-pff1'
assert p['pff_sha256']==expected and hashlib.sha256((repo/'linux/boot/pikafish.pff').read_bytes()).hexdigest()==expected
assert not (work/'src/pikafish.nnue').exists()
PY
    net_option="-o net"
    model_flags="-DNNUE_EMBEDDING_OFF"
fi
test -f "$work/src/pikafish_embedded.cpp"
mkdir -p "$out/gui-obj"
objects=""
for source in \
    linux/pikafish/xiangqi_pikafish_gui.c linux/pikafish/xiangqi_fb_gui_linux.c \
    sw/xiangqi/xiangqi_mouse_input.c sw/xiangqi/xiangqi_pikafish_link.c \
    sw/xiangqi/xiangqi_gui_command.c sw/xiangqi/xiangqi_search.c \
    linux/voice/xqvoice_protocol.c linux/voice/xqvoice_notation.c linux/voice/xqvoice_gui_ipc.c \
    linux/vision/xq_vision.c linux/vision/xq_picture.c linux/vision/xq_grid.c \
    linux/vision/xq_speech.c linux/vision/xq_speech_linux.c \
    linux/vision/xq_camera.c linux/vision/xq_camera_linux.c linux/vision/xq_camera_capture_retry.c; do
    name=$(basename "$source" .c)
    "$cc" -std=gnu11 -O2 -pthread -march="$march" -mabi=ilp32 \
        -mstrict-align -ffunction-sections -fdata-sections -Wall -Wextra -Werror \
        -DVIDEO_FB_LINUX_MMAP -DPIKAFISH_DIRECT_CORE -DXQ_PICTURE_INPUT \
        -I"$repo/linux/pikafish" -I"$repo/sw/video" -I"$repo/sw/xiangqi" \
        -I"$repo/linux/voice" -I"$repo/sw/bootloader" -I"$repo/linux/vision" \
        -c "$repo/$source" -o "$out/gui-obj/$name.o"
    objects="$objects $out/gui-obj/$name.o"
done
make -C "$work/src" ARCH=riscv32 COMP=gcc CXX="$cxx" objclean
make -C "$work/src" -j"${PIKAFISH_BUILD_JOBS:-2}" $net_option build ARCH=riscv32 COMP=gcc CXX="$cxx" \
    EXTRACXXFLAGS="-DPIKAFISH_EMBEDDED_GUI -DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL $model_flags" \
    EXTRALDFLAGS="$objects -Wl,--strip-debug"
cp "$work/src/pikafish" "$out/xiangqi-pikafish-gui"
echo 'PICTURE_GUI_CANDIDATE_BUILD_PASS backend=stub board_validated=false'
