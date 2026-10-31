#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build/nnue10ms/tests
python3 sim/test_ddr_reference_placement.py
for test in stagea resident; do
    cc -std=c11 -Wall -Wextra -Werror -Ilinux/mac_accel \
        "sim/test_pango_mac_${test}_uapi.c" -o "build/nnue10ms/tests/uapi-$test"
    "build/nnue10ms/tests/uapi-$test"
done
cc -std=c11 -O2 -Wall -Wextra -Werror sim/test_pango_mac_copy_chunks.c -o build/nnue10ms/tests/copy-chunks
build/nnue10ms/tests/copy-chunks
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic -pthread \
    -Ilinux/pikafish sim/test_stagea_gather_descriptors.cpp \
    linux/pikafish/pikafish_stagea_accel.cpp -o build/nnue10ms/tests/descriptors
build/nnue10ms/tests/descriptors
bash scripts/test_pff1_stagea_stream.sh
iverilog -g2012 -s tb_pff1_stagea_gather -o build/nnue10ms/tests/gather-original.vvp \
    rtl/mac_accel/pff1_stagea_gather.v sim/tb_pff1_stagea_gather.sv
vvp build/nnue10ms/tests/gather-original.vvp
for test in tb_i2s_audio tb_audio_fifo_order; do
    source="sim/$test.v"
    if [ "$test" = tb_audio_fifo_order ]; then source="sim/$test.sv"; fi
    iverilog -g2012 -s "$test" -o "build/nnue10ms/tests/$test.vvp" \
        rtl/audio/i2s_audio_duplex.v "$source"
    vvp "build/nnue10ms/tests/$test.vvp"
done
iverilog -g2012 -s tb_audio_mmio -o build/nnue10ms/tests/audio-mmio.vvp \
    rtl/audio/audio_mmio.v sim/tb_audio_mmio.v
vvp build/nnue10ms/tests/audio-mmio.vvp
iverilog -g2012 -s tb_mac_conv_window_limits -o build/nnue10ms/tests/window-limits.vvp \
    rtl/mac_accel/mac_conv_window.v sim/tb_mac_conv_window_limits.sv
vvp build/nnue10ms/tests/window-limits.vvp
echo NNUE10MS_FOCUSED_TEST_PASS
