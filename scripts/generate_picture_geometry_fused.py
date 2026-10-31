"""Generate exact reduction/consumer fusion, optionally after cancellation.

Original geometry bytes are untouched. Prefix construction and ordered
((a-b)-c)+d arithmetic remain verbatim; only intermediate tmp traversals move.
"""
from pathlib import Path
import argparse
import hashlib
import json


def generate(root, source_path, output, retain_tmp=False):
    original_bytes = source_path.read_bytes()
    newline = '\r\n' if b'\r\n' in original_bytes else '\n'
    original = original_bytes.decode('utf-8').replace('\r\n', '\n')
    source = original
    edits = []
    assert 'XQGEOM_FUSED_HELPER' not in source
    cancellable = 'xqgeom_cancel_state *control' in source

    def edit(old, new, count=1):
        nonlocal source
        assert source.count(old) == count, ('fusion anchor drift', old[:100], source.count(old))
        source = source.replace(old, new)
        edits.append((old, new, count))

    begin = original.index('    unsigned pw=width+2*hx,ph=height+2*hy,stride=pw+1;')
    end = original.index('    for(unsigned y=0;y<height;', begin)
    prefix = original[begin:end]
    reduction = ('integral[(size_t)b*stride+r]-integral[(size_t)y*stride+r]-\n'
                 '                integral[(size_t)b*stride+x]+integral[(size_t)y*stride+x]')
    control = ',xqgeom_cancel_state *control' if cancellable else ''
    helper = '''/* XQGEOM_FUSED_HELPER_BEGIN */
#include "geometry_min_bits.h"
#if !defined(XQ_GEOMETRY_FUSED) || XQ_GEOMETRY_FUSED != 1 || \
    !defined(XQ_GEOMETRY_FAST) || !XQ_GEOMETRY_FAST || \
    !defined(XQ_GEOMETRY_ARITH) || !XQ_GEOMETRY_ARITH || \
    !defined(XQ_GEOMETRY_COMPACT) || !XQ_GEOMETRY_COMPACT || \
    !defined(XQ_GEOMETRY_SELECTIVE) || !XQ_GEOMETRY_SELECTIVE
#error geometry_fused_requires_fast_arith_compact_selective
#endif
/* Every prefix pass completes before writing output. mode1 may alias in,
 * mode3 may alias previous; each consumer reads only its own original value.
 * Prefix allocation/cleanup remains original. The now-unused tmp carrier is
 * removed by default; retain_tmp provides an isolated allocation control. */
static int box_sum_fused(const double *in,unsigned hy,unsigned hx,double *out,unsigned width,unsigned height,
    const xqgeom_count_value *counts,const xqgeom_mask_value *mask,const double *previous,unsigned mode'''+control+')\n{\n'+prefix
    for mode in [1, 2, 3]:
        helper += ('    if' if mode == 1 else '    else if')+'(mode=='+str(mode)+') {\n'
        helper += '        for(unsigned y=0;y<height;y++){\n'
        if cancellable:
            helper += '            if(!(y&15u) && xqgeom_cancel_poll(control,XQGC_REDUCTION,y)){free(integral);return 0;}\n'
        helper += '            for(unsigned x=0;x<width;x++){\n                size_t at=(size_t)y*width+x;\n'
        if cancellable:
            phase = 'XQGC_CONTRAST' if mode == 1 else 'XQGC_SCORE'
            helper += '                if(!(at&8191u) && xqgeom_cancel_poll(control,'+phase+',at)){free(integral);return 0;}\n'
        if mode == 1:
            helper += '                if(mask[at]==0){out[at]=0;continue;}\n'
        elif mode == 2:
            helper += '                if(counts[at]<48){out[at]=-1;continue;}\n'
        else:
            helper += '                if(previous[at]<0 || counts[at]<48 || mask[at]<.5){out[at]=0;continue;}\n'
        helper += '                unsigned b=y+2*hy+1,r=x+2*hx+1;\n                double value='+reduction+';\n'
        if mode == 1:
            helper += '                double contrast=xqgeom_div(value,961)-in[at]-5;\n'
            helper += '                out[at]=contrast<=0?0:contrast>=60?1:xqgeom_div(contrast,60);\n'
        elif mode == 2:
            helper += '                out[at]=xqgeom_div(value,(unsigned)counts[at]);\n'
        else:
            helper += '                out[at]=xqgeom_min(previous[at],xqgeom_div(value,(unsigned)counts[at]));\n'
        helper += '            }\n        }\n    }\n'
    helper += '    else {free(integral);return 0;}\n    free(integral);return 1;\n}\n/* XQGEOM_FUSED_HELPER_END */\n'
    anchor = '/* XQGEOM_SELECT_WRAPPER_END */'
    edit(anchor, anchor+'\n'+helper)
    for old, dest, mode, count in [
        ('box_sum_selected(gray,15,15,tmp,width,height,NULL,mask,NULL', 'gray', 1, 1),
        ('box_sum_selected(gray,1,13,tmp,width,height,counts,NULL,NULL', 'score', 2, 2),
        ('box_sum_selected(gray,13,1,tmp,width,height,counts,mask,score', 'score', 3, 2),
    ]:
        suffix = ',control)' if cancellable else ')'
        new = old.replace('box_sum_selected(', 'box_sum_fused(').replace(',tmp,', ','+dest+',')
        edit(old+suffix, new+','+str(mode)+suffix, count)
    for name in ['CONTRAST','HORIZONTAL','VERTICAL']:
        first = '/* XQGEOM_EXACT_'+name+'_BEGIN */'
        last = '/* XQGEOM_EXACT_'+name+'_END */'
        lo = source.index(first)+len(first)
        hi = source.index(last, lo)
        old = source[lo:hi]
        edit(first+old+last, first+'\n/* Applied in the completed-prefix reduction pass. */\n'+last)
    if not retain_tmp:
        edit('tmp=malloc(pixels_count*8);', '/* tmp carrier not materialized */', 2)
        edit('if(!gray || !mask || !tmp || !score || !counts)',
             'if(!gray || !mask || !score || !counts)')
    include = '"../../artifacts/vision-model-20261020/geometry/geometry_reference.c"'
    if include in source:
        path = (root/'artifacts/vision-model-20261020/geometry/geometry_reference.c').as_posix()
        if len(path) > 2 and path[1:3] == ':/':
            path = '/mnt/'+path[0].lower()+path[2:]
        edit(include, '"'+path+'"')
    restored = source
    for old, new, count in reversed(edits):
        assert restored.count(new) == count, ('fusion reverse drift', new[:100])
        restored = restored.replace(new, old)
    assert restored.replace('\n', newline).encode('utf-8') == original_bytes
    assert not output.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(source.encode('utf-8'))
    record = dict(status='GEOMETRY_FUSED_OVERLAY_REVERSES_TO_EXACT_INPUT',
        input_sha256=hashlib.sha256(original_bytes).hexdigest(),
        generated_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        cancellation_preserved=cancellable, production_sources_unchanged=True,
        original_prefix_arithmetic_and_allocations_retained=True,
        unused_tmp_allocation_removed=not retain_tmp, edits=len(edits))
    output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--retain-tmp', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(generate(root,args.input or root/'linux/picture_new/geometry_locality.c',args.output,args.retain_tmp)['status'])
