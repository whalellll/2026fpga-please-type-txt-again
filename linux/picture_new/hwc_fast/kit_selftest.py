"""Finite, synthetic-only self-check of the shipped host and converter."""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    expected = json.loads((HERE / 'expected.json').read_text())
    checks = []
    for rel, digest in expected['files'].items():
        assert sha(HERE / rel) == digest, rel
    exponent = expected['input_exponent']
    with tempfile.TemporaryDirectory(prefix='hwc-kit-selftest-') as directory:
        work = Path(directory)

        def run(args, code=0):
            result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=300)
            assert result.returncode == code, result.stdout + result.stderr
            return result.stdout + result.stderr

        for case, values in expected['cases'].items():
            converted = work / (case + '.hwc8')
            run([HERE / 'hwc-convert', HERE / 'models/detector.xqi', 'nchw-f32',
                 HERE / ('synthetic/' + case + '.f32'), 640, 640, 0, 0, 640, 640, converted])
            assert sha(converted) == values['input_sha256'], case + ' conversion'
            output = work / (case + '.heads.f32')
            log = run([HERE / 'integer-host', HERE / 'models/detector.xqi', converted, 1, output])
            assert 'jobs=166' in log and 'output_crc=' + values['output_crc32'] in log
            assert sha(output) == values['output_sha256'], case + ' full heads'
            checks.append(case + ': conversion, 166 jobs, three full heads CRC/SHA')

        # Independent constant-image reference includes the real 565 bit
        # replication and 640x360 +114-pad geometry. No photos are read.
        packed = (19 << 11) | (37 << 5) | 7
        rgb = [(19 << 3) | (19 >> 2), (37 << 2) | (37 >> 4), (7 << 3) | (7 >> 2)]
        source = work / 'constant.rgb565'
        source.write_bytes(struct.pack('<H', packed) * (1280 * 720))
        converted = work / 'constant.hwc8'
        log = run([sys.executable, HERE / 'convert.py', '--format', 'rgb565', '--input', source,
                   '--roi', 0, 0, 1280, 720, '--output', converted])
        assert 'width=640 height=360 left=0 top=140' in log

        def quant(value):
            unit = struct.unpack('<f', struct.pack('<f', value / 255))[0]
            return max(-128, min(127, round(math.ldexp(unit, -exponent)))) & 255

        body = b''.join(bytes([*(quant(c) for c in (rgb if 140 <= y < 500 else [114]*3)), 0]) * 640
                        for y in range(640))
        want = struct.pack('<8s6IiI', b'XQHWC81\0', 1, 640, 640, 3, 4, len(body), exponent, zlib.crc32(body)) + body
        assert converted.read_bytes() == want
        checks.append('RGB565 bit replication, letterbox, padding and quantization: independent bytes')
        raw = work / 'constant.rgb8'
        raw.write_bytes(bytes(rgb) * (1280 * 720))
        same = work / 'rgb8.hwc8'
        run([sys.executable, HERE / 'convert.py', '--format', 'rgb8', '--input', raw,
             '--width', 1280, '--height', 720, '--roi', 0, 0, 1280, 720, '--output', same])
        assert same.read_bytes() == want
        try:
            from PIL import Image
        except ImportError:
            checks.append('PNG decode: optional Pillow unavailable; RGB8 path checked')
        else:
            png = work / 'constant.png'
            Image.new('RGB', (1280, 720), tuple(rgb)).save(png)
            output = work / 'png.hwc8'
            run([sys.executable, HERE / 'convert.py', '--format', 'png', '--input', png,
                 '--roi', 0, 0, 1280, 720, '--output', output])
            assert output.read_bytes() == want
            checks.append('PNG RGB8 decode: identical to RGB565/RGB8 bytes')
        invalid = work / 'nonfinite.f32'
        data = bytearray((HERE / 'synthetic/zero.f32').read_bytes())
        struct.pack_into('<f', data, 0, float('nan'));invalid.write_bytes(data)
        run([HERE / 'hwc-convert', HERE / 'models/detector.xqi', 'nchw-f32', invalid,
             640, 640, 0, 0, 640, 640, work / 'bad.hwc8'], 2)
        assert not (work / 'bad.hwc8').exists()
        invalid.write_bytes(b'\0')
        run([HERE / 'hwc-convert', HERE / 'models/detector.xqi', 'rgb565', invalid,
             1280, 720, 0, 0, 1280, 720, work / 'short.hwc8'], 2)
        run([HERE / 'hwc-convert', HERE / 'models/detector.xqi', 'rgb565', source,
             1280, 720, 0, 0, 1281, 720, work / 'outside.hwc8'], 2)
        checks.append('NaN, truncated input and out-of-frame ROI rejected before output')
    print(json.dumps({'status': 'HWC_ACCEPTANCE_KIT_SYNTHETIC_SELFTEST_PASS', 'checks': checks,
                      'hardware_used': False, 'camera_v2_or_game2_accessed': False}, indent=2))


if __name__ == '__main__':
    main()
