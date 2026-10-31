"""Finite exact output transpose, frozen auxiliary graph and CPU pair checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import statistics
import struct
import subprocess
import zlib
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--phase',choices=['unit','graphs','all'],default='all')
    ap.add_argument('--targets',default='host,rv32,sanitizer')
    ap.add_argument('--expect-old-path',action='store_true')
    a=ap.parse_args();out=workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(exist_ok=False)
    targets=a.targets.split(',');assert targets and set(targets)<={'host','rv32','sanitizer'}
    assert not a.expect_old_path or (a.phase=='graphs' and targets==['host'])
    include=['linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
    graph_sources=['linux/picture_new/test_e42_model_mock.c','linux/picture_new/graph_runtime.c',
        'linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c','linux/picture_new/vision32_layer.c',
        'linux/picture_new/vision32_backend.c','linux/picture_new/graph_profile.c',
        'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    files=set(graph_sources+['linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/test_exact_graph.c','linux/picture_new/test_exact_word_output.c',
        'linux/picture_new/test_exact_word_output_layer.c',
        'linux/picture_new/graph_bilinear_s16.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
        'scripts/check_picture_exact_word_output.py'])
    for folder in include:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={n:sha(ROOT/n) for n in sorted(files)}
    result=dict(status='FAILED_PRESERVED',phase=a.phase,hardware_used=False,source_sha256=before,checks=[],targets={})
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
           '-ffp-contract=off','-ffunction-sections','-fdata-sections']
    inc=['-I'+wsl_path(ROOT/p) for p in include]
    def run(name,argv,seconds=90,codes=(0,)):
        with (out/(name+'.log')).open('xb') as log:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        result['checks'].append(dict(name=name,exit=r.returncode))
        assert r.returncode in codes,(name,text[-1800:]);return text
    try:
        original=(ROOT/'linux/picture_new/test_exact_graph.c').read_text()
        assert original.count('role<3;role++')==1
        source='unsigned xqewo_test_calls;\n'+original.replace('role<3;role++','role<3;role+=2')
        marker='unsigned exact=xqtest_exact_jobs();assert(xqn_run(m,&device.io,batch,v,0,&stats));'
        assert source.count(marker)==1
        source=source.replace(marker,'xqewo_test_calls=0;'+marker+'assert(xqewo_test_calls>0);')
        recovery='stop_after=0;\n        for(unsigned head=0;head<3;head++)free(expected[head]);'
        assert source.count(recovery)==1
        source=source.replace(recovery,'stop_after=0;\n        assert(xqn_run(m,&device.io,batch,v,0,&stats));\n        for(unsigned head=0;head<3;head++)if(bytes[head])assert(!memcmp(xqn_output(m,head,NULL),expected[head],bytes[head]));\n        for(unsigned head=0;head<3;head++)free(expected[head]);')
        fixture=out/'actual-aux-graphs.c';fixture.write_text(source,newline='\n')
        hook=out/'output-hook.h';hook.write_text('extern unsigned xqewo_test_calls;\n#define XQEWO_NOTE(p,c) (++xqewo_test_calls)\n')
        inputs=out/'inputs';inputs.mkdir()
        for name,role,side in [('board',0,192),('classifier',2,32)]:
            count=3*side*side;raw=bytes((i*37+i//257)%127-63 & 255 for i in range(count))
            header=struct.pack('<8s8Ii',b'XQINP1\0\0',1,role,1,3,side,side,count,zlib.crc32(raw),-6)
            (inputs/(name+'.input')).write_bytes(header+raw)
        models=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models'
        result['model_sha256']={n:sha(models/n) for n in ['board.xqm','classifier.xqm']}
        for target in targets:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            row=result['targets'].setdefault(target,{})
            if a.phase in ['unit','all']:
                exe=out/('unit-'+target)
                run(target+'-unit-build',[cc,*flags,*extra,*inc,wsl_path(ROOT/'linux/picture_new/test_exact_word_output.c'),'-o',wsl_path(exe)])
                text=run(target+'-unit',prefix+[wsl_path(exe),*(['--bench'] if target!='sanitizer' else [])])
                assert 'EXACT_WORD_OUTPUT_BYTES_GUARDS_PASS cases=152' in text
                pairs={}
                for shape,pair,word,ns in re.findall(r'OUTPUT_WORD_PAIR shape=(\d+) pair=(\d+) word=(\d+) cpu_ns=(\d+)',text):
                    pairs.setdefault(shape,{}).setdefault(int(word),[]).append(int(ns))
                row['unit_cases']=152
                row['pack_only_pairs']={n:dict(original_ns=v[0],word_ns=v[1],median_ratio=statistics.median(v[1])/statistics.median(v[0])) for n,v in pairs.items()}
            if a.phase in ['graphs','all']:
                exe=out/('graphs-'+target)
                options=['-DXQ_FAST_REQUANT=1','-DXQ_CLASSIFIER_S16=1','-DXQ_EXACT_EPILOGUE=1',
                    '-DXQ_FAST_FP32_BILINEAR=1','-DXQ_EXACT_WORD_INPUT=1','-DXQ_EXACT_WORD_OUTPUT=1',
                    '-include',wsl_path(hook)]
                if not a.expect_old_path:
                    layer=out/('layers-'+target)
                    run(target+'-layers-build',[cc,*flags,*extra,*options,*inc,
                        wsl_path(ROOT/'linux/picture_new/test_exact_word_output_layer.c'),
                        *[wsl_path(ROOT/p) for p in graph_sources],
                        '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl',
                        '-Wl,--gc-sections','-lm','-o',wsl_path(layer)])
                    text=run(target+'-layers',prefix+[wsl_path(layer)],120)
                    assert 'EXACT_WORD_OUTPUT_REAL_LAYER_PASS cases=14' in text
                    row['actual_layer_fallback_fault_cases']=14
                run(target+'-graphs-build',[cc,*flags,*extra,*options,*inc,wsl_path(fixture),
                    *[wsl_path(ROOT/p) for p in graph_sources],
                    '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl',
                    '-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
                text=run(target+'-graphs',prefix+[wsl_path(exe),wsl_path(models),wsl_path(inputs)],240,
                         codes=(6,134) if a.expect_old_path else (0,))
                if a.expect_old_path:
                    assert 'xqewo_test_calls>0' in text and 'Assertion' in text
                    row['old_scalar_did_not_exercise_new_path_rejected']=True
                else:
                    assert 'EXACT_GRAPH_ALL3_CLASSIFIER_B1_3_8_OUTPUT_CAPS_FATAL_CANCEL_PASS_NOT_BOARD' in text
                    row.update(frozen_aux_heads_equal_cpu=True,classifier_batches=[1,3,8],
                        new_path_observed=True,old_caps_raw=True,io_fatal_no_retry=True,
                        cancel_invalidates=True,same_model_recovery=True)
        if a.phase in ['unit','all']:
            header=(ROOT/'linux/picture_new/exact_word_output.h').read_text()
            assert header.count('(x&0xffffu)|(y<<16)')==1
            mutant=out/'wrong-lanes.h';mutant.write_text(header.replace('(x&0xffffu)|(y<<16)','(x>>16)|(y<<16)'))
            exe=out/'wrong-lanes'
            run('negative-build',['gcc',*flags,*inc,'-DEXACT_WORD_OUTPUT_HEADER="'+wsl_path(mutant)+'"',
                wsl_path(ROOT/'linux/picture_new/test_exact_word_output.c'),'-o',wsl_path(exe)])
            text=run('negative-lanes',[wsl_path(exe)],codes=(6,134));assert 'memcmp' in text and 'Assertion' in text
        assert all(sha(ROOT/n)==h for n,h in before.items())
        result['status']=('OLD_SCALAR_PATH_REJECTED_BY_REAL_CALL_COUNTER_NOT_CANDIDATE_PASS' if a.expect_old_path
                          else 'EXACT_WORD_OUTPUT_SELECTED_CHECKS_PASS_NOT_BOARD')
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for target,row in result['targets'].items():
        if 'pack_only_pairs' in row:print(target,'copy_only_ratios',{n:round(v['median_ratio'],4) for n,v in row['pack_only_pairs'].items()})


if __name__=='__main__':
    main()
