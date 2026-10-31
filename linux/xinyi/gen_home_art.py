"""Offline Xiangqi board and brush-style title; target only decodes bitmaps.

Uses the installed KaiTi for rasterization. The font program is not copied or
included in the product; generated pixels build without a font dependency.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deps',type=Path)
    ap.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/simkai.ttf'))
    ap.add_argument('--preview',type=Path)
    ap.add_argument('--check',action='store_true')
    a=ap.parse_args()
    if a.deps:sys.path.insert(0,str(a.deps.resolve()))
    from PIL import Image,ImageDraw,ImageFont,features
    import PIL
    font_data=a.font.read_bytes();font_sha=hashlib.sha256(font_data).hexdigest()
    image=Image.new('RGB',(960,540),(247,244,236));draw=ImageDraw.Draw(image)
    # Nine files / ten ranks; inner files stop across the river. Palaces and
    # river labels stay visible in the gaps beside the central menu.
    paper=(237,219,185);ink=(143,109,69);edge=(176,139,91)
    draw.rounded_rectangle((299,105,661,509),radius=5,fill=paper,outline=edge,width=2)
    x0,y0,cell=312,118,42
    for rank in range(10):draw.line((x0,y0+rank*cell,x0+8*cell,y0+rank*cell),fill=ink,width=1)
    for file in range(9):
        x=x0+file*cell
        if file in (0,8):draw.line((x,y0,x,y0+9*cell),fill=ink,width=1)
        else:
            draw.line((x,y0,x,y0+4*cell),fill=ink,width=1)
            draw.line((x,y0+5*cell,x,y0+9*cell),fill=ink,width=1)
    for rank in (0,7):
        draw.line((x0+3*cell,y0+rank*cell,x0+5*cell,y0+(rank+2)*cell),fill=ink,width=1)
        draw.line((x0+5*cell,y0+rank*cell,x0+3*cell,y0+(rank+2)*cell),fill=ink,width=1)
    river=ImageFont.truetype(str(a.font),18)
    draw.text((336,307),'楚河',font=river,fill=(123,88,53))
    draw.text((588,307),'汉界',font=river,fill=(123,88,53))
    piece_font=ImageFont.truetype(str(a.font),27)
    for x,y,c,color in [(354,202,'車',(155,53,43)),(606,202,'馬',(54,65,56)),
                        (354,454,'馬',(54,65,56)),(606,454,'車',(155,53,43))]:
        draw.ellipse((x-18,y-18,x+18,y+18),fill=(251,238,209),outline=color,width=2)
        draw.ellipse((x-14,y-14,x+14,y+14),outline=color,width=1)
        box=draw.textbbox((0,0),c,font=piece_font)
        draw.text((x-(box[2]-box[0])/2-box[0],y-(box[3]-box[1])/2-box[1]),c,font=piece_font,fill=color)
    # Rotate the illustration as one board, preserving its nine-by-ten grid.
    board=image.crop((298,104,662,510)).transpose(Image.Transpose.ROTATE_270)
    base=Image.new('RGB',image.size,(247,244,236));rotated=base.copy()
    rotated.paste(board,((960-board.width)//2,306-board.height//2))
    image=Image.blend(base,rotated,.32)
    pixels=[((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in image.getdata()]
    runs=[];offsets=[0]
    for y in range(540):
        row=pixels[y*960:(y+1)*960];x=0
        while x<960:
            end=x+1
            while end<960 and row[end]==row[x]:end+=1
            runs.append(((end-x)<<16)|row[x]);x=end
        offsets.append(len(runs))
    assert len(runs)<65536
    # Rasterize the complete title so Chinese/Latin spacing and centering use
    # the same brush font; no changes to the existing UI glyph bitmaps.
    text='中国象棋RISC-V对弈平台';font=ImageFont.truetype(str(a.font),80*3)
    box=font.getbbox(text);w=((box[2]-box[0]+5)//6)*2+16;h=(box[3]-box[1]+2)//3+16
    alpha=Image.new('L',(w*3,h*3));ImageDraw.Draw(alpha).text((24-box[0],24-box[1]),text,font=font,fill=255)
    alpha=alpha.resize((w,h),Image.Resampling.LANCZOS)
    values=[(v*15+127)//255 for v in alpha.getdata()]
    packed=bytes((values[i]<<4)|values[i+1] for i in range(0,len(values),2))
    assert w<1500 and h<130
    lines=['/* Offline board illustration and rendered KaiTi title. No font program included. */',
        '#ifndef XINYI_HOME_ART_H','#define XINYI_HOME_ART_H','#include <stdint.h>',
        '#define XY15_ART_HEIGHT 540u','#define XY15_ART_WIDTH 960u',
        f'#define XY15_TITLE_WIDTH {w}u',f'#define XY15_TITLE_HEIGHT {h}u',
        'static const uint16_t xy15_art_offsets[541]={',','.join(map(str,offsets)),'};',
        f'static const uint32_t xy15_art_runs[{len(runs)}]={{']
    lines += [','.join('0x%08xu'%n for n in runs[i:i+8])+',' for i in range(0,len(runs),8)]
    lines += ['};',f'static const uint8_t xy15_title_alpha[{len(packed)}]={{']
    lines += [','.join('0x%02x'%n for n in packed[i:i+24])+',' for i in range(0,len(packed),24)]
    lines += ['};','#endif',''];header='\n'.join(lines).encode()
    meta=dict(schema=1,board_files=9,board_ranks=10,river_and_palaces=True,source_size=[960,540],
        board_rotation_clockwise_degrees=90,board_opacity=.32,
        output_size=[1920,1080],offline_generated=True,runtime_blur=False,
        title=text,title_font_family='KaiTi',source_font_name=a.font.name,source_font_sha256=font_sha,
        font_program_redistributed=False,title_dimensions=[w,h],title_alpha_bits=4,
        rom_bytes=len(runs)*4+len(offsets)*2+len(packed),pillow=PIL.__version__,
        freetype=features.version('freetype2'),header_sha256=hashlib.sha256(header).hexdigest())
    root=Path(__file__).resolve().parent;out=root/'xinyi_home_art.h';receipt=root/'fonts/home-art-r15.json'
    encoded=(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    if a.check:assert out.read_bytes()==header and receipt.read_bytes()==encoded
    else:out.write_bytes(header);receipt.write_bytes(encoded)
    if a.preview:
        a.preview.mkdir(parents=True,exist_ok=False)
        image.resize((1920,1080),Image.Resampling.NEAREST).save(a.preview/'background.png')
        title=Image.new('RGBA',(w,h),(38,56,49,0));title.putalpha(alpha);title.save(a.preview/'title.png')
    print('HOME_ART_R15_EXACT_CHECK_PASS' if a.check else 'HOME_ART_R15_GENERATED',meta['rom_bytes'])


if __name__=='__main__':main()
