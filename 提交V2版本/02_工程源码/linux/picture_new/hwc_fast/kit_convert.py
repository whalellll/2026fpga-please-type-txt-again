"""Lossless PNG decoding and argument adapter for the frozen C input converter."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--format', choices=['png', 'rgb565', 'rgb8', 'nchw-f32'], required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--model', type=Path, default=HERE / 'models/detector.xqi')
    ap.add_argument('--width', type=int)
    ap.add_argument('--height', type=int)
    ap.add_argument('--roi', nargs=4, type=int, metavar=('X0', 'Y0', 'X1', 'Y1'),
                    help='Same-frame half-open detector crop; never reuse previous frame geometry')
    a = ap.parse_args()
    if a.output.exists():
        ap.error('Output exists; choose a new path')
    mode, source = a.format, a.input.resolve()
    width, height = a.width, a.height
    with tempfile.TemporaryDirectory(prefix='hwc-input-') as directory:
        if mode == 'png':
            try:
                from PIL import Image
            except ImportError:
                ap.error('PNG decoding requires Pillow; nchw-f32/rgb565/rgb8 need only Python 3')
            with Image.open(source) as picture:
                if picture.format != 'PNG' or picture.mode != 'RGB':
                    ap.error('Use an RGB8 PNG without alpha/palette/grayscale; no implicit color conversion')
                width, height = picture.size
                if not (0 < width <= 1280 and 0 < height <= 720):
                    ap.error('PNG must fit 1280x720; supply original preprocessed nchw-f32 for other sizes')
                source = Path(directory) / 'rgb8.bin'
                source.write_bytes(picture.tobytes())
                mode = 'rgb8'
        elif mode == 'rgb565':
            width, height = 1280, 720
        elif mode == 'nchw-f32':
            width, height = 640, 640
            if a.roi:
                ap.error('nchw-f32 already contains the detector crop/letterbox; do not crop twice')
        if width is None or height is None:
            ap.error('rgb8 needs --width and --height')
        if a.format != 'nchw-f32' and not a.roi:
            ap.error('Image input requires an explicit same-frame --roi; use 0 0 W H only for a full-image detector')
        roi = a.roi or [0, 0, 640, 640]
        command = [str(HERE / 'hwc-convert'), str(a.model.resolve()), mode, str(source),
                   str(width), str(height), *map(str, roi), str(a.output.resolve())]
        subprocess.run(command, check=True)
    print('HWC8_SHA256=' + hashlib.sha256(a.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
