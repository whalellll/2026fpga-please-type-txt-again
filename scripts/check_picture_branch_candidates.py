"""Isolated pinned-main GUI primitives and word-copy review, no branch merge."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import shlex
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

BASE='776f217c68305ff8c074862c9b9c0d35bdfeaf81'
MAIN='538215e20b0d628e713f296cfbe7e13c741e42a5'
RENDER='linux/pikafish/xiangqi_fb_gui_1080.c'


def function(text,signature):
    start=text.index(signature);open_at=text.index('{',start);depth=0
    for i in range(open_at,len(text)):
        if text[i]=='{':depth+=1
        if text[i]=='}':
            depth-=1
            if not depth:return start,i+1,text[start:i+1]
    raise AssertionError('Unclosed '+signature)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args();out=workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(exist_ok=False)
    git=lambda ref,path:subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT,timeout=30)
    digest=lambda b:hashlib.sha256(b).hexdigest()
    originals={n:(ROOT/n).read_bytes() for n in [RENDER,'linux/xinyi/xinyi_fb.c','linux/xinyi/test_fb.c',
        'linux/xinyi/xinyi_product.c','linux/mac_accel/kernel/pango_mac_io32.h','linux/mac_accel/test_io32_bulk.c']}
    assert originals[RENDER]==git(BASE,RENDER),'Renderer has accumulated local edits'
    result=dict(status='FAILED_PRESERVED',base=BASE,incoming=MAIN,hardware_used=False,
        production_sources_modified=False,checks=[],gui={},io={},source_sha256={n:digest(b) for n,b in originals.items()})
    flags=['-std=gnu11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
    common_includes=['linux/pikafish/include','linux/pikafish','sw/xiangqi','sw/video','linux/voice','linux/xinyi',
                     'artifacts/vision-model-20261020-adapter/runtime']
    inc=['-I'+wsl_path(ROOT/p) for p in common_includes]
    sha_source=ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c'
    def run(name,args,seconds=120,codes=(0,)):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        result['checks'].append(dict(name=name,exit=p.returncode))
        assert p.returncode in codes,(name,text[-1800:]);return text
    try:
        base=originals[RENDER].decode();incoming=git(MAIN,RENDER).decode()
        candidate=base
        for signature in ['static void draw_ui_glyph(','static void draw_disc(','static void draw_ring(']:
            start,end,_=function(candidate,signature);new=function(incoming,signature)[2]
            if signature.startswith('static void draw_ui_glyph'):
                new=function(incoming,'static uint16_t blend_ui_colour(')[2]+'\n\n'+new
            candidate=candidate[:start]+new+candidate[end:]
        (out/'renderer-primitives.patch').write_text(''.join(difflib.unified_diff(base.splitlines(True),candidate.splitlines(True),
            fromfile='a/'+RENDER,tofile='b/'+RENDER)),encoding='utf-8',newline='\n')
        (out/'incoming-renderer.c').write_bytes(git(MAIN,RENDER))
        fixture=git(MAIN,'sim/test_gui1080_host.c').decode()
        # Independent full-buffer SHA complements per-frame dirty/full memcmp.
        fixture=fixture.replace('#include <stdio.h>','#include <stdio.h>\n#include "xq_sha256.h"',1)
        needle='printf("GUI_FRAME step=%u fnv=%08x\\n",step,hash);'
        assert fixture.count(needle)==1
        fixture=fixture.replace(needle,needle+' char sha[65];xq_sha256_hex(current,VIDEO_FB_FRAME_BYTES,sha);printf("GUI_SHA step=%u value=%s\\n",step,sha);')
        legacy=out/'legacy-fixture.c';legacy.write_text(fixture,newline='\n')
        product=originals['linux/xinyi/test_fb.c'].decode()
        start,end,_=function(product,'static void save_ppm(')
        product=product[:start]+'''static void save_ppm(const char *dir,const char *name,const uint16_t *pixels)
{ char sha[65];(void)dir;xq_sha256_hex(pixels,VIDEO_FB_FRAME_BYTES,sha);printf("PRODUCT_SAVE name=%s sha=%s\\n",name,sha); }
'''+product[end:]
        product=product.replace('#include "xinyi_fb.c"','#include "xinyi_fb.c"\n#include "xq_sha256.h"',1)
        needle='assert(!memcmp(actual,reference,VIDEO_FB_FRAME_BYTES));';assert product.count(needle)==1
        product=product.replace(needle,needle+' {static unsigned n;char sha[65];xq_sha256_hex(actual,VIDEO_FB_FRAME_BYTES,sha);printf("PRODUCT_FRAME step=%u sha=%s\\n",n++,sha);}')
        prod_fixture=out/'product-fixture.c';prod_fixture.write_text(product,newline='\n')
        helper='''#include <stdint.h>
static uint64_t gui_fb_reads,gui_fb_writes;
static inline uint32_t gui_fb_read(volatile uint32_t *p,unsigned i){gui_fb_reads++;return p[i];}
static inline void gui_fb_write(volatile uint32_t *p,unsigned i,uint32_t v){gui_fb_writes++;p[i]=v;}
'''
        for label,text in [('baseline',base),('candidate',candidate)]:
            folder=out/label;folder.mkdir()
            counted=re.sub(r'words\[([^\]]+)\]\s*=\s*(.*?);',lambda m:'gui_fb_write(words,'+m[1]+','+m[2]+');',text,flags=re.S)
            counted=re.sub(r'words\[([^\]]+)\]',lambda m:'gui_fb_read(words,'+m[1]+')',counted)
            (folder/'xiangqi_fb_gui_1080.c').write_text(helper+counted,newline='\n')
            (folder/'uncounted-renderer.c').write_text(text,newline='\n')
        result['gui']['candidate_sha256']=digest(candidate.encode())
        result['gui']['main_primitive_functions_only']=True
        summaries={}
        for target in ['host','sanitizer','rv32']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            for kind,source in [('legacy',legacy),('product',prod_fixture)]:
                for label in ['baseline','candidate']:
                    folder=out/label;exe=out/(target+'-'+kind+'-'+label)
                    sources=[source,sha_source,ROOT/'sw/xiangqi/xiangqi_search.c']
                    if kind=='legacy':sources += [ROOT/'linux/voice/xqvoice_protocol.c',ROOT/'sw/xiangqi/xiangqi_mouse_input.c']
                    else:sources += [ROOT/'linux/xinyi/xinyi_product.c']
                    defines=['-DVIDEO_FB_LINUX_MMAP','-DGUI_FB_COUNTED','-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h')]
                    if kind=='legacy':defines+=['-DXQ_RENDERER_SOURCE="'+wsl_path(folder/'xiangqi_fb_gui_1080.c')+'"']
                    run(exe.name+'-build',[cc,*flags,*extra,*defines,'-I'+wsl_path(folder),*inc,
                        *[wsl_path(p) for p in sources],'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
                    if target=='rv32':continue  # Compile only: exact runtime proof below is host+sanitizers.
                    text=run(exe.name,[wsl_path(exe),wsl_path(out)],180)
                    frames=re.findall(r'^(?:GUI_SHA|PRODUCT_FRAME|PRODUCT_SAVE).*$',text,re.M)
                    assert len(frames)>=60,(kind,'missing frame comparisons')
                    summaries[target,kind,label]=frames
                    if kind=='legacy':
                        io_counts=[tuple(map(int,p)) for p in re.findall(r'GUI_IO step=\d+ reads=(\d+) writes=(\d+)',text)]
                        assert len(io_counts)==96
                        result['gui'][target+'-'+label+'-legacy_io']=dict(reads=sum(x[0] for x in io_counts),writes=sum(x[1] for x in io_counts))
                if target!='rv32':assert summaries[target,kind,'baseline']==summaries[target,kind,'candidate'],(target,kind,'pixel SHA changed')
        for kind in ['legacy','product']:
            assert summaries['host',kind,'baseline']==summaries['sanitizer',kind,'candidate']
        result['gui'].update(host_sanitizer_all_frame_sha_equal=True,legacy_frames=96,
            product_frame_records=len(summaries['host','product','candidate']),rv32_compile_only=True,
            pixel_io_counts_not_measured_hardware_traffic=True)
        # Exercise main's new helper against the existing posted-write oracle.
        header=out/'incoming-pango_vision_io_modes.h';header.write_bytes(git(MAIN,'linux/mac_accel/kernel/pango_vision_io_modes.h'))
        io_src=originals['linux/mac_accel/test_io32_bulk.c'].decode()
        io_src=io_src.replace('#include "kernel/pango_mac_io32.h"',
            '#define readl readl_relaxed\n#define writel writel_relaxed\n#include "incoming-pango_vision_io_modes.h"')
        io_src=io_src.replace('pango_mac_toio32(','pango_mac_toio32_unrolled(').replace('pango_mac_fromio32(','pango_mac_fromio32_unrolled(')
        test=out/'io-unrolled.c';test.write_text(io_src,newline='\n')
        for target in ['host','rv32','sanitizer']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
            exe=out/('io-'+target)
            run(exe.name+'-build',[cc,*flags,*extra,'-I'+wsl_path(out),wsl_path(test),'-o',wsl_path(exe)])
            text=run(exe.name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe)])
            assert 'PANGO_IO32_BULK_BOUNDARY_TAIL_ALIGNMENT_PASS cases=192' in text
            result['io'][target]=dict(cases=192,word_only=True,tail_neighbors=True,both_boundaries=True,posted_dma_mock=True)
        for missing in ['BEGIN','END']:
            exe=out/('negative-'+missing.lower())
            run(exe.name+'-build',['gcc',*flags,'-DPANGO_TEST_OMIT_'+missing,'-I'+wsl_path(out),wsl_path(test),'-o',wsl_path(exe)])
            text=run(exe.name,[wsl_path(exe)],codes=(6,134));assert 'Assertion' in text
        # Mutant with a transparent first pixel must not discard its neighbor.
        mutant=candidate.replace('if(!(a0|a1))','if(!a0)');assert mutant!=candidate
        f=out/'wrong-alpha.c';f.write_text(mutant,newline='\n');exe=out/'wrong-alpha'
        run('wrong-alpha-build',['gcc',*flags,'-DVIDEO_FB_LINUX_MMAP','-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h'),
            '-DXQ_RENDERER_SOURCE="'+wsl_path(f)+'"',*inc,wsl_path(legacy),wsl_path(sha_source),
            wsl_path(ROOT/'linux/voice/xqvoice_protocol.c'),wsl_path(ROOT/'sw/xiangqi/xiangqi_mouse_input.c'),
            wsl_path(ROOT/'sw/xiangqi/xiangqi_search.c'),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
        text=run('wrong-alpha',[wsl_path(exe)],codes=(0,1))
        wrong=re.findall(r'^GUI_SHA.*$',text,re.M)
        assert wrong!=summaries['host','legacy','baseline'][:len(wrong)] or len(wrong)!=96
        assert all((ROOT/n).read_bytes()==b for n,b in originals.items())
        result.update(status='PINNED_MAIN_GUI_PIXEL_AND_UNROLLED_COPY_CANDIDATES_PASS_NOT_MERGED_NOT_BOARD',
            io_barrier_negatives_rejected=True,gui_alpha_negative_rejected=True,
            incoming_renderer_sha256=digest(git(MAIN,RENDER)),incoming_io_header_sha256=digest(header.read_bytes()))
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status']);print(json.dumps(result['gui'],indent=2))


if __name__=='__main__':main()
