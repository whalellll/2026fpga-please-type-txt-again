"""Bounded binary64 min numeric, full-array, paired and cancellation checks.

Private saved geometry inputs and result bytes stay in the explicit E build
junction. Same fused baseline on both sides; timing never models board DDR.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import subprocess

from generate_picture_geometry_cancel import generate as cancel_generate
from generate_picture_geometry_fused import generate as fused_generate
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--stage',choices=['numeric','pairs','cancel'],required=True)
    ap.add_argument('--targets',default='host,rv32,sanitizers')
    ap.add_argument('--negative-only',action='store_true',help='Reuse numeric proofs after a harness-only failure')
    ap.add_argument('--private-fixture',type=Path,action='append',default=[])
    args=ap.parse_args()
    assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True,exist_ok=False)
    targets=args.targets.split(',');assert set(targets)<=set(['host','rv32','sanitizers'])
    assert not args.negative_only or args.stage=='numeric'
    coach=ROOT/'linux/picture_new'
    sources=[coach/p for p in ['geometry_exact.h','geometry_min_bits.h','geometry_locality.c',
        'test_geometry_min_bits.c','test_geometry_fused.c','test_geometry_pair.c','test_geometry_cancel.c']]
    sources += [Path(__file__).resolve(),ROOT/'scripts/generate_picture_geometry_fused.py',
        ROOT/'scripts/generate_picture_geometry_cancel.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p:sha(p) for p in sources}
    fixtures=[workspace_path(p) for p in args.private_fixture]
    private_before={p:sha(p) for p in fixtures}
    result=dict(status='FAILED_PRESERVED',stage=args.stage,hardware_used=False,checks=[],pairs=[],
        source_sha256={p.relative_to(ROOT).as_posix():h for p,h in before.items()},
        fixtures_sha256=list(private_before.values()),cancellation_disabled_for_timing=True,
        no_board_or_product_latency_claim=True)
    def run(name,argv,expected=(0,),seconds=60):
        with (out/(name+'.log')).open('xb') as log:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+15)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert p.returncode in expected,(name,p.returncode,text[-2000:])
        return text
    try:
        includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader',
            'artifacts/vision-model-20261020-adapter/runtime']
        flags=['-std=c11','-D_POSIX_C_SOURCE=200809L','-O2','-Wall','-Wextra','-Werror',
            '-ffp-contract=off','-ffunction-sections','-fdata-sections']+['-I'+wsl_path(ROOT/p) for p in includes]
        options=['-D'+p+'=1' for p in ['XQ_GEOMETRY_GRAY_TABLE','XQ_GEOMETRY_FAST',
            'XQ_GEOMETRY_ARITH','XQ_GEOMETRY_COMPACT','XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND','XQ_GEOMETRY_FUSED']]
        if args.stage=='numeric':flags+=['-Wno-unused-function']
        crc=ROOT/'sw/bootloader/crc32_fast.c'
        geometry=out/'geometry-fused.c'
        if args.stage!='numeric':
            source=coach/'geometry_locality.c'
            if args.stage=='cancel':
                raw=out/'geometry-cancel.c';cancel_generate(ROOT,raw)
                source=out/'geometry-cancel-wsl.c'
                reference=ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c'
                source.write_text(raw.read_text().replace(reference.as_posix(),wsl_path(reference)),newline='\n')
                options+=['-DXQ_GEOMETRY_CANCEL=1']
            result['overlay']=fused_generate(ROOT,source,geometry)
        reference_bits=None
        for target in ([] if args.negative_only else targets):
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizers':extra=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            if args.stage=='numeric':
                for flag in [0,1]:
                    name=target+'-'+str(flag);exe=out/name
                    run(name+'-build',[cc,*flags,*extra,'-DXQ_GEOMETRY_MIN_BITS='+str(flag),
                        wsl_path(coach/'test_geometry_min_bits.c'),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
                    text=run(name,prefix+[wsl_path(exe)])
                    row=re.search(r'NUMERIC_PASS cases=(\d+) flag=(\d)',text);assert row
                    result['checks'].append(dict(target=target,flag=flag,cases=int(row[1])))
            elif args.stage=='pairs':
                assert fixtures
                exe=out/(target+'-arrays')
                run(target+'-arrays-build',[cc,*flags,*extra,*options,'-DXQ_GEOMETRY_MIN_BITS=1',
                    '-DGEOMETRY_SOURCE="'+wsl_path(geometry)+'"',wsl_path(coach/'test_geometry_fused.c'),
                    wsl_path(crc),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
                assert '18_SHAPES_MASKS_ALL_THREE_ARRAYS_ALIAS_EXACT_PASS' in run(target+'-arrays',prefix+[wsl_path(exe)])
                objects=[]
                for flag,variant in [(0,'baseline'),(1,'candidate')]:
                    obj=out/(target+'-'+variant+'.o');objects.append(obj)
                    renamed=['-Dxnp_'+n+'='+variant+'_'+n for n in ['filter_candidates','load_rng','coarse','refine','refine_full','finish']]
                    renamed+=['-Dxq_training_geometry_cli='+variant+'_training_cli']
                    run(target+'-'+variant+'-build',[cc,*flags,*extra,*options,*renamed,'-DXQ_GEOMETRY_MIN_BITS='+str(flag),
                        '-c',wsl_path(geometry),'-o',wsl_path(obj)])
                exe=out/(target+'-pair')
                run(target+'-pair-build',[cc,*flags,*extra,wsl_path(coach/'test_geometry_pair.c'),
                    *[wsl_path(p) for p in objects],wsl_path(crc),'-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
                for i,fixture in enumerate(fixtures):
                    text=run(target+'-pair-'+str(i),prefix+[wsl_path(exe),wsl_path(fixture)])
                    assert 'GEOMETRY_PAIR_FULL_CORNERS_STATISTICS_EQUAL' in text
                    samples={0:[],1:[]}
                    for v,cpu,wall in re.findall(r'GEOMETRY_PAIR_NS repeat=\d+ variant=(\d+) cpu=(\d+) wall=(\d+)',text):samples[int(v)].append(int(cpu))
                    assert all(len(v)==4 for v in samples.values())
                    result['pairs'].append(dict(target=target,case=i,cpu_samples_ns=samples,
                        median_cpu_ratio=statistics.median(samples[1])/statistics.median(samples[0]),
                        full_status_corners_stats_bits_equal=True,sanitizer_not_ranked=target=='sanitizers'))
                for kind in ['corner','stats']:
                    assert 'GEOMETRY_PAIR_MISMATCH kind=' in run(target+'-negative-'+kind,
                        prefix+[wsl_path(exe),wsl_path(fixtures[0]),'--negative-'+kind],expected=(3,))
                result['checks'].append(dict(target=target,three_full_arrays=18,aliases=True,corner_and_stats_negatives=True))
            else:
                for flag in [0,1]:
                    name=target+'-'+str(flag);exe=out/name
                    run(name+'-build',[cc,*flags,*extra,*options,'-DXQ_GEOMETRY_MIN_BITS='+str(flag),
                        '-DGEOMETRY_SOURCE="'+wsl_path(geometry)+'"',wsl_path(coach/'test_geometry_cancel.c'),
                        wsl_path(ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c'),wsl_path(crc),
                        '-Wl,--wrap=malloc,--wrap=calloc,--wrap=free,--gc-sections','-lm','-o',wsl_path(exe)])
                    rng=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models/refinement_rng.bin'
                    text=run(name+'-reference',prefix+[wsl_path(exe),wsl_path(rng),'--reference'])
                    bits=next(line for line in text.splitlines() if line.startswith('GEOMETRY_CANCEL_BITS'))
                    if reference_bits is None:reference_bits=bits
                    assert bits==reference_bits
                    if flag:assert 'GEOMETRY_REAL_CANCEL_13_PHASES_OOM_RECOVERY_EXACT_PASS' in run(name+'-check',prefix+[wsl_path(exe),wsl_path(rng),'--check'])
                result['checks'].append(dict(target=target,reference_bits_equal=True,real_cancel_13_phases_oom_recovery=True))
        if args.stage=='numeric':
            mutant=out/'geometry-min-mutant.h'
            text=(coach/'geometry_min_bits.h').read_text()
            assert text.count('return x<y?a:b;')==1
            mutant.write_text(text.replace('return x<y?a:b;','return x>y?a:b;'),newline='\n')
            unit=out/'negative-test.c'
            unit.write_text((coach/'test_geometry_min_bits.c').read_text().replace('"geometry_min_bits.h"','"'+wsl_path(mutant)+'"'),newline='\n')
            exe=out/'negative'
            run('negative-build',['cc',*flags,'-DXQ_GEOMETRY_MIN_BITS=1',wsl_path(unit),
                '-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
            assert 'MIN_BITS_MISMATCH' in run('negative',[wsl_path(exe)],expected=(3,))
            result['negative_wrong_selection_rejected']=True
        assert all(sha(p)==h for p,h in before.items()) and all(sha(p)==h for p,h in private_before.items())
        result.update(status='GEOMETRY_MIN_BITS_'+args.stage.upper()+'_PASS_NOT_BOARD',sources_and_private_inputs_stable=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
