"""Frozen first-layer narrow-column candidate: exact offline checks only."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path
HWC='linux/picture_new/hwc_fast'
RUNTIME='artifacts/vision-model-20261020-adapter/runtime'
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--kit',type=Path,default=ROOT/'build/hwc-acceptance-kit')
    ap.add_argument('--unit-only',action='store_true');a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    kit=workspace_path(a.kit);expected=json.loads((kit/'expected.json').read_text())
    assert sha(kit/'models/detector.xqm')=='d65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'
    assert sha(kit/'models/detector.xqi')=='d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    provider=(ROOT/HWC/'integer_hwc.c').read_text();candidate=(ROOT/HWC/'tail_columns.h').read_text()
    original=provider.split('int xi8_run(',1)[1].split('size_t xi8_output_elements(',1)[0]
    original='int xi8_run('+original
    coordinator=candidate.split('/* XQIH_TAIL_COORDINATOR_BEGIN */\n',1)[1].split('/* XQIH_TAIL_COORDINATOR_END */',1)[0]
    restored=coordinator.replace('static int xqih_run_tail(','int xi8_run(').replace('!xqih_convolution_tail(','!convolution(')
    assert restored.strip()==original.strip(),'provider coordinator drift'
    common=[HWC+'/adapter.c',HWC+'/tests/picture_new_graph_mock.c','linux/picture_new/graph_runtime.c',
        'linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c','linux/picture_new/graph_profile.c',
        'linux/picture_new/vision32_layer.c','linux/picture_new/vision32_backend.c',RUNTIME+'/xq_sha256.c','sw/bootloader/crc32_fast.c']
    includes=[HWC,RUNTIME,'linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader']
    files=set(common+[HWC+'/tail_columns.h',HWC+'/integer_hwc.c',HWC+'/integer_hwc.h',HWC+'/tests/test_tail_columns.c',
        HWC+'/tests/product_adapter.c','scripts/check_picture_hwc_tail_columns.py','linux/picture_new/vision32_locality.c',
        'linux/picture_new/vision32_exact.c','linux/picture_new/whole_layer_fast/vision32_layer.c','linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c'])
    for d in includes:files.update(q.relative_to(ROOT).as_posix() for q in (ROOT/d).glob('*.h'))
    before={q:sha(ROOT/q) for q in sorted(files)}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,models_changed=False,source_sha256=before,
        provider_coordinator_unchanged_except_dispatch=True,unit_checks=[],full_heads_checks=[])
    def run(name,args,seconds=120,allowed=(0,)):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert r.returncode in allowed,(name,r.returncode,(out/(name+'.log')).read_text(errors='replace')[-2000:])
        return (out/(name+'.log')).read_text(errors='replace')
    def build(name,target,src,extra):
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizers':flags+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
        exe=out/name
        run(name+'-build',[cc,*flags,*['-I'+wsl_path(ROOT/q) for q in includes],*extra,*[wsl_path(ROOT/q) for q in src],'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
        return exe
    try:
        for target in ['host','rv32','sanitizers']:
            prefix=['qemu-riscv32'] if target=='rv32' else []
            exe=build(target+'-unit',target,[HWC+'/tests/test_tail_columns.c'],[])
            text=run(target+'-unit',[*prefix,wsl_path(exe)],180)
            assert 'HWC_TAIL_32_TO_18_COVERAGE_HALO_BYTES_PARAMETER_LEASE_S8_S16_CANCEL_IO_RECOVERY_PASS_NOT_BOARD' in text
            result['unit_checks'].append(dict(target=target,first_layer_jobs_before=32,after=18,exact_coverage_halo_lease_s8_s16_and_faults=True))
        if not a.unit_only:
            for target,cases in [('host',['fixed','zero','signed']),('rv32',['fixed']),('sanitizers',['fixed'])]:
                prefix=['qemu-riscv32'] if target=='rv32' else []
                flags=['-DXQ_HWC_DETECTOR=1','-DXQ_CLASSIFIER_S16=1','-DXQ_FAST_REQUANT=1','-DXQ_HWC_WORD_INPUT=1',
                    '-DXQ_HWC_RGB8_DIRECT=1','-DXQ_HWC_TAIL_COLUMNS=1','-DXQIH_EXPECTED_JOBS=152',
                    '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl,--wrap=malloc,--wrap=calloc']
                exe=build(target+'-product',target,[HWC+'/tests/product_adapter.c',*common],flags)
                for case in cases:
                    dest=out/(target+'-'+case+'.heads.f32')
                    text=run(target+'-'+case,[*prefix,wsl_path(exe),wsl_path(kit/'models/detector.xqm'),wsl_path(kit/('synthetic/'+case+'.f32')),wsl_path(dest)],900)
                    assert 'HWC_PRODUCT_BOUNDARY_NO_CPU_FALLBACK_NO_RAW2_OBSERVER_OOM_CANCEL_IOCTL_INVALIDATE_PASS' in text
                    assert sha(dest)==expected['cases'][case]['output_sha256'],(target,case,'heads differ')
                    result['full_heads_checks'].append(dict(target=target,case=case,jobs=152,three_heads_equal_frozen_cpu=True))
        assert before=={q:sha(ROOT/q) for q in before}
        result.update(status='TAIL_COLUMNS_UNITS_PASS_FULL_HEADS_NOT_RUN' if a.unit_only else 'TAIL_COLUMNS_HOST_RV32_SANITIZERS_FULL_HEADS_PASS_NOT_BOARD',source_stable=True,default_selected=False,board_latency_accepted=False)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
