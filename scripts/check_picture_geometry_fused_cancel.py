"""Real 13-phase cancellation/OOM/recovery and fused geometry allocation proof."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import subprocess

from generate_picture_geometry_cancel import generate as cancel_generate
from generate_picture_geometry_fused import generate as fused_generate
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--private-fixture',required=True,action='append',type=Path)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True,exist_ok=False)
    original=ROOT/'linux/picture_new/geometry_locality.c'
    cancel_source=out/'geometry-cancellable.c';cancel_generate(ROOT,cancel_source)
    # The cancellable generator is also callable from Windows; normalize its
    # absolute training-reference include to the path used by the WSL compiler.
    source=cancel_source.read_text();windows=(ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c').as_posix()
    source=source.replace('"'+windows+'"','"'+wsl_path(ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c')+'"')
    normalized=out/'geometry-cancellable-wsl.c';normalized.write_text(source,newline='\n')
    fused=out/'geometry-fused-cancellable.c';overlay=fused_generate(ROOT,normalized,fused)
    plain_fused=out/'geometry-fused.c';fused_generate(ROOT,original,plain_fused)
    fixtures=[workspace_path(p) for p in a.private_fixture]
    files=[original,ROOT/'scripts/generate_picture_geometry_cancel.py',ROOT/'scripts/generate_picture_geometry_fused.py',
        Path(__file__).resolve(),ROOT/'linux/picture_new/test_geometry_cancel.c',ROOT/'linux/picture_new/test_geometry_cancel_fixture.c',
        ROOT/'linux/picture_new/test_geometry_fused_memory.c',ROOT/'linux/picture_new/geometry_cancel.h',
        ROOT/'linux/picture_new/geometry_exact.h',ROOT/'linux/picture_new/geometry_mask.h',
        ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c',ROOT/'sw/bootloader/crc32_fast.c']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p:sha(p) for p in files};private_before={p:sha(p) for p in fixtures}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,overlay=overlay,checks=[],memory=[],
        source_sha256={p.relative_to(ROOT).as_posix():h for p,h in before.items()})

    def run(name,args,seconds=90):
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(seconds)+' '+shlex.join(args)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+15)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert not p.returncode,(name,p.returncode,text[-2000:]);return text
    try:
        includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader',
                  'artifacts/vision-model-20261020-adapter/runtime']
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        flags+=['-I'+wsl_path(ROOT/p) for p in includes]
        flags+=['-D'+name+'=1' for name in ['XQ_GEOMETRY_GRAY_TABLE','XQ_GEOMETRY_FAST','XQ_GEOMETRY_ARITH',
            'XQ_GEOMETRY_COMPACT','XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND']]
        rng=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models/refinement_rng.bin'
        reference=None
        for target in ['host','rv32','sanitizers']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizers':extra=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            for flag in [0,1]:
                name=target+'-'+str(flag);exe=out/(name+'-unit')
                path=fused if flag else original
                defs=['-DXQ_GEOMETRY_CANCEL='+str(flag),'-DXQ_GEOMETRY_FUSED='+str(flag),
                      '-DGEOMETRY_SOURCE="'+wsl_path(path)+'"']
                run(name+'-build',[cc,*flags,*extra,*defs,wsl_path(ROOT/'linux/picture_new/test_geometry_cancel.c'),
                    wsl_path(files[-2]),wsl_path(files[-1]),'-Wl,--wrap=malloc,--wrap=calloc,--wrap=free,--gc-sections','-lm','-o',wsl_path(exe)])
                text=run(name+'-reference',prefix+[wsl_path(exe),wsl_path(rng),'--reference'])
                bits=next(line for line in text.splitlines() if line.startswith('GEOMETRY_CANCEL_BITS'))
                if reference is None:reference=bits
                assert bits==reference
                if flag:
                    assert 'GEOMETRY_REAL_CANCEL_13_PHASES_OOM_RECOVERY_EXACT_PASS_NOT_BOARD' in run(name+'-check',prefix+[wsl_path(exe),wsl_path(rng),'--check'])
                fixture=out/(name+'-fixture')
                run(name+'-fixture-build',[cc,*flags,*extra,'-DXQ_GEOMETRY_CANCEL='+str(flag),
                    '-DXQ_GEOMETRY_FUSED='+str(flag),wsl_path(ROOT/'linux/picture_new/test_geometry_cancel_fixture.c'),
                    wsl_path(path),wsl_path(files[-1]),'-Wl,--gc-sections','-lm','-o',wsl_path(fixture)])
                for i,p in enumerate(fixtures):run(name+'-private-'+str(i),prefix+[wsl_path(fixture),wsl_path(p),wsl_path(out/(name+'-private-'+str(i)+'.bin'))])
            for i in range(len(fixtures)):
                assert (out/(target+'-0-private-'+str(i)+'.bin')).read_bytes()==(out/(target+'-1-private-'+str(i)+'.bin')).read_bytes()
            result['checks'].append(dict(target=target,reference_bits_equal=True,real_13_phase_cancel_oom_recovery=True,
                private_fixtures_bits_equal=len(fixtures)))
            if target=='sanitizers':continue
            memory=[]
            for variant,path in [('baseline',original),('fused',plain_fused)]:
                binary=out/(target+'-memory-'+variant)
                run(target+'-memory-'+variant+'-build',[cc,*flags,*extra,*(['-DXQ_GEOMETRY_FUSED=1'] if variant=='fused' else []),
                    '-DGEOMETRY_SOURCE="'+wsl_path(path)+'"',wsl_path(ROOT/'linux/picture_new/test_geometry_fused_memory.c'),
                    wsl_path(files[-1]),'-Wl,--wrap=malloc,--wrap=calloc,--wrap=free,--gc-sections','-lm','-o',wsl_path(binary)])
                samples=[]
                for i,p in enumerate(fixtures):
                    text=run(target+'-memory-'+variant+'-'+str(i),prefix+[wsl_path(binary),wsl_path(p),wsl_path(out/(target+'-memory-'+variant+'-'+str(i)+'.bin'))])
                    samples.append({k:int(v) for k,v in re.findall(r'(allocations|total|peak|first|live)=(\d+)',text)})
                memory.append(samples)
            for i,(b,c) in enumerate(zip(*memory)):
                assert (out/(target+'-memory-baseline-'+str(i)+'.bin')).read_bytes()==(out/(target+'-memory-fused-'+str(i)+'.bin')).read_bytes()
                assert b['allocations']==c['allocations']+1 and b['total']-c['total']==b['first']==c['first']
                assert b['peak']-c['peak']==b['first'] and b['live']==c['live']==0
                result['memory'].append(dict(target=target,case=i,baseline=b,fused=c,saved_bytes=b['first']))
        assert all(sha(p)==h for p,h in before.items()) and all(sha(p)==h for p,h in private_before.items())
        result.update(status='GEOMETRY_FUSED_CANCEL_13_PHASE_OOM_MEMORY_FULL_BITS_PASS_NOT_BOARD',
            production_sources_and_private_inputs_stable=True,no_global_cancellation_state=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
