"""Reproducible decorative board, blurred offline and row-run encoded RGB565."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deps', type=Path)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.deps:
        sys.path.insert(0, str(a.deps.resolve()))
    from PIL import Image, ImageDraw, ImageFilter
    import PIL
    size = (240, 135)
    base = Image.new('RGB', size, (245, 241, 234))
    ink = Image.new('RGB', size, (245, 241, 234))
    draw = ImageDraw.Draw(ink)
    # An illustration, independent of photographs, game positions or models.
    draw.rounded_rectangle((12, 20, 228, 132), 5, fill=(224, 208, 179), outline=(155, 115, 78), width=2)
    for x in range(24, 217, 24):
        draw.line((x, 29, x, 71), fill=(122, 91, 70))
        draw.line((x, 83, x, 125), fill=(122, 91, 70))
    for y in range(29, 126, 12):
        draw.line((24, y, 216, y), fill=(122, 91, 70))
    for x in [24, 216]:
        draw.line((x, 29, x, 125), fill=(122, 91, 70))
    for x, y, red in [(24, 41, True), (216, 41, False), (24, 113, False), (216, 113, True)]:
        color = (146, 61, 48) if red else (64, 74, 68)
        draw.ellipse((x-11, y-11, x+11, y+11), fill=(241, 222, 190), outline=color, width=2)
        draw.line((x-4, y, x+4, y), fill=color, width=2)
        draw.line((x, y-5, x, y+5), fill=color, width=2)
    image = Image.blend(base, ink.filter(ImageFilter.GaussianBlur(1.8)), .30)
    pixels = [((r*31+127)//255 << 11) | ((g*63+127)//255 << 5) | ((b*31+127)//255)
              for r, g, b in image.getdata()]
    runs, offsets = [], [0]
    for y in range(size[1]):
        row = pixels[y*size[0]:(y+1)*size[0]]
        x = 0
        while x < len(row):
            end = x+1
            while end < len(row) and row[end] == row[x]:
                end += 1
            runs.append((end-x) << 16 | row[x]); x = end
        offsets.append(len(runs))
    assert len(runs) < 65536
    text = ['/* Generated procedural illustration; no camera/model inputs. */',
            '#ifndef XINYI_HOME_BACKGROUND_H', '#define XINYI_HOME_BACKGROUND_H', '#include <stdint.h>',
            'static const uint16_t xy_home_row_offsets[136] = {',
            ','.join(str(n) for n in offsets), '};',
            f'static const uint32_t xy_home_runs[{len(runs)}] = {{']
    text += [','.join('0x%08xu' % n for n in runs[i:i+8])+',' for i in range(0, len(runs), 8)]
    text += ['};', '#endif', '']
    data = '\n'.join(text).encode()
    root = Path(__file__).resolve().parent
    receipt = (json.dumps(dict(schema=1, pillow=PIL.__version__, procedural=True,
        source_size=list(size), output_size=[1920,1080], runtime_blur=False,
        runs=len(runs), rom_bytes=4*len(runs)+2*len(offsets),
        header_sha256=hashlib.sha256(data).hexdigest()), indent=2)+'\n').encode()
    header, meta = root/'xinyi_home_background.h', root/'fonts/home-background.json'
    if a.check:
        assert header.read_bytes() == data and meta.read_bytes() == receipt
        print('HOME_BACKGROUND_EXACT_REBUILD_PASS')
    else:
        header.write_bytes(data); meta.write_bytes(receipt)
        print('HOME_BACKGROUND_GENERATED', len(runs), 'runs')


if __name__ == '__main__':
    main()
