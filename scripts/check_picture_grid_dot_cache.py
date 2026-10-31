"""Differential grid dot cache, recovery guards and bounded same-process pairs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import subprocess

from diagnose_picture_saved_frames import GRID_HARNESS
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--capture', required=True, type=Path)
    ap.add_argument('--pairs-only', action='store_true', help='Run new pairs without repeating completed guards')
    a = ap.parse_args()
    out = workspace_path(a.output)
    capture = workspace_path(a.capture)
    private = (ROOT/'build/picture-e42-20261025').resolve()
    assert out.is_relative_to(private) and capture.is_relative_to(private)
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    grid = ROOT/'linux/picture_new/board_grid_recovery.c'
    sources = [grid, ROOT/'linux/picture_new/board_grid_recovery.h',
               ROOT/'linux/picture_new/test_grid_plan.c', ROOT/'linux/picture_new/test_grid_recovery.c',
               ROOT/'linux/vision/xq_roi.c', Path(__file__)]
    before = {str(p): sha(p) for p in sources}
    result = dict(status='FAILED_PRESERVED', hardware_used=False, checks=[], pairs=[],
                  source_sha256={p.relative_to(ROOT).as_posix(): before[str(p)] for p in sources})
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())

    def run(name, args, expected=0, limit=90):
        with (out/(name+'.log')).open('xb') as f:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(limit)+' '+shlex.join(args)],
                stdout=f, stderr=subprocess.STDOUT, timeout=limit+15)
        log = (out/(name+'.log')).read_text(errors='replace')
        assert (p.returncode == 0) == (expected == 0), (name, p.returncode, log[-1800:])
        return log

    try:
        # The old matrix also covers repeated lattices, ties, signed zero and
        # exact cancellation call counts. Add oblique line/family normals so
        # each cached projection must select the correct line and corner.
        internal = (ROOT/'linux/picture_new/test_grid_plan.c').read_text()
        internal = internal.replace('#include "board_grid_recovery.c"', '#include GRID_SOURCE')
        anchor = '    double d=15;'
        assert internal.count(anchor) == 1
        internal = internal.replace(anchor, '    double theta=(mode?.07:-.11)+a*1.5707963267948966;\n'
            '        f->nx=cos(theta);f->ny=sin(theta);\n'+anchor)
        anchor = 'l->log_votes=(next()%64)*.125;'
        assert internal.count(anchor) == 1
        internal = internal.replace(anchor, 'l->nx=cos(theta+(i%3-1)*.003);l->ny=sin(theta+(i%3-1)*.003);\n'
            '            '+anchor)
        (out/'internal.c').write_text(internal, newline='\n')
        (out/'real.c').write_text(GRID_HARNESS, newline='\n')
        includes = ['-I'+wsl_path(ROOT/p) for p in ['linux/picture_new', 'linux/vision', 'sw/xiangqi', 'sw/bootloader']]
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
                 '-ffunction-sections', '-fdata-sections', *includes]
        for target in ([] if a.pairs_only else ['host', 'rv32', 'sanitizers']):
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
            extra = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
            if target == 'sanitizers':
                extra = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-no-pie']
            prefix = ['qemu-riscv32'] if target == 'rv32' else []
            for cache in [0, 1]:
                config = [*flags, *extra, '-DXQ_GRID_DOT_CACHE='+str(cache), '-DXQ_GRID_PLAN_FAST=1']
                for fixture in ['internal', 'real', 'recovery']:
                    exe = out/(target+'-'+str(cache)+'-'+fixture)
                    inputs = [wsl_path(out/(fixture+'.c'))] if fixture != 'recovery' else [
                        wsl_path(ROOT/'linux/picture_new/test_grid_recovery.c'), wsl_path(grid),
                        wsl_path(ROOT/'linux/vision/xq_roi.c')]
                    run(exe.name+'-build', [cc, *config, '-DGRID_SOURCE="'+wsl_path(grid)+'"', *inputs,
                        '-Wl,--wrap=calloc,--gc-sections' if fixture == 'recovery' else '-Wl,--gc-sections',
                        '-lm', '-o', wsl_path(exe)])
                    if fixture == 'recovery':
                        run(exe.name, [*prefix, wsl_path(exe), '--synthetic'])
                    elif fixture == 'internal':
                        run(exe.name, [*prefix, wsl_path(exe), wsl_path(out/(exe.name+'.bin'))])
                    else:
                        for case in ['01-missing-red-rook', '02-correct']:
                            run(exe.name+'-'+case, [*prefix, wsl_path(exe), wsl_path(capture/case/'grid.bin'),
                                wsl_path(out/(exe.name+'-'+case+'.bin'))])
            assert (out/(target+'-0-internal.bin')).read_bytes() == (out/(target+'-1-internal.bin')).read_bytes()
            for case in ['01-missing-red-rook', '02-correct']:
                assert (out/(target+'-0-real-'+case+'.bin')).read_bytes() == (out/(target+'-1-real-'+case+'.bin')).read_bytes()
            result['checks'].append(dict(target=target, oblique_internal_96_full_bits=True,
                recovery_cancel_oom_guards=True, both_real_grid_results_exact=True))
        # Incorrect line selection must fail the full internal state oracle.
        mutant = grid.read_text().replace('line_projected[j][c]-r1', 'line_projected[i][c]-r1')
        assert mutant != grid.read_text()
        (out/'mutant.c').write_text(mutant, newline='\n')
        if not a.pairs_only:
            run('mutant-build', ['cc', *flags, '-DXQ_GRID_PLAN_FAST=1', '-DXQ_GRID_DOT_CACHE=1',
                '-DGRID_SOURCE="'+wsl_path(out/'mutant.c')+'"', wsl_path(out/'internal.c'), '-lm', '-o', wsl_path(out/'mutant')])
            run('mutant', [wsl_path(out/'mutant'), wsl_path(out/'mutant.bin')])
            assert (out/'mutant.bin').read_bytes() != (out/'host-0-internal.bin').read_bytes()
            result['wrong_line_negative_rejected'] = True
        # Compile both real implementations separately, call in alternating
        # order within one process, with both warmups outside measurement.
        bench = GRID_HARNESS.replace('#include GRID_SOURCE', '#include "board_grid_recovery.h"\n#include <stdlib.h>\n#include <string.h>\n'
            'int baseline(const uint8_t *,size_t,const float *,float *,int (*)(void *),void *,xqgrid_stats *);\n'
            'int candidate(const uint8_t *,size_t,const float *,float *,int (*)(void *),void *,xqgrid_stats *);')
        first = '    xqgrid_stats stats={0};mark=ns();int okay=xqgrid_recover(rgb,1280u*720u*3u,q,out,NULL,NULL,&stats);stage(5);'
        assert bench.count(first) == 1
        bench = bench.replace(first, r'''
    (void)stage;xqgrid_stats stats={0};int okay=0;float expected[8];xqgrid_stats ref={0};
    assert(baseline(rgb,1280u*720u*3u,q,expected,NULL,NULL,&ref));
    assert(candidate(rgb,1280u*720u*3u,q,out,NULL,NULL,&stats));
    assert(!memcmp(expected,out,32) && !memcmp(&ref,&stats,sizeof(ref)));
    for(unsigned pair=0;pair<4;pair++)for(unsigned turn=0;turn<2;turn++){
        unsigned which=turn^(pair&1);unsigned long long start=ns();
        for(unsigned repeat=0;repeat<8;repeat++){
            okay=which?candidate(rgb,1280u*720u*3u,q,out,NULL,NULL,&stats):
                baseline(rgb,1280u*720u*3u,q,out,NULL,NULL,&stats);
            assert(okay && !memcmp(expected,out,32) && !memcmp(&ref,&stats,sizeof(ref)));
        }
        printf("PAIR %u %u %llu\n",pair,which,ns()-start);
    }
''')
        (out/'bench.c').write_text(bench, newline='\n')
        for target in ['host', 'rv32']:
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
            extra = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
            objs = []
            for cache, name in [(0, 'baseline'), (1, 'candidate')]:
                obj = out/(target+'-'+name+'.o'); objs.append(wsl_path(obj))
                run(obj.stem+'-build', [cc, *flags, *extra, '-DXQ_GRID_PLAN_FAST=1', '-DXQ_GRID_DOT_CACHE='+str(cache),
                    '-Dxqgrid_recover='+name, '-c', wsl_path(grid), '-o', wsl_path(obj)])
            exe = out/(target+'-bench')
            run(exe.name+'-build', [cc, *flags, *extra, wsl_path(out/'bench.c'), *objs, '-lm', '-o', wsl_path(exe)])
            log = run(exe.name, [*(['qemu-riscv32'] if target == 'rv32' else []), wsl_path(exe),
                wsl_path(capture/'02-correct/grid.bin'), wsl_path(out/(exe.name+'.bin'))])
            times = {(int(p), int(v)): int(ns) for p, v, ns in re.findall(r'PAIR (\d+) (\d+) (\d+)', log)}
            assert len(times) == 8
            ratios = [times[p, 1]/times[p, 0] for p in range(4)]
            result['pairs'].append(dict(target=target, pairs=4, repeats=8, ratios=ratios, median_ratio=statistics.median(ratios)))
        assert all(sha(p) == before[str(p)] for p in sources)
        result.update(status=('GRID_DOT_CACHE_PAIRS_ONLY_PASS_NOT_BOARD' if a.pairs_only else
                              'GRID_DOT_CACHE_BITS_GUARDS_AND_PAIRS_PASS_NOT_BOARD'),
                      source_sha256={p.relative_to(ROOT).as_posix(): before[str(p)] for p in sources})
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
