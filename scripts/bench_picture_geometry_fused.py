"""Exact fused geometry arrays plus same-process alternating saved-input pairs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import subprocess

from generate_picture_geometry_fused import generate
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--private-fixture',required=True,type=Path,action='append')
    parser.add_argument('--targets',choices=['host','host,rv32','host,rv32,sanitizers'],default='host,rv32,sanitizers')
    args = parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'linux/picture_new/geometry_locality.c'
    unit=ROOT/'linux/picture_new/test_geometry_fused.c'
    pair=ROOT/'linux/picture_new/test_geometry_pair.c'
    files=[source,unit,pair,ROOT/'scripts/generate_picture_geometry_fused.py',Path(__file__).resolve(),
        ROOT/'linux/picture_new/geometry_exact.h',ROOT/'linux/picture_new/geometry_mask.h',
        ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c',ROOT/'sw/bootloader/crc32_fast.c']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p:sha(p) for p in files}
    fixtures=[workspace_path(p) for p in args.private_fixture]
    private_before={p:sha(p) for p in fixtures}
    generated=out/'geometry-fused.c';overlay=generate(ROOT,source,generated)
    result=dict(status='FAILED_PRESERVED',hardware_used=False,production_sources_unchanged=True,
        sources_sha256={p.relative_to(ROOT).as_posix():h for p,h in before.items()},
        overlay=overlay,unit_checks=[],pairs=[],warmup_both=True,alternating_four_pairs=True,
        cancellation_enabled_for_timing=False,device_or_board_latency=False)

    def run(name,argv,expected=(0,),seconds=90):
        with (out/(name+'.log')).open('xb') as f:
            proc=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(seconds)+' '+shlex.join(argv)],
                stdout=f,stderr=subprocess.STDOUT,timeout=seconds+15)
        text=(out/(name+'.log')).read_text(errors='replace')
        assert proc.returncode in expected,(name,proc.returncode,text[-2000:])
        return text

    try:
        includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader',
                  'artifacts/vision-model-20261020-adapter/runtime']
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        flags+=['-I'+wsl_path(ROOT/p) for p in includes]
        options=['-D'+name+'=1' for name in ['XQ_GEOMETRY_GRAY_TABLE','XQ_GEOMETRY_FAST',
            'XQ_GEOMETRY_ARITH','XQ_GEOMETRY_COMPACT','XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND']]
        for target in args.targets.split(','):
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizers':extra=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            binary=out/(target+'-unit')
            run(target+'-unit-build',[cc,*flags,*extra,*options,'-DXQ_GEOMETRY_FUSED=1',
                '-DGEOMETRY_SOURCE="'+wsl_path(generated)+'"',wsl_path(unit),wsl_path(files[-1]),
                '-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            assert 'GEOMETRY_FUSED_18_SHAPES_MASKS_ALL_THREE_ARRAYS_ALIAS_EXACT_PASS_NOT_BOARD' in run(target+'-unit',prefix+[wsl_path(binary)])
            result['unit_checks'].append(dict(target=target,cases=18,three_full_arrays_and_alias_bits_equal=True))
            objects=[]
            for variant,path in [('baseline',source),('candidate',generated)]:
                renamed=['-Dxnp_'+name+'='+variant+'_'+name for name in ['filter_candidates','load_rng','coarse','refine','refine_full','finish']]
                renamed+=['-Dxq_training_geometry_cli='+variant+'_training_cli']
                obj=out/(target+'-'+variant+'.o');objects.append(obj)
                run(target+'-'+variant+'-build',[cc,*flags,*extra,*options,*renamed,
                    *(['-DXQ_GEOMETRY_FUSED=1'] if variant=='candidate' else []),'-c',wsl_path(path),'-o',wsl_path(obj)])
            binary=out/(target+'-pair')
            run(target+'-pair-build',[cc,*flags,*extra,wsl_path(pair),*[wsl_path(p) for p in objects],
                wsl_path(files[-1]),'-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            for i,fixture in enumerate(fixtures):
                text=run(target+'-pair-'+str(i),prefix+[wsl_path(binary),wsl_path(fixture)])
                assert 'GEOMETRY_PAIR_FULL_CORNERS_STATISTICS_EQUAL' in text
                samples={0:[],1:[]}
                for v,cpu,wall in re.findall(r'GEOMETRY_PAIR_NS repeat=\d+ variant=(\d+) cpu=(\d+) wall=(\d+)',text):samples[int(v)].append(int(cpu))
                assert all(len(v)==4 for v in samples.values())
                result['pairs'].append(dict(target=target,case=i,full_status_corners_stats_bits_equal=True,
                    cpu_samples_ns=samples,median_cpu_ratio=statistics.median(samples[1])/statistics.median(samples[0]),
                    sanitizer_not_ranked=target=='sanitizers'))
            for kind in ['corner','stats']:
                text=run(target+'-negative-'+kind,prefix+[wsl_path(binary),wsl_path(fixtures[0]),'--negative-'+kind],expected=(3,))
                assert 'GEOMETRY_PAIR_MISMATCH kind=' in text
        mutant=out/'geometry-fused-mutant.c'
        text=generated.read_text();old='xqgeom_div(value,961)-in[at]-5;';assert text.count(old)==1
        mutant.write_text(text.replace(old,'xqgeom_div(value,961)-in[at]-4;'),newline='\n')
        binary=out/'mutant-unit'
        run('mutant-build',['cc',*flags,*options,'-DXQ_GEOMETRY_FUSED=1','-DGEOMETRY_SOURCE="'+wsl_path(mutant)+'"',
            wsl_path(unit),wsl_path(files[-1]),'-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
        text=run('mutant-rejected',[wsl_path(binary)],expected=(6,134));assert 'Assertion' in text or 'assertion' in text
        assert all(sha(p)==h for p,h in before.items())
        assert all(sha(p)==h for p,h in private_before.items())
        result.update(status='GEOMETRY_FUSED_FULL_ARRAYS_PAIRED_BITS_NEGATIVE_CONTROLS_PASS_NOT_BOARD',
            sources_and_private_inputs_stable=True,contrast_corner_stats_mutants_rejected=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
