"""Offline exact reduction prototype, numeric checks and alternating geometry pairs.

Production geometry is untouched. The generated candidate changes only the
three ordered arithmetic operations of the four-corner integral reduction.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import subprocess

from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-fixture', type=Path, action='append', required=True)
    args = parser.parse_args()
    if not args.output.absolute().is_relative_to(ROOT/'build'):
        parser.error('Use a new private build output directory')
    out = workspace_path(args.output)
    if not out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()):
        parser.error('Private fixture evidence must stay in E')
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT/'linux/picture_new/geometry_locality.c'
    header = ROOT/'linux/picture_new/experiments/geometry_reduce_exact.h'
    unit = ROOT/'linux/picture_new/experiments/test_geometry_reduce_exact.c'
    pair = ROOT/'linux/picture_new/test_geometry_pair.c'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    files = [source, header, unit, pair, Path(__file__).resolve(),
        ROOT/'linux/picture_new/geometry_mask.h', ROOT/'linux/picture_new/geometry_exact.h',
        ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c',
        ROOT/'sw/bootloader/crc32_fast.c']
    before = {p: sha(p) for p in files}
    fixtures = [workspace_path(p) for p in args.private_fixture]
    private_before = {p: sha(p) for p in fixtures}
    original = source.read_text(encoding='utf-8')
    old = ('out[(size_t)y*width+x]=integral[(size_t)b*stride+r]-integral[(size_t)y*stride+r]-\n'
           '            integral[(size_t)b*stride+x]+integral[(size_t)y*stride+x];')
    new = ('out[(size_t)y*width+x]=xqgeom_reduce4(integral[(size_t)b*stride+r],integral[(size_t)y*stride+r],\n'
           '            integral[(size_t)b*stride+x],integral[(size_t)y*stride+x]);')
    assert original.count(old) == 1
    candidate = original.replace(old, new)
    assert candidate.replace(new, old) == original
    generated = out/'geometry-reduce.c'
    include = '../../artifacts/vision-model-20261020/geometry/geometry_reference.c'
    candidate = '#include "'+wsl_path(header)+'"\n'+candidate.replace(include, wsl_path(files[-2]))
    generated.write_text(candidate, encoding='utf-8', newline='\n')
    result = dict(status='FAILED_PRESERVED', hardware_used=False, production_source_unchanged=True,
        source_sha256={p.relative_to(ROOT).as_posix():h for p,h in before.items()},
        generated_sha256=sha(generated), numeric_checks=[], pairs=[],
        not_integrated_into_worker=True, not_board_latency=True, reassociation_forbidden=True)

    def run(label, argv, expected=(0,), seconds=60):
        log = out/(label+'.log')
        with log.open('xb') as f:
            proc = subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(seconds)+' '+shlex.join(argv)],
                stdout=f, stderr=subprocess.STDOUT, timeout=seconds+15)
        text = log.read_text(errors='replace')
        assert proc.returncode in expected, (label, proc.returncode, text[-1500:])
        return text

    try:
        flags = ['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
                 '-ffunction-sections','-fdata-sections']
        includes = ['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader',
                    'artifacts/vision-model-20261020-adapter/runtime']
        flags += ['-I'+wsl_path(ROOT/p) for p in includes]
        for target in ['host','rv32','sanitizers']:
            compiler = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
            extra = ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target == 'rv32' else []
            if target == 'sanitizers':
                extra = ['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                         '-fno-omit-frame-pointer','-no-pie']
            prefix = ['qemu-riscv32'] if target == 'rv32' else []
            binary = out/(target+'-numeric')
            run(target+'-numeric-build',[compiler,*flags,*extra,wsl_path(unit),'-lm','-o',wsl_path(binary)])
            text = run(target+'-numeric',prefix+[wsl_path(binary)])
            assert 'GEOMETRY_REDUCE_EXACT cases=4000392 PASS_NOT_BOARD' in text
            result['numeric_checks'].append(dict(target=target,cases=4000392,bits_equal=True))
            objects = []
            for variant,path in [('baseline',source),('candidate',generated)]:
                renamed = ['-Dxnp_'+name+'='+variant+'_'+name for name in
                    ['filter_candidates','load_rng','coarse','refine','refine_full','finish']]
                renamed += ['-Dxq_training_geometry_cli='+variant+'_training_cli']
                options = ['-D'+name+'=1' for name in ['XQ_GEOMETRY_GRAY_TABLE','XQ_GEOMETRY_FAST',
                    'XQ_GEOMETRY_ARITH','XQ_GEOMETRY_COMPACT','XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND']]
                obj = out/(target+'-'+variant+'.o');objects.append(obj)
                run(target+'-'+variant+'-build',[compiler,*flags,*extra,*renamed,*options,
                    '-c',wsl_path(path),'-o',wsl_path(obj)])
            binary = out/(target+'-pair')
            run(target+'-pair-build',[compiler,*flags,*extra,wsl_path(pair),*[wsl_path(p) for p in objects],
                wsl_path(files[-1]),'-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            for index,fixture in enumerate(fixtures):
                text = run(target+'-pair-'+str(index),prefix+[wsl_path(binary),wsl_path(fixture)])
                assert 'GEOMETRY_PAIR_FULL_CORNERS_STATISTICS_EQUAL' in text
                samples = {0:[],1:[]}
                for variant,cpu,wall in re.findall(r'GEOMETRY_PAIR_NS repeat=\d+ variant=(\d+) cpu=(\d+) wall=(\d+)',text):
                    samples[int(variant)].append(int(cpu))
                assert all(len(v)==4 for v in samples.values())
                ratio = statistics.median(samples[1])/statistics.median(samples[0])
                result['pairs'].append(dict(target=target,case=index,full_result_bits_equal=True,
                    cpu_samples_ns=samples,median_cpu_ratio=ratio,sanitizer_not_ranked=target=='sanitizers'))
            for kind in ['corner','stats']:
                text = run(target+'-negative-'+kind,prefix+[wsl_path(binary),wsl_path(fixtures[0]),'--negative-'+kind],expected=(3,))
                assert 'GEOMETRY_PAIR_MISMATCH kind=' in text
        # A deliberately reassociated reduction must be distinguishable.
        mutant = out/'numeric-reassociated.c'
        bad_header = out/'geometry-reassociated.h'
        text = header.read_text(encoding='utf-8')
        start = text.index('    double first=xqgeom_reduce_sub(a,b);')
        finish = text.index('\n}',start)
        text = text[:start]+'    return (a-b)-(c-d);'+text[finish:]
        bad_header.write_text(text,encoding='utf-8',newline='\n')
        mutant.write_text(unit.read_text(encoding='utf-8').replace('"geometry_reduce_exact.h"','"'+wsl_path(bad_header)+'"'),encoding='utf-8',newline='\n')
        binary = out/'numeric-reassociated'
        run('mutant-build',['cc',*flags,wsl_path(mutant),'-lm','-o',wsl_path(binary)])
        text = run('mutant-rejected',[wsl_path(binary)],expected=(6,134))
        assert 'Assertion' in text or 'assertion' in text
        assert all(sha(p)==h for p,h in before.items())
        assert all(sha(p)==h for p,h in private_before.items())
        result.update(status='EXACT_REDUCTION_NUMERIC_AND_PAIRED_GEOMETRY_PASS_NOT_SELECTED_NOT_BOARD',
            sources_private_inputs_stable=True,reassociated_reduction_mutant_rejected=True,
            warmup_both=True,alternating_four_pairs=True)
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
