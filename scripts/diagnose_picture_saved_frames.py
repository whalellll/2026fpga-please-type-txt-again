"""Bounded saved-frame seam capture and grid profiling; all payloads stay on E.

Uses an explicitly supplied, previously audited mock builder and its options.
No device, camera, model modification, truth/layout prior or installer.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import subprocess

from picture_workspace import ROOT, workspace_path, wsl_path


CAPTURE = r'''
#define _POSIX_C_SOURCE 200809L
#include "board_grid_recovery.h"
#include "coach_geometry.h"
#include "geometry_cancel.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned geometry_call;
static FILE *create(const char *name){
    const char *dir=getenv("XQ_SAVED_FRAME_CAPTURE");char path[2048];assert(dir);
    int n=snprintf(path,sizeof(path),"%s/%s",dir,name);assert(n>0 && (size_t)n<sizeof(path));
    FILE *f=fopen(path,"wbx");assert(f);return f;
}
static void put(FILE *f,const void *p,size_t bytes){assert(fwrite(p,1,bytes,f)==bytes);}
int __real_xqgrid_recover(const uint8_t *,size_t,const float *,float *,int (*)(void *),void *,xqgrid_stats *);
int __wrap_xqgrid_recover(const uint8_t *rgb,size_t bytes,const float *q,float *o,
    int (*cancel)(void *),void *context,xqgrid_stats *stats){
    assert(bytes==1280u*720u*3u);FILE *f=create("grid.bin");
    put(f,"XQGRID1",8);put(f,q,32);put(f,rgb,bytes);assert(!fclose(f));
    return __real_xqgrid_recover(rgb,bytes,q,o,cancel,context,stats);
}
int __real_xqcoach_refine_cancellable(const uint8_t *,const double [4][2],const xqr_box *,
    unsigned,const uint8_t [91][240][4],double [4][2],xnp_refinement *,int (*)(void *),void *);
int __wrap_xqcoach_refine_cancellable(const uint8_t *rgb,const double q[4][2],const xqr_box *b,
    unsigned n,const uint8_t rng[91][240][4],double o[4][2],xnp_refinement *stats,
    int (*cancel)(void *),void *context){
    char name[64];snprintf(name,sizeof(name),"geometry-%u.bin",geometry_call++);
    assert(sizeof(xqr_box)==24 && sizeof(unsigned)==4 && sizeof(double)==8);
    FILE *f=create(name);put(f,"XQGEOM1",8);put(f,&n,4);put(f,q,64);put(f,b,n*24u);
    put(f,rng,91u*240u*4u);put(f,rgb,1280u*720u*3u);assert(!fclose(f));
    return __real_xqcoach_refine_cancellable(rgb,q,b,n,rng,o,stats,cancel,context);
}
'''

GRID_HARNESS = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <time.h>
static unsigned long long ns(void){struct timespec t;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));
    return (unsigned long long)t.tv_sec*1000000000u+t.tv_nsec;}
static unsigned long long elapsed[6],mark;
static void stage(unsigned i){unsigned long long now=ns();elapsed[i]+=now-mark;mark=now;}
#include GRID_SOURCE
int main(int argc,char **argv){
    assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);char magic[8];float q[8],out[8]={0};
    unsigned char *rgb=malloc(1280u*720u*3u);assert(rgb);
    assert(fread(magic,1,8,f)==8 && !memcmp(magic,"XQGRID1",8) && fread(q,4,8,f)==8);
    assert(fread(rgb,1,1280u*720u*3u,f)==1280u*720u*3u && fgetc(f)==EOF && !ferror(f) && !fclose(f));
    xqgrid_stats stats={0};mark=ns();int okay=xqgrid_recover(rgb,1280u*720u*3u,q,out,NULL,NULL,&stats);stage(5);
    f=fopen(argv[2],"wbx");assert(f);
    assert(fwrite(&okay,sizeof(okay),1,f)==1 && fwrite(out,sizeof(out),1,f)==1);
    unsigned fields[]={stats.attempted,stats.used,stats.corner,stats.edges,stats.normal0,stats.normal1,stats.cancelled};
    assert(fwrite(fields,sizeof(fields),1,f)==1 && fwrite(&stats.score,8,1,f)==1 && !fclose(f));
    for(unsigned i=0;i<6;i++)printf("GRID_PHASE %u %llu\n",i,elapsed[i]);
    printf("GRID_RESULT %d %u %u %u\n",okay,stats.attempted,stats.used,stats.edges);free(rgb);return 0;
}
'''


def observe_grid(source):
    changes = []

    def change(a, b):
        nonlocal source
        assert source.count(a) == 1, a
        source = source.replace(a, b)
        changes.append((a, b))

    change('    if(!make_edges(s,rgb) || !hough(s,normals))goto done;',
           '    stage(0);\n    if(!make_edges(s,rgb))goto done;stage(1);\n'
           '    if(!hough(s,normals))goto done;stage(2);')
    change('    double score=-INFINITY,proposal[4][2]={{0}};',
           '    stage(3);\n    double score=-INFINITY,proposal[4][2]={{0}};')
    change('        if(!find_lattices(s,s->families,assignment?10:9) ||\n'
           '           !find_lattices(s,s->families+1,assignment?9:10) || !combine(s,&score,proposal))goto done;',
           '        if(!find_lattices(s,s->families,assignment?10:9) ||\n'
           '           !find_lattices(s,s->families+1,assignment?9:10))goto done;\n'
           '        stage(4);\n        if(!combine(s,&score,proposal))goto done;stage(5);')
    reverse = source
    for a, b in reversed(changes):
        assert reverse.count(b) == 1
        reverse = reverse.replace(b, a)
    return source, reverse


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--handoff', type=Path)
    ap.add_argument('--mock-build', type=Path)
    ap.add_argument('--mock-receipt', type=Path)
    ap.add_argument('--models', type=Path)
    ap.add_argument('--grid-dot-cache', action='store_true')
    ap.add_argument('--geometry-min-bits', action='store_true')
    ap.add_argument('--graph-profile', action='store_true')
    ap.add_argument('--phase', choices=['capture', 'grid'], required=True)
    ap.add_argument('--capture', type=Path, help='Existing capture directory for grid phase')
    ap.add_argument('--targets', default='host,rv32', choices=['host', 'host,rv32'])
    a = ap.parse_args()
    if a.phase == 'capture' and any(p is None for p in [a.handoff, a.mock_build, a.mock_receipt, a.models]):
        ap.error('capture requires --handoff, --mock-build, --mock-receipt and --models')
    if a.phase == 'grid' and a.capture is None:
        ap.error('grid requires --capture')
    private = (ROOT/'build/picture-e42-20261025').resolve()
    out = workspace_path(a.output)
    assert out.is_relative_to(private)
    handoff = workspace_path(a.handoff) if a.handoff else None
    assert handoff is None or handoff.is_relative_to(private)
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(status='FAILED_PRESERVED', hardware_used=False, driver_drain_mocked=True,
                  script_sha256=sha(Path(__file__)), checks=[])
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())

    def run(name, args, seconds=60):
        with (out/(name+'.log')).open('xb') as f:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(seconds)+' '+shlex.join(args)],
                stdout=f, stderr=subprocess.STDOUT, timeout=seconds+15)
        log = (out/(name+'.log')).read_text(errors='replace')
        assert p.returncode == 0, (name, p.returncode, log[-2000:])
        return log

    try:
        if a.phase == 'capture':
            for row in json.loads((handoff/'manifest.json').read_text())['files']:
                p = handoff/row['path']
                if row['path'].startswith('cases/'):
                    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
            build = workspace_path(a.mock_build)
            receipt = workspace_path(a.mock_receipt)
            source = build.read_text()
            source, n = re.subn(r'test "\$out" = [^\n]+',
                                'test "$out" = '+wsl_path(out/'worker'), source, count=1)
            assert n == 1 and source.count('"$worker" "$graph" "$@"') == 1
            source = source.replace('"$worker" "$graph" "$@"',
                                    '"$worker" '+shlex.quote(wsl_path(out/'capture.c'))+' "$graph" "$@"')
            assert source.count('-Wl,--wrap=ioctl,') == 1
            source = source.replace('-Wl,--wrap=ioctl,',
                '-Wl,--wrap=xqgrid_recover,--wrap=xqcoach_refine_cancellable,--wrap=ioctl,')
            if a.grid_dot_cache:
                assert source.count('"$cc" $flags ') == 1
                source = source.replace('"$cc" $flags ', '"$cc" $flags -DXQ_GRID_DOT_CACHE=1 ')
            if a.geometry_min_bits:
                assert source.count('"$cc" $flags ') == 1
                source = source.replace('"$cc" $flags ', '"$cc" $flags -DXQ_GEOMETRY_MIN_BITS=1 ')
            (out/'capture.c').write_text(CAPTURE, newline='\n')
            (out/'build.sh').write_text(source, newline='\n')
            options = json.loads(receipt.read_text())['options']
            if a.graph_profile:
                assert not any(s.startswith('XQ_GRAPH_PROFILE=') for s in options)
                options.append('XQ_GRAPH_PROFILE=1')
            result.update(mock_builder_sha256=sha(build), options=options, grid_dot_cache=a.grid_dot_cache,
                          geometry_min_bits=a.geometry_min_bits)
            run('build', ['env', *options, 'sh', wsl_path(out/'build.sh'), wsl_path(ROOT),
                wsl_path(out/'worker'), wsl_path(workspace_path(a.models)), 'host'], 120)
            for case, packet in [('01-missing-red-rook', 'r09-mock-result.txt'),
                                 ('02-correct', 'actual-result.txt')]:
                caseout = out/case; caseout.mkdir()
                saved = handoff/'cases'/case
                log = run(case, ['env', 'XQ_SAVED_FRAME_CAPTURE='+wsl_path(caseout),
                    wsl_path(out/'worker/xq-coach-worker'), '--driver', '--models', wsl_path(workspace_path(a.models)),
                    '--request', wsl_path(saved/'request.txt'), '--input', wsl_path(saved/'frame.rgb565'),
                    '--output', wsl_path(caseout/'result.txt')], 180)
                assert (caseout/'result.txt').read_bytes() == (saved/packet).read_bytes()
                assert (caseout/'grid.bin').exists()
                geometries = list(caseout.glob('geometry-*.bin')); assert geometries
                result['checks'].append(dict(case=case, packet_byte_equal=True, geometry_calls=len(geometries),
                    summary=[s for s in log.splitlines() if s.startswith(('XQ_NATIVE_GRID', 'XQ_NATIVE_STAGE',
                            'XQ_NATIVE_PROFILE', 'XQ_NATIVE_CANDIDATES', 'XQ_HWC_PROFILE', 'PN05_GRAPH_PROFILE'))]))
            result['status'] = 'TWO_SAVED_FRAME_SEAM_CAPTURES_PACKET_EXACT_NOT_BOARD'
        else:
            capture = workspace_path(a.capture); assert capture.is_relative_to(private)
            grid = ROOT/'linux/picture_new/board_grid_recovery.c'
            original = grid.read_text()
            observed, reverse = observe_grid(original); assert reverse == original
            (out/'grid-observed.c').write_text(observed, newline='\n')
            (out/'grid.c').write_text(GRID_HARNESS, newline='\n')
            result.update(grid_source_sha256=sha(grid), observation_reverses_exactly=True,
                phase_names=['setup', 'edges', 'hough', 'families', 'lattices', 'combine_finish'])
            for target in a.targets.split(','):
                cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
                extra = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
                prefix = ['qemu-riscv32'] if target == 'rv32' else []
                for variant, source in [('baseline', grid), ('observed', out/'grid-observed.c')]:
                    exe = out/(target+'-'+variant)
                    run(target+'-'+variant+'-build', [cc, '-std=c11', '-O2', '-ffp-contract=off', *extra,
                        '-I'+wsl_path(ROOT/'linux/picture_new'), '-DXQ_GRID_PLAN_FAST=1',
                        '-DGRID_SOURCE="'+wsl_path(source)+'"', wsl_path(out/'grid.c'), '-lm', '-o', wsl_path(exe)])
                    for case in ['01-missing-red-rook', '02-correct']:
                        name = target+'-'+variant+'-'+case
                        log = run(name, [*prefix, wsl_path(exe), wsl_path(capture/case/'grid.bin'),
                                         wsl_path(out/(name+'.bin'))])
                        if variant == 'observed':
                            assert (out/(name+'.bin')).read_bytes() == (out/(target+'-baseline-'+case+'.bin')).read_bytes()
                            result['checks'].append(dict(target=target, case=case, full_result_bytes_equal=True,
                                cpu_ns=[int(v) for _, v in re.findall(r'GRID_PHASE (\d+) (\d+)', log)]))
            result['status'] = 'GRID_OBSERVATION_COMPLETE_RESULT_EXACT_NOT_BOARD'
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
