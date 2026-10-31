"""Bounded frozen board/classifier synthetic profile; exact device is mocked."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--word-input',action='store_true')
    ap.add_argument('--word-output',action='store_true')
    a=ap.parse_args();out=workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(exist_ok=False)
    sources=['linux/picture_new/test_aux_profile.c','linux/picture_new/test_e42_model_mock.c',
        'linux/picture_new/graph_runtime.c','linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c',
        'linux/picture_new/vision32_layer.c','linux/picture_new/vision32_backend.c','linux/picture_new/graph_profile.c',
        'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
    files=set(sources+['linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
        'linux/picture_new/graph_bilinear_s16.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
        'scripts/diagnose_picture_aux_prepare.py'])
    for folder in includes:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={name:sha(ROOT/name) for name in sorted(files)}
    models=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models'
    result=dict(status='FAILED_PRESERVED',hardware_used=False,synthetic_only=True,
        exact_word_input=a.word_input,exact_word_output=a.word_output,source_sha256=before,model_sha256={n:sha(models/n) for n in ['board.xqm','classifier.xqm']},targets={})
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-ffp-contract=off',
        '-ffunction-sections','-fdata-sections','-DXQ_NATIVE_COACH','-DXQ_GRAPH_PROFILE','-DXQ_FAST_REQUANT=1',
        '-DXQ_CLASSIFIER_S16=1','-DXQ_EXACT_EPILOGUE=1','-DXQ_FAST_FP32_BILINEAR=1','-DXQ_BOARD_CORNER_TABLE=1']
    flags += ['-DXQ_EXACT_WORD_INPUT='+str(int(a.word_input))]
    flags += ['-DXQ_EXACT_WORD_OUTPUT='+str(int(a.word_output))]
    def run(name,args,seconds):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-1500:])
        return (out/(name+'.log')).read_text()
    try:
        for target in ['host','rv32']:
            cc='gcc' if target=='host' else '/opt/toolchain/bin/riscv32-linux-musl-gcc'
            extra=[] if target=='host' else ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
            exe=out/target
            run(target+'-build',[cc,*flags,*extra,*['-I'+wsl_path(ROOT/d) for d in includes],
                *[wsl_path(ROOT/p) for p in sources],'-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl',
                '-Wl,--gc-sections','-lm','-o',wsl_path(exe)],90)
            text=run(target+'-run',*[[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),wsl_path(models)]],240)
            assert 'AUX_FROZEN_PROFILE_COMPLETE_NOT_BOARD' in text
            entries={}
            for line in text.splitlines():
                if line.startswith(('AUX_PREPARE ','AUX_PHASE ','AUX_OUTPUT ')):
                    tag,*words=line.split();fields=dict(w.split('=',1) for w in words);name=fields.pop('name')
                    e=entries.setdefault(name,dict(phases={},output_sha256={}))
                    if tag=='AUX_PREPARE':e.update({k:int(v) for k,v in fields.items()})
                    elif tag=='AUX_PHASE':e['phases'][fields.pop('phase')]={k:int(v) for k,v in fields.items()}
                    else:e['output_sha256'][fields['head']]=fields['sha256']
            assert set(entries)=={'board','classifier'}
            result['targets'][target]=entries
        assert all(result['targets']['host'][name]['output_sha256']==result['targets']['rv32'][name]['output_sha256'] for name in ['board','classifier'])
        assert all(sha(ROOT/n)==h for n,h in before.items())
        result['status']='AUX_FROZEN_EXACT_PROFILE_HOST_RV32_HEADS_EQUAL_NOT_BOARD'
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    for target,entries in result['targets'].items():
        for name,e in entries.items():
            stages=sorted([(int(k),v['cpu_ns']/1e6) for k,v in e['phases'].items() if int(k)!=16],key=lambda x:-x[1])
            print(target,name,'normalize_ms',round(e['normalize_cpu_ns']/1e6,3),'top_cpu_phases_ms',stages[:5])


if __name__=='__main__':main()
