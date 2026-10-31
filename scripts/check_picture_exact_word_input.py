"""Exact word-transpose bytes, actual frozen auxiliary graphs and finite CPU pairs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import struct
import subprocess
import zlib
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(exist_ok=False)
    includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
    graph_sources=['linux/picture_new/test_e42_model_mock.c','linux/picture_new/graph_runtime.c',
        'linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c','linux/picture_new/vision32_layer.c',
        'linux/picture_new/vision32_backend.c','linux/picture_new/graph_profile.c',
        'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    files=set(graph_sources+['linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/exact_word_input.h','linux/picture_new/test_exact_word_input.c',
        'linux/picture_new/test_exact_graph.c','linux/picture_new/graph_bilinear_s16.c',
        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c','scripts/check_picture_exact_word_input.py'])
    for folder in includes:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={n:sha(ROOT/n) for n in sorted(files)}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,synthetic_only=True,source_sha256=before,checks=[],targets={})
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-ffp-contract=off','-ffunction-sections','-fdata-sections']
    inc=['-I'+wsl_path(ROOT/p) for p in includes]
    wraps=['-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl','-Wl,--gc-sections','-lm']
    def run(name,args,seconds=90,codes=(0,)):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        result['checks'].append(dict(name=name,exit_code=p.returncode))
        assert p.returncode in codes,(name,text[-1800:]);return text
    try:
        # The real caller must exercise the selected path, not merely produce
        # equal heads through an unchanged scalar fallback.
        original=(ROOT/'linux/picture_new/test_exact_graph.c').read_text()
        assert original.count('role<3;role++')==1
        source=original.replace('role<3;role++','role<3;role+=2')
        source='unsigned xqew_test_calls;\n'+source
        trigger='unsigned exact=xqtest_exact_jobs();assert(xqn_run(m,&device.io,batch,v,0,&stats));'
        assert trigger in source
        source=source.replace(trigger,'xqew_test_calls=0;'+trigger+'assert(xqew_test_calls>0);')
        recovery='stop_after=0;\n        for(unsigned head=0;head<3;head++)free(expected[head]);'
        assert recovery in source
        source=source.replace(recovery,'stop_after=0;\n        assert(xqn_run(m,&device.io,batch,v,0,&stats));\n        for(unsigned head=0;head<3;head++)if(bytes[head])assert(!memcmp(xqn_output(m,head,NULL),expected[head],bytes[head]));\n        for(unsigned head=0;head<3;head++)free(expected[head]);')
        fixture=out/'actual-aux-graphs.c';fixture.write_text(source,newline='\n')
        probe=out/'word-hook.h';probe.write_text('extern unsigned xqew_test_calls;\n#define XQEW_NOTE(p,c) (++xqew_test_calls)\n')
        inputs=out/'inputs';inputs.mkdir()
        for name,role,side in [('board',0,192),('classifier',2,32)]:
            count=3*side*side;raw=bytes((i*37+i//257)%127-63 & 255 for i in range(count))
            header=struct.pack('<8s8Ii',b'XQINP1\0\0',1,role,1,3,side,side,count,zlib.crc32(raw),-6)
            (inputs/(name+'.input')).write_bytes(header+raw)
        models=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models'
        for target in ['host','rv32','sanitizer']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            unit=out/('unit-'+target)
            run(target+'-unit-build',[cc,*flags,*extra,*inc,wsl_path(ROOT/'linux/picture_new/test_exact_word_input.c'),'-o',wsl_path(unit)])
            text=run(target+'-unit',prefix+[wsl_path(unit),*(['--bench'] if target!='sanitizer' else [])])
            assert 'EXACT_WORD_INPUT_BYTES_GUARDS_PASS cases=77' in text
            pairs={}
            for shape,pair,word,t in re.findall(r'WORD_PAIR shape=(\d+) pair=(\d+) word=(\d+) cpu_ns=(\d+)',text):
                pairs.setdefault(shape,{}).setdefault(int(word),[]).append(int(t))
            summary={k:dict(original_ns=v[0],word_ns=v[1],median_ratio=statistics.median(v[1])/statistics.median(v[0])) for k,v in pairs.items()}
            exe=out/('graphs-'+target)
            options=['-DXQ_FAST_REQUANT=1','-DXQ_CLASSIFIER_S16=1','-DXQ_EXACT_EPILOGUE=1',
                '-DXQ_FAST_FP32_BILINEAR=1','-DXQ_EXACT_WORD_INPUT=1','-include',wsl_path(probe)]
            run(target+'-graphs-build',[cc,*flags,*extra,*options,*inc,wsl_path(fixture),
                *[wsl_path(ROOT/p) for p in graph_sources],*wraps,'-o',wsl_path(exe)])
            text=run(target+'-graphs',prefix+[wsl_path(exe),wsl_path(models),wsl_path(inputs)],240)
            assert 'EXACT_GRAPH_ALL3_CLASSIFIER_B1_3_8_OUTPUT_CAPS_FATAL_CANCEL_PASS_NOT_BOARD' in text
            result['targets'][target]=dict(unit_cases=77,actual_frozen_aux_graphs=['board','classifier'],classifier_batches=[1,3,8],
                cpu_reference_bytes_equal=True,word_path_observed=True,old_caps_raw_compatible=True,
                ioctl_fatal_no_retry=True,cancel_invalidates=True,same_model_recovery=True,pack_only_pairs=summary)
        # Removing the storage permutation must be detected at byte granularity.
        header=(ROOT/'linux/picture_new/exact_word_input.h').read_text();assert header.count('((b&255u)<<8)')==1
        mutant=out/'wrong-channel.h';mutant.write_text(header.replace('((b&255u)<<8)','((cc&255u)<<8)'))
        exe=out/'wrong-channel'
        run('negative-build',['gcc',*flags,*inc,'-DEXACT_WORD_INPUT_HEADER="'+wsl_path(mutant)+'"',
            wsl_path(ROOT/'linux/picture_new/test_exact_word_input.c'),'-o',wsl_path(exe)])
        text=run('negative-channel',[wsl_path(exe)],codes=(6,134));assert 'memcmp' in text and 'Assertion' in text
        assert all(sha(ROOT/n)==h for n,h in before.items())
        result['status']='EXACT_WORD_INPUT_77_CASES_AUX_GRAPHS_CPU_IO_CANCEL_RECOVERY_PAIRS_PASS_NOT_BOARD'
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for target,e in result['targets'].items():
        print(target,'pack_only_ratios',{k:round(v['median_ratio'],4) for k,v in e['pack_only_pairs'].items()})


if __name__=='__main__':main()
