"""Independently decode the synthetic RAM fixture; no camera capture data."""
import struct
import sys
import zlib
from pathlib import Path


def check(path):
    data = path.read_bytes()
    assert len(data) == 2769183
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, chunks = 8, []
    while offset < len(data):
        length, = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc, = struct.unpack_from(">I", data, offset + 8 + length)
        assert zlib.crc32(kind + payload) & 0xffffffff == crc
        if kind == b"IHDR":
            assert struct.unpack(">IIBBBBB", payload) == (1280, 720, 8, 2, 0, 0, 0)
        if kind == b"IDAT": chunks.append(payload)
        offset += length + 12
    pixels = zlib.decompress(b"".join(chunks))
    assert len(pixels) == 720 * 3841
    for y in range(720):
        assert pixels[y * 3841] == 0
        for x in range(1280):
            r, g, b = x * 31 // 1279, y * 63 // 719, (x + y) * 31 // 1998
            expected = bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
            position = y * 3841 + 1 + x * 3
            assert pixels[position:position + 3] == expected, (x, y)
    print("XQ_PICTURE_PNG_TEST_PASS synthetic=921600-pixels RGB565LE top-to-bottom")


if __name__ == "__main__":
    path = Path(sys.argv[1])
    try:
        check(path)
    finally:
        path.unlink()
