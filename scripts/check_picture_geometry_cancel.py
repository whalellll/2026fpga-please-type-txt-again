"""Real geometry cancellation, exact uninterrupted output, OOM and recovery.

Only bounded offline runs; authorized private dumps are optional. No device or
model inference. The legacy before/after-only cancellation reproducer must fail.
"""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--private-fixture',action='append',type=Path,default=[]);a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    includes=['linux/picture_new','artifacts/vision-model-20261020-adapter/runtime','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader']
    files=['scripts/generate_picture_geometry_cancel.py','scripts/check_picture_geometry_cancel.py',
        'linux/picture_new/geometry_locality.c','linux/picture_new/geometry_mask.h','linux/picture_new/geometry_cancel.h',
        'linux/picture_new/geometry_exact.h','linux/picture_new/coach_geometry.c','linux/picture_new/coach_geometry.h',
        'linux/picture_new/test_geometry_cancel.c','linux/picture_new/test_geometry_cancel_fixture.c',
        'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
    before={q:sha(ROOT/q) for q in files};private={workspace_path(q):sha(workspace_path(q)) for q in a.private_fixture}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,sources_sha256=before,checks=[],private_fixtures=len(private))
    def run(name,args,seconds=180,expected=(0,)):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert r.returncode in expected,(name,r.returncode,text[-2000:]);return text
    try:
        generated=out/'geometry-cancellable.c'
        run('generate',['python3',wsl_path(ROOT/'scripts/generate_picture_geometry_cancel.py'),'--output',wsl_path(generated)])
        inc=['-I'+wsl_path(ROOT/q) for q in includes]
        base=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections',
            '-DXQ_GEOMETRY_FAST=1','-DXQ_GEOMETRY_ARITH=1','-DXQ_GEOMETRY_COMPACT=1','-DXQ_GEOMETRY_SELECTIVE=1','-DXQ_GEOMETRY_SEED_BOUND=1','-DXQ_GEOMETRY_GRAY_TABLE=1']
        rng=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models/refinement_rng.bin'
        reference=None
        for target in ['host','rv32','sanitizers']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizers':extra=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            for flag in [0,1]:
                name=target+'-'+str(flag);exe=out/(name+'-unit')
                flags=base+extra+['-DXQ_GEOMETRY_CANCEL='+str(flag),'-DGEOMETRY_SOURCE="'+wsl_path(ROOT/'linux/picture_new/coach_geometry.c')+'"']
                if flag:flags+=['-DXQ_GEOMETRY_CANCEL_SOURCE="'+wsl_path(generated)+'"']
                run(name+'-build',[cc,*flags,*inc,wsl_path(ROOT/'linux/picture_new/test_geometry_cancel.c'),
                    wsl_path(ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c'),wsl_path(ROOT/'sw/bootloader/crc32_fast.c'),
                    '-Wl,--wrap=malloc,--wrap=calloc,--wrap=free,--gc-sections','-lm','-o',wsl_path(exe)])
                text=run(name+'-reference',prefix+[wsl_path(exe),wsl_path(rng),'--reference'])
                bits=[line for line in text.splitlines() if line.startswith('GEOMETRY_CANCEL_BITS')];assert len(bits)==1
                if reference is None:reference=bits[0]
                assert reference==bits[0],(target,flag,'uninterrupted bits differ')
                if flag:
                    text=run(name+'-cancel',prefix+[wsl_path(exe),wsl_path(rng),'--check'])
                    assert 'GEOMETRY_REAL_CANCEL_13_PHASES_OOM_RECOVERY_EXACT_PASS_NOT_BOARD' in text
                elif target=='host':
                    text=run(name+'-negative-boundary',prefix+[wsl_path(exe),wsl_path(rng),'--check'],expected=(6,134))
                    assert 'allocations_after_cancel=2' in text
                if private:
                    fixture=out/(name+'-fixture')
                    run(name+'-fixture-build',[cc,*flags,*inc,wsl_path(ROOT/'linux/picture_new/test_geometry_cancel_fixture.c'),
                        wsl_path(ROOT/'linux/picture_new/coach_geometry.c'),wsl_path(ROOT/'sw/bootloader/crc32_fast.c'),'-Wl,--gc-sections','-lm','-o',wsl_path(fixture)])
                    for i,q in enumerate(private):run(name+'-private-'+str(i),prefix+[wsl_path(fixture),wsl_path(q),wsl_path(out/(name+'-private-'+str(i)+'.bin'))])
                result['checks'].append(dict(target=target,flag=flag,reference_bits_equal=True,real_cancel_oom_recovery_pass=bool(flag)))
            for i in range(len(private)):
                assert (out/(target+'-0-private-'+str(i)+'.bin')).read_bytes()==(out/(target+'-1-private-'+str(i)+'.bin')).read_bytes()
        assert before=={q:sha(ROOT/q) for q in before}
        assert all(sha(q)==h for q,h in private.items())
        result.update(status='REAL_GEOMETRY_CANCEL_HOST_RV32_SANITIZERS_EXACT_OOM_RECOVERY_PASS_NOT_BOARD',source_stable=True,
            legacy_boundary_negative_rejected=True,no_new_allocations_or_shared_state=True,private_uninterrupted_status_corners_stats_equal=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
