"""Full-graph exact epilogue vs direct CPU, old caps, fatal IO and cancellation."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--targets',choices=['host','host,qemu'],default='host,qemu')
    ap.add_argument('--timeout-seconds',type=int,default=900)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sources=['linux/picture_new/test_exact_graph.c','linux/picture_new/test_e42_model_mock.c',
             'linux/picture_new/graph_runtime.c','linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c',
             'linux/picture_new/vision32_layer.c','linux/picture_new/vision32_backend.c','linux/picture_new/graph_profile.c',
             'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
    files=set(sources+['linux/picture_new/vision32_locality.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
                       'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h','scripts/check_picture_exact_graph.py'])
    if (ROOT/'linux/picture_new/vision32_exact.c').exists():files.add('linux/picture_new/vision32_exact.c')
    for d in includes:files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={name:sha(ROOT/name) for name in sorted(files)}
    models=ROOT/'build/picture-merge-20261023/native-models'
    inputs=ROOT/'build/picture-board-resume-20261023/synthetic-inputs-r01'
    result={'status':'FAILED_PRESERVED','hardware_used':False,'source_sha256':before,'runs':[],'targets':{}}
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-ffp-contract=off',
           '-ffunction-sections','-fdata-sections','-DXQ_FAST_REQUANT=1','-DXQ_CLASSIFIER_S16=1','-DXQ_EXACT_EPILOGUE=1']

    def run(name,args,seconds):
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        result['runs'].append({'name':name,'exit':p.returncode,'timeout_seconds':seconds})
        assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2500:])
    try:
        for target in a.targets.split(','):
            cc='gcc' if target=='host' else '/opt/toolchain/bin/riscv32-linux-musl-gcc'
            extra=[] if target=='host' else ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
            binary=out/target
            run(target+'-build',[cc,*flags,*extra,*['-I'+wsl_path(ROOT/d) for d in includes],
                *[wsl_path(ROOT/p) for p in sources],'-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl',
                '-Wl,--gc-sections','-lm','-o',wsl_path(binary)],90)
            run(target+'-run',[*(['qemu-riscv32'] if target=='qemu' else []),wsl_path(binary),wsl_path(models),wsl_path(inputs)],a.timeout_seconds)
            text=(out/(target+'-run.log')).read_text()
            assert 'EXACT_GRAPH_ALL3_CLASSIFIER_B1_3_8_OUTPUT_CAPS_FATAL_CANCEL_PASS_NOT_BOARD' in text
            result['targets'][target]={'all_three_graphs_final_output_bytes_equal':True,'classifier_batches':[1,3,8],
                'old_caps_raw2_compatible':True,'ioctl_error_fatal_no_retry':True,'cancel_invalidates_output':True,'binary_sha256':sha(binary)}
        assert all(sha(ROOT/name)==h for name,h in before.items())
        result.update(status='EXACT_GRAPH_CPU_OUTPUT_CAPS_FATAL_CANCEL_HOST_RV32_PASS_NOT_BOARD',source_stable=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
