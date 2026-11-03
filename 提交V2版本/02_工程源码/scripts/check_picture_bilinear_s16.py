"""Bit-exact S16-parent FP32 bilinear candidate vs independent frozen arithmetic."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--full-graphs',action='store_true',help='Compare all80 layer checks and every final head against option0')
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    sources=['linux/picture_new/graph_bilinear_s16.c','linux/picture_new/test_bilinear_s16.c']
    files=sources+['linux/picture_new/graph_bilinear_s16.h','linux/picture_new/graph_tensor.h','scripts/check_picture_bilinear_s16.py']
    graph_sources=['linux/picture_new/vision32_backend.c','linux/picture_new/vision32_layer.c',
        'linux/picture_new/test_v321_mock.c','linux/picture_new/graph_runtime.c',
        'linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c','linux/picture_new/graph_profile.c',
        'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    includes=['artifacts/vision-model-20261020-adapter/runtime','linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader']
    models=ROOT/'build/picture-merge-20261023/native-models'
    inputs=ROOT/'build/picture-board-resume-20261023/synthetic-inputs-r01'
    if a.full_graphs:
        files+=graph_sources+['linux/picture_new/test_v321_golden.c','linux/picture_new/test_graph_profile.c',
            'linux/picture_new/vision32_locality.c','linux/picture_new/vision32_exact.c',
            'linux/picture_new/whole_layer_fast/vision32_layer.c',
            'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
            'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h']
        for d in includes:files += [p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h')]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={name:sha(ROOT/name) for name in files}
    fixtures={p:sha(p) for name in ['board','detector','classifier'] for p in
        [models/(name+'.xqm'),inputs/(name+'.input')]} if a.full_graphs else {}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,source_sha256=before,runs=[],full_graphs={})
    def run(name,args,seconds=120):
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        result['runs'].append(dict(name=name,exit=p.returncode))
        assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-1500:])
    try:
        for target in ['host','rv32']:
            cc='gcc' if target=='host' else '/opt/toolchain/bin/riscv32-linux-musl-gcc'
            flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off']
            if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
            binary=out/target
            run(target+'-build',[cc,*flags,'-I'+wsl_path(ROOT/'linux/picture_new'),*[wsl_path(ROOT/s) for s in sources],'-lm','-o',wsl_path(binary)])
            run(target+'-run',[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(binary)])
            assert 'BILINEAR_S16_FROZEN_FLOAT_BIT_EQUAL_PASS_NOT_BOARD' in (out/(target+'-run.log')).read_text()
            if a.full_graphs:
                checks={};heads={}
                for enabled in [0,1]:
                    for test,filename in [('golden','test_v321_golden.c'),('profile','test_graph_profile.c')]:
                        label=f'{target}-{enabled}-{test}';exe=out/label
                        run(label+'-build',[cc,*flags,'-ffunction-sections','-fdata-sections',
                            '-DXQ_INTEGER_CARRIER=1','-DXQ_CLASSIFIER_S16=1','-DXQ_FAST_REQUANT=1',
                            '-DXQ_GRAPH_PROFILE','-DXQ_NATIVE_COACH','-DXQ_FAST_FP32_BILINEAR='+str(enabled),
                            *['-I'+wsl_path(ROOT/d) for d in includes],
                            *[wsl_path(ROOT/s) for s in graph_sources+[f'linux/picture_new/{filename}']],
                            '-Wl,--wrap=ioctl,--gc-sections','-lm','-o',wsl_path(exe)])
                        args=[wsl_path(models),wsl_path(inputs)]
                        checkfile=out/(label+'-checks.txt')
                        if test=='golden':args += [wsl_path(checkfile),'--mock-v321']
                        run(label+'-run',[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),*args],300)
                        log=(out/(label+'-run.log')).read_text()
                        if test=='golden':
                            assert 'V321_MOCK_GOLDEN_PASS records=80' in log
                            checks[enabled]=checkfile.read_bytes()
                        else:
                            heads[enabled]=re.findall(r'XQG_OUTPUT model=(\w+) index=(\d+) sha256=([0-9a-f]{64})',log)
                            assert len(heads[enabled])==6
                assert checks[0]==checks[1] and heads[0]==heads[1]
                result['full_graphs'][target]=dict(all80_four_tensor_crc_sha_equal=True,all6_final_heads_sha_equal=True)
        assert all(sha(ROOT/name)==h for name,h in before.items())
        assert all(sha(p)==h for p,h in fixtures.items())
        result.update(status='BILINEAR_S16_FROZEN_FLOAT_HOST_RV32_PASS_NOT_BOARD',source_stable=True,
            exhaustive_s16_and_corner_combinations=True,exponents=[-120,-119,-112,-32,-8,-1,0,1,32,110,112],
            subpixel_rounding_added=False,float_output_kept=True,ineligible_output_untouched=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
