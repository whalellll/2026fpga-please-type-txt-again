"""Synthetic perspective/occlusion/corner-bias controls and exact fused replay."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import subprocess

from diagnose_picture_geometry import HARNESS
from generate_picture_geometry_fused import generate
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True,exist_ok=False);fixtures=out/'fixtures';fixtures.mkdir()
    source=ROOT/'linux/picture_new/geometry_locality.c'
    fused=out/'geometry-fused.c';generate(ROOT,source,fused)
    harness=out/'fixture.c';harness.write_text(HARNESS,newline='\n')
    files=[source,ROOT/'linux/picture_new/test_geometry_correspondence.c',ROOT/'scripts/generate_picture_geometry_fused.py',
        ROOT/'scripts/diagnose_picture_geometry.py',Path(__file__).resolve(),ROOT/'linux/picture_new/geometry_exact.h',
        ROOT/'linux/picture_new/geometry_mask.h',ROOT/'sw/bootloader/crc32_fast.c']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={p:sha(p) for p in files}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,synthetic_inputs_only=True,
        production_sources_unchanged=True,source_sha256={p.relative_to(ROOT).as_posix():h for p,h in before.items()},
        controls=[],checks=[])

    def run(name,args):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 60 '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=75)
        text=(out/(name+'.log')).read_text(errors='replace');assert not p.returncode,(name,p.returncode,text[-2000:]);return text

    try:
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
        flags+=['-I'+wsl_path(ROOT/p) for p in includes]
        flags+=['-D'+name+'=1' for name in ['XQ_GEOMETRY_GRAY_TABLE','XQ_GEOMETRY_FAST','XQ_GEOMETRY_ARITH',
            'XQ_GEOMETRY_COMPACT','XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND']]
        maker=out/'make-controls'
        run('make-build',['cc',*flags,'-DGEOMETRY_SOURCE="'+wsl_path(source)+'"',wsl_path(files[1]),
            wsl_path(files[-1]),'-Wl,--gc-sections','-lm','-o',wsl_path(maker)])
        text=run('make-controls',[wsl_path(maker),wsl_path(ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models/refinement_rng.bin'),wsl_path(fixtures)])
        for name,okay,crossings,inliers,error in re.findall(r'GEOMETRY_CORRESPONDENCE case=(\S+) okay=(\d+) crossings=(\d+) inliers=(\d+) truth_error_grid=(\S+)',text):
            result['controls'].append(dict(case=name,okay=int(okay),crossings=int(crossings),inliers=int(inliers),
                truth_error_grid_units=float(error) if int(okay) else None))
        assert len(result['controls'])==8
        for target in ['host','rv32']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            prefix=['qemu-riscv32'] if target=='rv32' else []
            for variant,path in [('baseline',source),('fused',fused)]:
                exe=out/(target+'-'+variant)
                run(target+'-'+variant+'-build',[cc,*flags,*extra,*(['-DXQ_GEOMETRY_FUSED=1'] if variant=='fused' else []),
                    '-DDIAG_SOURCE="'+wsl_path(path)+'"',wsl_path(harness),wsl_path(files[-1]),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
                for row in result['controls']:
                    case=row['case']
                    run(target+'-'+variant+'-'+case,prefix+[wsl_path(exe),wsl_path(fixtures/(case+'.bin')),
                        wsl_path(out/(target+'-'+variant+'-'+case+'.bin')),'-','fast'])
            for row in result['controls']:
                case=row['case']
                assert (out/(target+'-baseline-'+case+'.bin')).read_bytes()==(out/(target+'-fused-'+case+'.bin')).read_bytes()
                result['checks'].append(dict(target=target,case=case,full_status_corners_statistics_bits_equal=True))
        assert all(sha(p)==h for p,h in before.items())
        result.update(status='SYNTHETIC_CORRESPONDENCE_EIGHT_CONTROLS_FUSED_BITS_PASS_NOT_BOARD',
            frozen_algorithm_quality_limits_preserved=True,real_failed_frame_not_fixed=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
