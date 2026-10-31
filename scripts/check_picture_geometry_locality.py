"""Bitwise geometry traversal comparison and bounded host/QEMU microbench.

Synthetic tests are public. Optional --private-fixture is a separately
authorized capture, never copied/hashes published by this checker.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--private-fixture',type=Path)
    ap.add_argument('--targets',choices=['host','host,qemu'],default='host,qemu')
    ap.add_argument('--variant',choices=['row','gray','both','fast','arith','add','compact','selective','compact-selective','seed'],default='row')
    ap.add_argument('--baseline',choices=['frozen','pn08','speed-r01'],default='frozen')
    ap.add_argument('--sanitizer',action='store_true',help='Also check real refinement and every allocation failure under ASan/UBSan')
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    old='artifacts/vision-model-20261020-adapter/runtime/xq_native_post.c';new='linux/picture_new/geometry_locality.c'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original=(ROOT/old).read_text();local=(ROOT/new).read_text()
    assert re.search(r'Source SHA256 ([a-f0-9]{64})',local).group(1)==sha(ROOT/old)
    local=local[local.index('#include "xq_native_post.h"'):].replace('../../artifacts/vision-model-20261020/geometry/geometry_reference.c','../../vision-model-20261020/geometry/geometry_reference.c')
    # Recover exact original source by selecting rollback arms. This covers
    # all QR/RANSAC/thresholds, not just a collection of expected constants.
    def rollback(block):
        depth=0;begin=None;end=None
        for match in re.finditer(r'^#\s*(if\b[^\n]*|ifdef\b[^\n]*|ifndef\b[^\n]*|else\b[^\n]*|endif\b[^\n]*)\n',block,re.M):
            directive=match[1].split()[0]
            if directive in ('if','ifdef','ifndef'):depth+=1
            elif directive=='else' and depth==1:begin=match.end()
            elif directive=='endif':
                depth-=1
                if depth==0:end=match.start()
        assert depth==0 and end is not None
        return block[begin:end] if begin is not None else ''
    # Inner optional blocks must be restored before the enclosing ROW arm.
    for name in ['SEED_SCORE','SEED_DISTANCE','SEED_BOUND',
                 'SELECT_HORIZONTAL','SELECT_VERTICAL','COMPACT_HORIZONTAL','COMPACT_VERTICAL',
                 'REDUCE_HELPERS','SELECT_SIGNATURE','SELECT_REDUCTION','SELECT_WRAPPER',
                 'COMPACT_DECL','COMPACT_ALLOC','SELECT_FIRST',
                 'FAST_HELPERS','SPARSE_PREFIX','EXACT_PREFIX','EXACT_CONTRAST',
                 'MASK_HORIZONTAL','EXACT_HORIZONTAL','MASK_VERTICAL','EXACT_VERTICAL',
                 'SEARCH_BOUNDS','SEARCH_PRUNE','ROW','GRAY','TABLE']:
        begin='/* XQGEOM_'+name+'_BEGIN */\n';endmark='/* XQGEOM_'+name+'_END */\n'
        at=local.index(begin);endat=local.index(endmark,at)+len(endmark)
        block=local[at:endat];replacement=rollback(block)
        local=local[:at]+replacement+local[endat:]
    for marker in ['/* XQGEOM_SEARCH_WINDOW_BEGIN */\n','/* XQGEOM_SEARCH_WINDOW_END */\n']:
        assert local.count(marker)==1
        local=local.replace(marker,'')
    assert local==original,'Unselected original geometry source changed'
    mark='static int box_sum(';end='/* Normalized least squares'
    assert original[:original.index(mark)]==local[:local.index(mark)]
    assert original[original.index(end):]==local[local.index(end):], 'QR/RANSAC/guards must remain exact source'
    for token in ['    for(unsigned y=0;y<=ph;y++) {','    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++) {']:
        assert original[original.index(token):original.index(end)]==local[local.index(token):local.index(end)]
    sources=['linux/picture_new/test_geometry_locality.c','artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
    files=set(sources+[old,new,'artifacts/vision-model-20261020/geometry/geometry_reference.c','scripts/check_picture_geometry_locality.py'])
    for d in includes:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h'))
    before={p:sha(ROOT/p) for p in sorted(files)}
    result={'status':'FAILED_PRESERVED','source_sha256':before,'hardware_used':False,'targets':{},
            'variant':a.variant,
            'baseline':a.baseline,
            'all_guards_qr_ransac_unchanged_source':True,'private_fixture_used':bool(a.private_fixture),
            'not_board_latency':True,'not_camera_v2_or_game2':True}

    def run(name,args,seconds=300):
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
        return (out/(name+'.log')).read_text()
    try:
        for target in a.targets.split(',')+(['sanitizer'] if a.sanitizer else []):
            platform={};outputs={};private={}
            for name,source in [('baseline',old if a.baseline=='frozen' else new),('locality',new)]:
                cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='qemu' else 'gcc'
                flags=['-std=c11','-O2','-ffp-contract=off','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-DXQGEOM_TEST_REDUCE']
                if target=='sanitizer':flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-DXQGEOM_TEST_ALLOC_FAIL','-Wl,--wrap=malloc,--wrap=calloc']
                if source==new:
                    variant=a.variant if name=='locality' else 'compact-selective' if a.baseline=='speed-r01' else 'arith'
                    flags+=['-DXQ_GEOMETRY_ROW_LOCAL='+str(int(variant in ['row','both'])),
                        '-DXQ_GEOMETRY_GRAY_TABLE='+str(int(variant!='row')),
                        '-DXQ_GEOMETRY_FAST='+str(int(variant in ['fast','arith','add','compact','selective','compact-selective','seed'])),
                        '-DXQ_GEOMETRY_ARITH='+str(int(variant in ['arith','add','compact','selective','compact-selective','seed'])),
                        '-DXQ_GEOMETRY_ADD='+str(int(variant=='add')),
                        '-DXQ_GEOMETRY_COMPACT='+str(int(variant in ['compact','compact-selective','seed'])),
                        '-DXQ_GEOMETRY_SELECTIVE='+str(int(variant in ['selective','compact-selective','seed'])),
                        '-DXQ_GEOMETRY_SEED_BOUND='+str(int(variant=='seed'))]
                if target=='qemu':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
                binary=out/(target+'-'+name)
                run(target+'-'+name+'-build',[cc,*flags,*['-I'+wsl_path(ROOT/d) for d in includes],
                    '-DGEOMETRY_SOURCE="'+wsl_path(ROOT/source)+'"',*[wsl_path(ROOT/p) for p in sources],
                    '-Wl,--gc-sections','-lm','-o',wsl_path(binary)],90)
                prefix=['qemu-riscv32'] if target=='qemu' else []
                text=run(target+'-'+name+'-synthetic',[*prefix,wsl_path(binary),'--synthetic',
                    wsl_path(ROOT/'build/picture-merge-20261023/native-models/refinement_rng.bin')])
                outputs[name]=[v for v in text.splitlines() if not v.startswith(('GEOMETRY_HOST_OR_QEMU_NS','GEOMETRY_REDUCTIONS','GEOMETRY_ALLOCATION_FAILURES_PASS'))]
                if target=='sanitizer':
                    assert 'GEOMETRY_ALLOCATION_FAILURES_PASS' in text
                    platform[name+'_allocation_failures_checked']=int(re.search(r'GEOMETRY_ALLOCATION_FAILURES_PASS count=(\d+)',text)[1])
                if name=='locality' and a.variant in ['selective','compact-selective','seed']:
                    assert int(re.search(r'GEOMETRY_REDUCTIONS retained=\d+ omitted=(\d+)',text)[1])>0
                    platform['synthetic_reduction_counters']=re.search(r'GEOMETRY_REDUCTIONS .*',text)[0]
                assert len([v for v in outputs[name] if 'box_sum_' in v])==6
                assert 'GEOMETRY_RESULT pass=1' in text and 'GEOMETRY_RESULT pass=0' in text
                if a.private_fixture:
                    timing=out/(target+'-'+name+'-timing')
                    timing_flags=[v for v in flags if v!='-DXQGEOM_TEST_REDUCE']
                    run(target+'-'+name+'-timing-build',[cc,*timing_flags,*['-I'+wsl_path(ROOT/d) for d in includes],
                        '-DGEOMETRY_SOURCE="'+wsl_path(ROOT/source)+'"',*[wsl_path(ROOT/p) for p in sources],
                        '-Wl,--gc-sections','-lm','-o',wsl_path(timing)],90)
                    text=run(target+'-'+name+'-private',[*prefix,wsl_path(timing),'--private-fixture',wsl_path(a.private_fixture)])
                    private[name]=[v for v in text.splitlines() if not v.startswith(('GEOMETRY_HOST_OR_QEMU_NS','GEOMETRY_REDUCTIONS'))]
                    ns=[int(v.split()[-1]) for v in text.splitlines() if v.startswith('GEOMETRY_HOST_OR_QEMU_NS')]
                    platform[name+'_private_median_ns']=statistics.median(ns)
            assert outputs['baseline']==outputs['locality'],target+' synthetic differs'
            if a.private_fixture:
                assert private['baseline']==private['locality'],target+' private geometry differs'
                platform.update(private_frame_geometry_bit_equal=True,
                        private_timing_reduction_probes_disabled=True,
                    private_microbench_ratio=platform['baseline_private_median_ns']/platform['locality_private_median_ns'])
            platform['synthetic_integral_refinement_statistics_bit_equal']=True
            # Only synthetic digests are published. Private logs stay here.
            platform['synthetic_reference_checks']=outputs['baseline'];result['targets'][target]=platform
        assert all(sha(ROOT/p)==h for p,h in before.items())
        result.update(status='GEOMETRY_'+a.variant.upper()+'_BIT_EQUAL_HOST_RV32_PASS_NOT_BOARD',source_stable=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
