"""Decode the production C encoder result independently with Python stdlib."""
import pathlib
import struct
import sys
import zlib

data = pathlib.Path(sys.argv[1]).read_bytes()
assert len(data) == 2769183
assert data[:8] == b"\x89PNG\r\n\x1a\n"
at = 8
compressed = b""
types = []
while at < len(data):
    n = struct.unpack_from(">I", data, at)[0]
    kind, payload = data[at+4:at+8], data[at+8:at+8+n]
    assert zlib.crc32(kind+payload) == struct.unpack_from(">I", data, at+8+n)[0]
    if kind == b"IHDR":
        assert struct.unpack(">IIBBBBB", payload) == (1280, 720, 8, 2, 0, 0, 0)
    elif kind == b"IDAT":
        compressed += payload
    types.append(kind)
    at += n+12
assert at == len(data) and types == [b"IHDR", b"IDAT", b"IEND"]
pixels = zlib.decompress(compressed)
assert len(pixels) == 720*3841
for y in range(720):
    assert pixels[y*3841] == 0
    for x in range(1280):
        v = ((y*97) ^ (x*31)) & 65535
        if y == 0 and x < 3:
            v = [0xf800, 0x07e0, 0x001f][x]
        red, green, blue = v >> 11, (v >> 5) & 63, v & 31
        expected = bytes(((red << 3) | (red >> 2),
                          (green << 2) | (green >> 4),
                          (blue << 3) | (blue >> 2)))
        pos = y*3841 + 1 + x*3
        assert pixels[pos:pos+3] == expected, (x, y)
print("CAMERA_SD_PNG_ALL_PIXELS_COLOR_ENDIAN_ROW_CRC_PASS")
