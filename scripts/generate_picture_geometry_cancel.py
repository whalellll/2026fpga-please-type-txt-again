"""Generate an explicit cancellable overlay; reverse edits recover exact source.

The frozen geometry, mask helper, arithmetic and legacy entry points stay in
their original files. Only explicit-call probes/cleanup are added to an output
translation unit. No TLS/global cancellation state, device access or logging.
"""
from pathlib import Path
import argparse,hashlib,json

def generate(root,output):
    original_bytes=(root/'linux/picture_new/geometry_locality.c').read_bytes()
    newline='\r\n' if b'\r\n' in original_bytes else '\n'
    original=original_bytes.decode().replace('\r\n','\n')
    mask=(root/'linux/picture_new/geometry_mask.h').read_text()
    source=original;edits=[]
    def edit(old,new,count=1):
        nonlocal source
        assert source.count(old)==count,('source anchor drift',old[:100],source.count(old))
        source=source.replace(old,new);edits.append((old,new,count))
    def poll(phase,index,cleanup='goto done;'):
        return 'if(xqgeom_cancel_poll(control,'+phase+','+index+')){'+cleanup+'}'
    mask_body=mask[mask.index('static int xqgeom_mask8_sum('):mask.rindex('#endif')]
    mask_body=mask_body.replace('static int xqgeom_mask8_sum(','static int xqgeom_mask8_sum_cancellable(')
    mask_body=mask_body.replace('unsigned width,unsigned height)','unsigned width,unsigned height,xqgeom_cancel_state *control)')
    mask_body=mask_body.replace('    uint16_t columns[1280];','    if(!control || !control->cancelled)return xqgeom_mask8_sum(in,hy,hx,out,width,height);\n    uint16_t columns[1280];')
    mask_body=mask_body.replace('    for(unsigned x=0;x<width;x++) {','    for(unsigned x=0;x<width;x++) {\n        if(!(x&15u) && xqgeom_cancel_poll(control,XQGC_MASK,x))return 0;')
    mask_body=mask_body.replace('    for(unsigned y=0;y<height;y++) {','    for(unsigned y=0;y<height;y++) {\n        if(!(y&15u) && xqgeom_cancel_poll(control,XQGC_MASK,y))return 0;')
    dependency='''#include "geometry_cancel.h"
#if !defined(XQ_GEOMETRY_CANCEL) || XQ_GEOMETRY_CANCEL != 1 || \
    !defined(XQ_GEOMETRY_FAST) || !XQ_GEOMETRY_FAST || \
    !defined(XQ_GEOMETRY_ARITH) || !XQ_GEOMETRY_ARITH || \
    !defined(XQ_GEOMETRY_COMPACT) || !XQ_GEOMETRY_COMPACT || \
    !defined(XQ_GEOMETRY_SELECTIVE) || !XQ_GEOMETRY_SELECTIVE
#error geometry_cancel_requires_fast_arith_compact_selective
#endif
'''
    edit('#include "xq_native_post.h"\n',dependency+'#include "xq_native_post.h"\n')
    edit('#include "geometry_mask.h"\n','#include "geometry_mask.h"\n'+mask_body)
    edit('const double *previous)\n','const double *previous,xqgeom_cancel_state *control)\n')
    edit('    if(!integral)return 0;\n','    if(!integral)return 0;\n    '+poll('XQGC_PREFIX_COLUMN','0','free(integral);return 0;')+'\n')
    for prefix,index in [('    for(unsigned y=0;y<ph;y++) {\n','y'),('    for(unsigned x=0;x<pw;x++) {\n','x')]:
        edit('\n'+prefix,'\n'+prefix+'        if(!('+index+'&15u) && xqgeom_cancel_poll(control,XQGC_PREFIX_COLUMN,'+index+')){free(integral);return 0;}\n')
    edit('    for(unsigned y=0;y<=ph;y++) {\n','    for(unsigned y=0;y<=ph;y++) {\n        if(!(y&15u) && xqgeom_cancel_poll(control,XQGC_PREFIX_ROW,y)){free(integral);return 0;}\n')
    edit('    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++) {\n/* XQGEOM_SELECT_REDUCTION_BEGIN */',
        '    for(unsigned y=0;y<height;y++){\n        if(!(y&15u) && xqgeom_cancel_poll(control,XQGC_REDUCTION,y)){free(integral);return 0;}\n        for(unsigned x=0;x<width;x++) {\n/* XQGEOM_SELECT_REDUCTION_BEGIN */')
    edit('    free(integral);return 1;','    }\n    free(integral);return 1;')
    edit('return box_sum_selected(in,hy,hx,out,width,height,NULL,NULL,NULL);','return box_sum_selected(in,hy,hx,out,width,height,NULL,NULL,NULL,NULL);')
    edit('xnp_refinement *stats,unsigned trials,int crop)','xnp_refinement *stats,unsigned trials,int crop,xqgeom_cancel_state *control)')
    edit('    if(!rgb || !rng || nb>300 || !xnp_coarse(coarse,seed,NULL))return 0;',
        '    '+poll('XQGC_START','0')+'\n    if(!rgb || !rng || nb>300 || !xnp_coarse(coarse,seed,NULL))return 0;')
    edit('    if(!gray || !mask || !tmp || !score || !counts)goto done;',
        '    if(!gray || !mask || !tmp || !score || !counts)goto done;\n    '+poll('XQGC_START','1'))
    edit('    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++) {\n        size_t i=',
        '    for(unsigned y=0;y<height;y++){\n        if(!(y&15u) && xqgeom_cancel_poll(control,XQGC_GRAY,y))goto done;\n        for(unsigned x=0;x<width;x++) {\n        size_t i=')
    edit('/* XQGEOM_GRAY_END */\n    }','/* XQGEOM_GRAY_END */\n    }\n    }')
    edit('        for(int y=y0;y<y1;y++)for(int x=x0;x<x1;x++)mask[(size_t)y*width+(unsigned)x]=0;',
        '        for(int y=y0;y<y1;y++){\n            if(!((unsigned)y&15u) && xqgeom_cancel_poll(control,XQGC_PIECES,(unsigned)y))goto done;\n            for(int x=x0;x<x1;x++)mask[(size_t)y*width+(unsigned)x]=0;\n        }')
    for old in ['box_sum_selected(gray,15,15,tmp,width,height,NULL,mask,NULL)',
                'box_sum_selected(gray,1,13,tmp,width,height,counts,NULL,NULL)',
                'box_sum_selected(gray,13,1,tmp,width,height,counts,mask,score)']:
        edit(old,old[:-1]+',control)',1 if '15,15' in old else 2)
    for hy,hx in [(1,13),(13,1)]:
        old=f'xqgeom_mask8_sum(mask,{hy},{hx},counts,width,height)'
        edit(old,f'xqgeom_mask8_sum_cancellable(mask,{hy},{hx},counts,width,height,control)')
    def chunk(phase):
        return '    for(size_t begin=0;begin<pixels_count;begin+=8192){\n        '+poll(phase,'begin')+'\n        size_t limit=pixels_count-begin<8192?pixels_count:begin+8192;\n        for(size_t i=begin;i<limit;i++)'
    edit('    for(size_t i=0;i<pixels_count;i++) {\n        if(mask[i]==0)',chunk('XQGC_CONTRAST')+' {\n        if(mask[i]==0)')
    edit('gray[i]=contrast<=0?0:contrast>=60?1:xqgeom_div(contrast,60);\n    }',
        'gray[i]=contrast<=0?0:contrast>=60?1:xqgeom_div(contrast,60);\n    }\n    }')
    old='    for(size_t i=0;i<pixels_count;i++)score[i]=counts[i]<48?-1:xqgeom_div(tmp[i],(unsigned)counts[i]);'
    edit(old,chunk('XQGC_SCORE')+old.split('i++)',1)[1]+'\n    }')
    old='    for(size_t i=0;i<pixels_count;i++)score[i]=score[i]<0 || counts[i]<48 || mask[i]<.5?0:fmin(score[i],xqgeom_div(tmp[i],(unsigned)counts[i]));'
    edit(old,chunk('XQGC_SCORE')+old.split('i++)',1)[1]+'\n    }')
    edit('    for(unsigned gy=0;gy<9;gy++)for(unsigned gx=0;gx<10;gx++) {',
        '    for(unsigned gy=0;gy<9;gy++)for(unsigned gx=0;gx<10;gx++) {\n        '+poll('XQGC_GRID','gy*10+gx'))
    edit('    for(unsigned trial=0;trial<trials;trial++) {','    for(unsigned trial=0;trial<trials;trial++) {\n        '+poll('XQGC_RANSAC','trial'))
    edit('    for(unsigned trial=0;trial<5;trial++) {','    for(unsigned trial=0;trial<5;trial++) {\n        '+poll('XQGC_REFIT','trial'))
    edit('        if(stats)stats->inliers=count;','        '+poll('XQGC_FINAL','count')+'\n        if(stats)stats->inliers=count;')
    edit('refine_run(rgb,coarse,boxes,n,rng,refined,stats,80,1);','refine_run(rgb,coarse,boxes,n,rng,refined,stats,80,1,NULL);')
    edit('refine_run(rgb,coarse,boxes,n,rng,refined,stats,240,0);','refine_run(rgb,coarse,boxes,n,rng,refined,stats,240,0,NULL);')
    old='"../../artifacts/vision-model-20261020/geometry/geometry_reference.c"'
    edit(old,'"'+(root/'artifacts/vision-model-20261020/geometry/geometry_reference.c').as_posix()+'"')
    restored=source
    for old,new,count in reversed(edits):
        assert restored.count(new)==count,('reverse anchor drift',new[:100])
        restored=restored.replace(new,old)
    assert restored.replace('\n',newline).encode()==original_bytes,'numeric/guard source changed outside reviewed overlay'
    api='''
int xqcoach_refine_cancellable(const uint8_t *rgb,const double coarse[4][2],const xqr_box *boxes,unsigned n,
    const uint8_t rng[91][240][4],double refined[4][2],xnp_refinement *stats,
    int (*cancelled)(void *),void *context)
{
    xqgeom_cancel_state control={cancelled,context,0};
    if(!refined){if(stats)memset(stats,0,sizeof(*stats));return 0;}
    int okay=refine_run(rgb,coarse,boxes,n,rng,refined,stats,80,1,&control);
    if(xqgeom_cancel_poll(&control,XQGC_FINAL,90)){
        memset(refined,0,8*sizeof(double));if(stats)memset(stats,0,sizeof(*stats));return 0;
    }
    return okay;
}
'''
    assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes((source+api).encode())
    sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
    record=dict(status='GEOMETRY_CANCEL_OVERLAY_REVERSES_TO_EXACT_SOURCE',
        original_sha256=sha(root/'linux/picture_new/geometry_locality.c'),mask_sha256=sha(root/'linux/picture_new/geometry_mask.h'),
        generated_sha256=sha(output),edits=len(edits),no_shared_cancellation_state=True)
    output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n');return record
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();print(generate(Path(__file__).resolve().parents[1],a.output)['status'])
