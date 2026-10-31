"""Off-board two-bank rendering, word-access diagnosis and platform flip checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path


def function(text,signature):
    start=text.index(signature);body=text.index('{',start);depth=1;i=body+1
    while depth:
        if text[i]=='{':depth+=1
        elif text[i]=='}':depth-=1
        i+=1
    return start,i,text[start:i]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--render-proof',type=Path,help='Reuse unchanged completed rendering checks after a platform-only repair')
    a=ap.parse_args();out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    include=['linux/xinyi_board','linux/xinyi','linux/pikafish','linux/pikafish/include',
        'linux/vision','linux/voice','linux/voice_ctc','linux/voice_speech','linux/mac_accel',
        'linux/picture_new','sw/xiangqi','sw/video','sw/bootloader']
    renderer=['linux/xinyi/xinyi_fb.c','linux/xinyi/test_fb.c','linux/pikafish/xiangqi_fb_gui_1080.c',
        'linux/xinyi/xinyi_product.c','linux/voice/xqvoice_protocol.c','sw/xiangqi/xiangqi_search.c',
        'sw/xiangqi/xiangqi_pikafish_link.c','artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c']
    platform=['linux/xinyi_board/platform.c','linux/xinyi_board/platform_test.c','linux/vision/xq_camera.c',
        'linux/vision/xq_camera_capture_retry.c','linux/vision/xq_picture.c','linux/vision/xq_vision.c','sw/bootloader/crc32_fast.c',
        'sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_pikafish_link.c']
    names=set(renderer+platform+['scripts/check_xinyi_gui_buffering.py'])
    for folder in include:names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={n:sha(ROOT/n) for n in sorted(names)}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,source_sha256=before,checks=[],rendering={})
    def run(name,argv,seconds=120):
        with (out/(name+'.log')).open('xb') as log:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        result['checks'].append(dict(name=name,exit=r.returncode))
        assert r.returncode==0,(name,text[-2500:]);return text
    try:
        prefix='''#include <stdint.h>
#include <time.h>
static uint64_t gui_reads,gui_writes,gui_font_reads,gui_font_writes,gui_cpu,gui_start;
static unsigned gui_font_depth;
static uint64_t gui_now(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;}
static uint32_t gui_read(volatile uint32_t *p,unsigned i){gui_reads++;if(gui_font_depth)gui_font_reads++;return p[i];}
static void gui_write(volatile uint32_t *p,unsigned i,uint32_t v){gui_writes++;if(gui_font_depth)gui_font_writes++;p[i]=v;}
'''
        def counted(text):
            text=re.sub(r'words\[([^\]]+)\]\s*=\s*([^;]+);',lambda m:'gui_write(words,'+m[1]+','+m[2]+');',text)
            return re.sub(r'words\[([^\]]+)\]',lambda m:'gui_read(words,'+m[1]+')',text)
        legacy=(ROOT/renderer[2]).read_text(encoding='utf-8-sig')
        start,end,raw=function(legacy,'static void draw_ui_glyph(')
        legacy=legacy[:start]+raw.replace('draw_ui_glyph(','draw_ui_glyph_raw(',1)+'''
static void draw_ui_glyph(volatile uint16_t *fb,int x,int y,const xq_ui_glyph_t *g,uint16_t c)
{gui_font_depth++;draw_ui_glyph_raw(fb,x,y,g,c);gui_font_depth--;}
'''+legacy[end:]
        (out/'xiangqi_fb_gui_1080.c').write_text(prefix+counted(legacy),newline='\n')
        product=(ROOT/renderer[0]).read_text(encoding='utf-8-sig')
        start,end,raw=function(product,'static int product_glyph(')
        product=product[:start]+raw.replace('product_glyph(','product_glyph_raw(',1)+'''
static int product_glyph(volatile uint16_t *fb,int x,int y,unsigned code,unsigned size,uint16_t color)
{gui_font_depth++;int v=product_glyph_raw(fb,x,y,code,size,color);gui_font_depth--;return v;}
'''+product[end:]
        marker='if(!a || !fb) return;';assert product.count(marker)==1
        product=product.replace(marker,marker+'\n gui_reads=gui_writes=gui_font_reads=gui_font_writes=0;gui_start=gui_now();')
        start,end,raw=function(product,'void xy_fb_render(')
        product=product[:start]+raw[:-1]+'gui_cpu=gui_now()-gui_start;\n}'+product[end:]
        (out/'xinyi_fb.c').write_text(counted(product),encoding='utf-8',newline='\n')
        fixture=(ROOT/renderer[1]).read_text(encoding='utf-8')
        start,end,_=function(fixture,'static void save_ppm(')
        fixture=fixture[:start]+'''static void save_ppm(const char *d,const char *n,const uint16_t *p){(void)d;(void)n;(void)p;}
'''+fixture[end:]
        fixture=fixture.replace('#include <assert.h>','#include <assert.h>\n#include "xq_sha256.h"',1)
        marker='    xy_fb_invalidate(); xy_fb_render(a,reference);';assert fixture.count(marker)==1
        fixture=fixture.replace(marker,'''    static unsigned frame_no;char digest[65];xq_sha256_hex(actual,VIDEO_FB_FRAME_BYTES,digest);
    printf("GUI_BANK_FRAME frame=%u page=%u mode=%u sha=%s reads=%llu writes=%llu font_reads=%llu font_writes=%llu cpu_ns=%llu\\n",frame_no++,(unsigned)a->page,(unsigned)a->mode,digest,(unsigned long long)gui_reads,(unsigned long long)gui_writes,(unsigned long long)gui_font_reads,(unsigned long long)gui_font_writes,(unsigned long long)gui_cpu);
'''+marker)
        marker='int main(int argc,char **argv)';assert fixture.count(marker)==1
        fixture=fixture.replace(marker,'''static void next_bank(xy_app *a,uint16_t **pixels,uint32_t *first,uint32_t *second,unsigned *turn)
{
    unsigned page=(*turn)++&1u;uint16_t *back=(void *)((page?second:first)+16),*front=(void *)((page?first:second)+16);
    char before[65],after[65];xq_sha256_hex(front,VIDEO_FB_FRAME_BYTES,before);
    xy_fb_render(a,back);xq_sha256_hex(front,VIDEO_FB_FRAME_BYTES,after);assert(!strcmp(before,after));*pixels=back;
}
'''+marker)
        marker='uint16_t *pixels,*reference=';assert fixture.count(marker)==1
        fixture=fixture.replace(marker,'uint32_t *guarded2=malloc(VIDEO_FB_FRAME_BYTES+128);unsigned bank_turn=0;\n    '+marker)
        marker='pixels=(uint16_t *)(guarded+16);';assert fixture.count(marker)==1
        fixture=fixture.replace(marker,'assert(guarded2);for(i=0;i<(VIDEO_FB_FRAME_BYTES+128)/4;i++)guarded2[i]=0xcafebabe;\n    '+marker)
        fixture=fixture.replace('xy_fb_render(&a,pixels);','next_bank(&a,&pixels,guarded,guarded2,&bank_turn);')
        marker='save_ppm(argv[1],"home",pixels);';assert fixture.count(marker)==1
        fixture=fixture.replace(marker,marker+'''
    for(unsigned warm=0;warm<4;warm++){
        next_bank(&a,&pixels,guarded,guarded2,&bank_turn);
        if(XINYI_GUI_DOUBLE_BUFFER && warm>0)assert(!gui_writes);
        compare_full(&a,pixels,reference);
    }
''')
        fixture=fixture.replace('free(guarded);free(reference);free(baseline);',
            'for(i=0;i<16;i++)assert(guarded2[i]==0xcafebabe && guarded2[16+VIDEO_FB_FRAME_BYTES/4+i]==0xcafebabe);\n    free(guarded2);free(guarded);free(reference);free(baseline);')
        full=out/'frames.c';full.write_text(fixture,encoding='utf-8',newline='\n')
        short=out/'frames-short.c';short.write_text(fixture.replace('i<12;','i<2;').replace('i<48;','i<4;').replace('i<90;i++','i<4;i++'),encoding='utf-8',newline='\n')
        inc=['-I'+wsl_path(out),*['-I'+wsl_path(ROOT/p) for p in include],'-I'+wsl_path(ROOT/'artifacts/vision-model-20261020-adapter/runtime')]
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-D_POSIX_C_SOURCE=200809L',
            '-ffunction-sections','-fdata-sections','-DVIDEO_FB_LINUX_MMAP','-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h')]
        render_jobs=[('baseline',0,'host',full),('candidate',1,'host',full),
            ('sanitizer',1,'sanitizer',full),('short-host',1,'host',short),('short-rv32',1,'rv32',short)]
        if a.render_proof:
            prior=workspace_path(a.render_proof);old=json.loads(prior.read_text())
            assert set(old['rendering'])=={x[0] for x in render_jobs}
            for n,h in old['source_sha256'].items():
                if n!='scripts/check_xinyi_gui_buffering.py':assert sha(ROOT/n)==h,n
            result['rendering']=old['rendering'];result['rendering_inherited_receipt_sha256']=sha(prior)
            result['rendering_inherited_source_sha256']=old['source_sha256'];render_jobs=[]
        for name,mode,target,source in render_jobs:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            exe=out/name
            run(name+'-build',[cc,*flags,*extra,'-DXINYI_GUI_DOUBLE_BUFFER='+str(mode),*inc,wsl_path(source),
                *[wsl_path(ROOT/n) for n in renderer[3:]],'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
            text=run(name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),wsl_path(out)],240)
            rows=[]
            for line in text.splitlines():
                if line.startswith('GUI_BANK_FRAME '):rows.append(dict(w.split('=',1) for w in line.split()[1:]))
            assert rows and 'XINYI_FRAMEBUFFER_PASS' in text
            result['rendering'][name]=rows
        hashes=lambda n:[r['sha'] for r in result['rendering'][n]]
        assert hashes('baseline')==hashes('candidate')==hashes('sanitizer')
        assert hashes('short-host')==hashes('short-rv32')
        # Synthetic device-tree fixtures, with the original negative cases.
        dt=out/'dt'
        for label in ['covered','split','missing-no-map','truncated-camera','bad-cells','bad-ranges','missing-clint']:
            r=dt/label/'reserved-memory';r.mkdir(parents=True)
            (r/'#address-cells').write_bytes(struct.pack('>I',2 if label=='bad-cells' else 1))
            (r/'#size-cells').write_bytes(struct.pack('>I',1));(r/'ranges').write_bytes(b'x' if label=='bad-ranges' else b'')
            spans=[(0x1b200000,0x200000),(0x1b400000,0x200000),(0x1b600000,0x200000),(0x1b800000,0x400000),(0x1bc00000,0x400000)]
            if label!='missing-clint':spans.append((0x02000000,0x10000))
            for i,(address,size) in enumerate(spans):
                p=r/str(i);p.mkdir();(p/'reg').write_bytes(struct.pack('>II',address,size-(4 if label=='truncated-camera' and i==0 else 0)))
                if not(label=='missing-no-map' and i==0):(p/'no-map').write_bytes(b'')
        for target in ['host','rv32','sanitizer']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            exe=out/('platform-'+target)
            run(exe.name+'-build',[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*extra,*inc,
                '-DXY_PLATFORM_TEST','-DXINYI_GUI_DOUBLE_BUFFER=1','-pthread',
                *[wsl_path(ROOT/n) for n in platform],'-Wl,--gc-sections','-lutil','-o',wsl_path(exe)])
            text=run(exe.name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),wsl_path(dt)])
            assert 'XINYI_GUI_BACK_PAGE_ACK_TWO_FRAMES_WRAP_ERRORS_TIMEOUT_PREVIEW_PASS_NOT_BOARD' in text
            assert 'XINYI_PLATFORM_HOST_PASS' in text
        assert all(sha(ROOT/n)==h for n,h in before.items())
        result['status']='GUI_TWO_BANK_FULL_PIXELS_FONT_WORD_COUNTS_AND_PLATFORM_ACK_PASS_NOT_BOARD'
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for name in ['baseline','candidate']:
        rows=result['rendering'][name];print(name,'frames',len(rows),'first_frame',rows[0], 'warm_home_writes',[r['writes'] for r in rows[1:5]])


if __name__=='__main__':main()
