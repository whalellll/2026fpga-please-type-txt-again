"""Build native-size UI coverage masks from a small, redistributable font subset."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import PIL
from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'linux/pikafish/fonts'
FONT = DIRECTORY/'XiangqiUiSans.ttf'
HEADER = ROOT/'linux/pikafish/xiangqi_ui_font_aa.h'
MANIFEST = DIRECTORY/'ui-font.json'
EXTRA = '一二三四五六七八九进退平来出'
ASCII = ''.join(map(chr, range(32, 127)))
SS = 4

def sha(data):
    return hashlib.sha256(data).hexdigest()

def characters():
    enum = (ROOT/'sw/xiangqi/xiangqi_font_zh.h').read_text(encoding='utf-8').split('typedef enum {')[1].split('}')[0]
    entries = re.findall(r'(XQ_HZ_\w+)[^\n]*', enum)
    chars = re.findall(r'XQ_HZ_\w+[^\n]*?/\*\s*(\S)\s*\*/', enum)
    # LV was added without a comment to the shared legacy enum.
    assert entries[-2:] == ['XQ_HZ_LV', 'XQ_HZ_COUNT']
    chars.append('率')
    assert len(chars) == len(entries)-1
    return ''.join(chars)

def subset_font(source, chars):
    from fontTools import subset, __version__
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    font = TTFont(source, recalcTimestamp=False)
    copyright_text = font['name'].getDebugName(0)
    family = font['name'].getDebugName(1)
    assert all(ord(c) in font.getBestCmap() for c in chars)
    instantiateVariableFont(font, {'wght': 500}, inplace=True)
    options = subset.Options()
    options.name_IDs = ['*']
    options.name_languages = ['*']
    options.recalc_timestamp = False
    small = subset.Subsetter(options=options)
    small.populate(text=chars)
    small.subset(font)
    names = {1:'Xiangqi UI Sans', 2:'Medium', 3:'XQ;XiangqiUiSans-Medium',
             4:'Xiangqi UI Sans Medium', 6:'XiangqiUiSans-Medium',
             16:'Xiangqi UI Sans', 17:'Medium'}
    for record in font['name'].names:
        if record.nameID in names:
            record.string = names[record.nameID].encode(record.getEncoding())
    font.save(FONT, reorderTables=True)
    metadata = dict(source_filename=source.name, source_family=family,
                    source_sha256=sha(source.read_bytes()), copyright=copyright_text,
                    weight=500, subset_family='Xiangqi UI Sans', fonttools_version=__version__,
                    subset_sha256=sha(FONT.read_bytes()), license='SIL Open Font License 1.1',
                    license_url='https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE')
    (DIRECTORY/'ui-source.json').write_bytes((json.dumps(metadata, ensure_ascii=False, indent=2)+'\n').encode())
    old_license = (DIRECTORY/'OFL.txt').read_text(encoding='utf-8')
    license_start = old_license.index('This Font Software')
    (DIRECTORY/'UI-OFL.txt').write_bytes((copyright_text+'\n\n'+old_license[license_start:]).encode())

def generate(chars):
    data = bytearray()
    tables = {}
    stats = []
    def append(character, canvas, advance):
        # Even row widths keep the target nibble lookup simple.
        if canvas.width & 1:
            padded = Image.new('L', (canvas.width+1, canvas.height))
            padded.paste(canvas, (0, 0))
            canvas = padded
        alpha = [(v*15+127)//255 for v in canvas.getdata()]
        offset = len(data)
        data.extend((alpha[i]<<4)|alpha[i+1] for i in range(0, len(alpha), 2))
        stats.append(dict(character=character, width=canvas.width, height=canvas.height,
                          intermediate_pixels=sum(0<a<15 for a in alpha)))
        return (offset, canvas.width, canvas.height, advance)
    for scale, size in [(1,16), (2,22), (3,30), (5,48)]:
        font = ImageFont.truetype(str(FONT), size*SS)
        boxes = [font.getbbox(c) for c in ASCII]
        top = min(b[1] for b in boxes)
        bottom = max(b[3] for b in boxes)
        left_pad = max(0, -min(b[0] for b in boxes))
        height = math.ceil((bottom-top)/SS)
        entries = []
        for c, box in zip(ASCII, boxes):
            advance = math.ceil(font.getlength(c)/SS)+1
            width = max(advance, math.ceil((box[2]+left_pad)/SS)+1)
            image = Image.new('L', (width*SS, height*SS))
            ImageDraw.Draw(image).text((left_pad,-top), c, font=font, fill=255)
            image = image.resize((width,height), Image.Resampling.LANCZOS)
            entries.append(append(c,image,advance))
        tables['xq_ui_ascii'+str(scale)] = entries
    for name, text, side, size in [('xq_ui_zh32',chars,32,30),
                                   ('xq_ui_zh48',chars,48,44),
                                   ('xq_ui_voice32',EXTRA,32,30)]:
        font = ImageFont.truetype(str(FONT), size*SS)
        entries = []
        for c in text:
            if side == 48 and c not in '楚河汉界中国象棋':
                entries.append((0,0,0,0))
                continue
            box = font.getbbox(c)
            image = Image.new('L',(side*SS,side*SS))
            ImageDraw.Draw(image).text(((side*SS-(box[2]-box[0]))//2-box[0],
                                        (side*SS-(box[3]-box[1]))//2-box[1]),c,font=font,fill=255)
            entries.append(append(c,image.resize((side,side),Image.Resampling.LANCZOS),side+side//16))
        tables[name] = entries
    lines = ['/* Generated by scripts/gen_xiangqi_ui_font.py. Noto Sans SC, SIL OFL 1.1. */',
             '#ifndef XIANGQI_UI_FONT_AA_H','#define XIANGQI_UI_FONT_AA_H','#include <stdint.h>',
             'typedef struct { uint32_t offset; uint8_t width, height, advance; } xq_ui_glyph_t;',
             '#define XQ_UI_HANZI_COUNT '+str(len(chars)),
             'static const uint8_t xq_ui_alpha4[] = {']
    for i in range(0,len(data),24):
        lines.append('    '+','.join('0x%02x'%v for v in data[i:i+24])+',')
    lines.append('};')
    for name, entries in tables.items():
        lines.append('static const xq_ui_glyph_t '+name+'['+str(len(entries))+'] = {')
        lines.extend('    {%du,%d,%d,%d},'%e for e in entries)
        lines.append('};')
    lines += ['#endif','']
    header = '\n'.join(lines).encode()
    manifest = dict(schema=1, hanzi=chars, voice=EXTRA, ascii=ASCII, weight=500,
                    ascii_sizes=[16,22,30,48], hanzi_sizes=[32,48], coverage_bits=4,
                    supersample=SS, alpha_bytes=len(data), subset_sha256=sha(FONT.read_bytes()),
                    header_sha256=sha(header), pillow_version=PIL.__version__,
                    freetype_version=features.version('freetype2'), glyphs=stats)
    return header,(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-font', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    chars = characters()
    if args.source_font:
        assert not args.check
        subset_font(args.source_font, chars+EXTRA+ASCII)
    header, manifest = generate(chars)
    if args.check:
        assert HEADER.read_bytes() == header, 'UI header differs'
        assert MANIFEST.read_bytes() == manifest, 'UI manifest differs'
        print('UI_FONT_REGENERATION_PASS native-size alpha=4bit')
    else:
        HEADER.write_bytes(header)
        MANIFEST.write_bytes(manifest)
        print('UI_FONT_GENERATED alpha_bytes='+str(json.loads(manifest)['alpha_bytes']))

if __name__ == '__main__':
    main()
