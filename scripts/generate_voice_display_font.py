"""Generate the Linux-only preview glyph subset from an OFL Source Han font."""
import argparse
import hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument('--font', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
characters = '一二三四五六七八九进退平来出'
font = ImageFont.truetype(str(args.font), 16)
lines = ['#ifndef XQVOICE_DISPLAY_FONT_H', '#define XQVOICE_DISPLAY_FONT_H',
         '/* Linux-only glyph subset from Source Han Sans, SIL OFL 1.1.',
         ' * Source SHA-256: ' + hashlib.sha256(args.font.read_bytes()).hexdigest(),
         ' * Regenerate with scripts/generate_voice_display_font.py. */',
         'static const uint16_t xqvoice_font16[14][16] = {']
for char in characters:
    image = Image.new('L', (16, 16))
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), char, font=font)
    draw.text(((16 - (box[2] - box[0])) // 2 - box[0], -box[1]),
              char, font=font, fill=255)
    rows = [sum((1 << (15 - x)) for x in range(16)
                if image.getpixel((x, y)) >= 96) for y in range(16)]
    lines.append('    {' + ','.join(f'0x{x:04x}u' for x in rows) + '}, /* ' + char + ' */')
lines.extend(['};', '#endif', ''])
args.output.write_bytes('\n'.join(lines).encode('utf8'))
print('VOICE_DISPLAY_FONT_GENERATED glyphs=14')
