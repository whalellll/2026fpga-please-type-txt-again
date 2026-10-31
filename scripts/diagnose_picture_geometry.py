"""Bounded offline geometry observation; private fixtures and dumps stay in build.

Generate an observational copy, compare its complete result bytes with the
unchanged implementation, and separate filtering/search/fitting costs. This
does not select a new geometry algorithm or establish device latency.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import struct
import subprocess

from picture_workspace import ROOT, workspace_path, wsl_path


PRELUDE = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
static FILE *diag_trace;
static const char *diag_directory;
static uint64_t diag_cpu[12],diag_wall[12],diag_last_cpu,diag_last_wall;
static uint64_t diag_sums[3][4][2];
static unsigned diag_sum_calls;
static unsigned diag_stage;
static uint64_t diag_now(clockid_t kind)
{struct timespec t;assert(!clock_gettime(kind,&t));return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;}
static void diag_phase(unsigned stage)
{
    uint64_t cpu=diag_now(CLOCK_PROCESS_CPUTIME_ID),wall=diag_now(CLOCK_MONOTONIC);
    if(diag_last_cpu){diag_cpu[diag_stage]+=cpu-diag_last_cpu;diag_wall[diag_stage]+=wall-diag_last_wall;}
    diag_last_cpu=cpu;diag_last_wall=wall;diag_stage=stage;
}
static void diag_blob(const char *name,const void *data,size_t size)
{
    if(!diag_trace)return;
    char path[2048];int n=snprintf(path,sizeof(path),"%s/%s",diag_directory,name);
    assert(n>0 && (size_t)n<sizeof(path));FILE *f=fopen(path,"wbx");
    assert(f && fwrite(data,1,size,f)==size && !fclose(f));
}
static void diag_sum_mark(unsigned call,unsigned stage,uint64_t *cpu,uint64_t *wall)
{
    uint64_t c=diag_now(CLOCK_PROCESS_CPUTIME_ID),w=diag_now(CLOCK_MONOTONIC);
    assert(call<3 && stage<4);diag_sums[call][stage][0]+=c-*cpu;diag_sums[call][stage][1]+=w-*wall;
    *cpu=c;*wall=w;
}
'''

HARNESS = r'''
#include DIAG_SOURCE
#include <assert.h>
int main(int argc,char **argv)
{
    assert(argc==5);
    FILE *f=fopen(argv[1],"rb");assert(f);char magic[8];unsigned n;
    double q[4][2],corners[4][2]={{0}};xqr_box boxes[300];xnp_refinement stats={0};
    uint8_t (*rng)[240][4]=malloc(91u*240u*4u),*rgb=malloc(1280u*720u*3u);
    assert(rng && rgb && fread(magic,1,8,f)==8 && !memcmp(magic,"XQGEOM1",8));
    assert(fread(&n,4,1,f)==1 && n<=300 && fread(q,8,8,f)==8 && fread(boxes,24,n,f)==n);
    assert(fread(rng,1,91u*240u*4u,f)==91u*240u*4u && fread(rgb,1,1280u*720u*3u,f)==1280u*720u*3u);
    assert(fgetc(f)==EOF && !ferror(f) && !fclose(f));
#ifdef DIAG_ENABLED
    diag_directory=argv[3];
    if(strcmp(argv[3],"-")){
        char path[2048];int count=snprintf(path,sizeof(path),"%s/trace.txt",diag_directory);
        assert(count>0 && (size_t)count<sizeof(path));diag_trace=fopen(path,"wx");assert(diag_trace);
    }
#endif
    int okay=!strcmp(argv[4],"full")?xnp_refine_full(rgb,q,boxes,n,rng,corners,&stats):
        xnp_refine(rgb,q,boxes,n,rng,corners,&stats);
#ifdef DIAG_ENABLED
    if(diag_trace)assert(!fclose(diag_trace));
    for(unsigned i=0;i<12;i++)printf("PHASE %u %llu %llu\n",i,
        (unsigned long long)diag_cpu[i],(unsigned long long)diag_wall[i]);
    for(unsigned i=0;i<diag_sum_calls;i++)for(unsigned j=0;j<4;j++)printf("SUM %u %u %llu %llu\n",i,j,
        (unsigned long long)diag_sums[i][j][0],(unsigned long long)diag_sums[i][j][1]);
#endif
    f=fopen(argv[2],"wbx");assert(f && fwrite(&okay,sizeof(okay),1,f)==1 &&
        fwrite(corners,sizeof(corners),1,f)==1 && fwrite(&stats,sizeof(stats),1,f)==1 && !fclose(f));
    printf("RESULT %d %u %u\n",okay,stats.crossings,stats.inliers);
    free(rng);free(rgb);return 0;
}
'''


def observed_source(original):
    edits = []

    def edit(old, new):
        nonlocal original
        if original.count(old) != 1:
            raise ValueError('Observation anchor is not unique: ' + old[:100])
        original = original.replace(old, new)
        edits.append((old, new))

    edit('    double *integral=calloc((size_t)(ph+1)*stride,sizeof(double));',
         '    unsigned diag_call=diag_sum_calls++;\n'
         '    uint64_t diag_at_cpu=diag_now(CLOCK_PROCESS_CPUTIME_ID),diag_at_wall=diag_now(CLOCK_MONOTONIC);\n'
         '    double *integral=calloc((size_t)(ph+1)*stride,sizeof(double));')
    edit('    if(!integral)return 0;',
         '    if(!integral)return 0;\n    diag_sum_mark(diag_call,0,&diag_at_cpu,&diag_at_wall);')
    edit('/* XQGEOM_ROW_END */',
         '/* XQGEOM_ROW_END */\n    diag_sum_mark(diag_call,1,&diag_at_cpu,&diag_at_wall);')
    edit('/* XQGEOM_EXACT_PREFIX_END */\n    }',
         '/* XQGEOM_EXACT_PREFIX_END */\n    }\n'
         '    diag_sum_mark(diag_call,2,&diag_at_cpu,&diag_at_wall);')
    edit('    free(integral);return 1;',
         '    diag_sum_mark(diag_call,3,&diag_at_cpu,&diag_at_wall);\n    free(integral);return 1;')
    edit('    if(stats)memset(stats,0,sizeof(*stats));',
         '    diag_phase(0);\n    if(stats)memset(stats,0,sizeof(*stats));')
    for anchor, stage in [
        ('/* XQGEOM_TABLE_BEGIN */', 1),
        ('/* XQGEOM_SELECT_FIRST_BEGIN */', 2),
        ('/* XQGEOM_EXACT_CONTRAST_BEGIN */', 3),
        ('/* XQGEOM_MASK_HORIZONTAL_BEGIN */', 4),
        ('/* XQGEOM_EXACT_HORIZONTAL_BEGIN */', 5),
        ('/* XQGEOM_MASK_VERTICAL_BEGIN */', 6),
        ('/* XQGEOM_EXACT_VERTICAL_BEGIN */', 7),
        ('    for(unsigned gy=0;gy<9;gy++)for(unsigned gx=0;gx<10;gx++) {', 8),
        ('    if(stats)stats->crossings=n;', 9),
    ]:
        edit(anchor, '    diag_phase(%u);\n' % stage + anchor)
    edit('    diag_phase(8);', r'''
    if(diag_trace){
        fprintf(diag_trace,"IMAGE %u %u %d %d %.17g %u\n",width,height,ox,oy,spacing,radius);
        diag_blob("score.f64",score,pixels_count*sizeof(*score));
        diag_blob("mask.u8",mask,pixels_count*sizeof(*mask));
    }
    diag_phase(8);''')
    edit('        if(x0<x1 && y0<y1 && score[(size_t)by*width+(unsigned)bx]>=.26) {', r'''
        if(diag_trace)fprintf(diag_trace,"PEAK %u %u %.17g %.17g %d %d %.17g %u\n",
            gx,gy,p[0],p[1],bx+ox,by+oy,score[(size_t)by*width+(unsigned)bx],
            ix>=ox && iy>=oy && ix<ox+(int)width && iy<oy+(int)height?
                (unsigned)mask[(size_t)(iy-oy)*width+(unsigned)(ix-ox)]:2u);
        if(x0<x1 && y0<y1 && score[(size_t)by*width+(unsigned)bx]>=.26) {''')
    edit('        if(v>best_value){best_value=v;memcpy(best,keep,n);}', r'''
        if(diag_trace)fprintf(diag_trace,"TRIAL %u %u %.17g\n",trial,count,v);
        if(v>best_value){best_value=v;memcpy(best,keep,n);}''')
    edit('    if(!isfinite(best_value))goto done;\n    memcpy(keep,best,n);', r'''
    if(!isfinite(best_value))goto done;
    if(diag_trace)for(unsigned i=0;i<n;i++)fprintf(diag_trace,"MATCH %u %.17g %.17g %.17g %.17g %u\n",
        i,grid[i][0],grid[i][1],pixels[i][0],pixels[i][1],best[i]);
    memcpy(keep,best,n);''')
    edit('        if(count<16 || !fit(grid,pixels,keep,n,h))goto done;', r'''
        if(count<16){if(diag_trace)fprintf(diag_trace,"REJECT support %u\n",count);goto done;}
        if(!fit(grid,pixels,keep,n,h)){if(diag_trace)fputs("REJECT fit\n",diag_trace);goto done;}''')
    edit('        if(count<16 || fmin((x1-x0)/9,(y1-y0)/8)<.65 || !fit(grid,pixels,keep,n,h))goto done;', r'''
        if(count<16){if(diag_trace)fprintf(diag_trace,"REJECT final_support %u\n",count);goto done;}
        if(fmin((x1-x0)/9,(y1-y0)/8)<.65){if(diag_trace)fputs("REJECT coverage\n",diag_trace);goto done;}
        if(!fit(grid,pixels,keep,n,h)){if(diag_trace)fputs("REJECT final_fit\n",diag_trace);goto done;}''')
    edit('        for(unsigned i=0;i<4;i++)if(!point(h,xy[i][0],xy[i][1],refined[i]) ||\n'
         '            hypot(refined[i][0]-coarse[i][0],refined[i][1]-coarse[i][1])/spacing>.5)goto done;', r'''
        for(unsigned i=0;i<4;i++){
            if(!point(h,xy[i][0],xy[i][1],refined[i]))goto done;
            double displacement=hypot(refined[i][0]-coarse[i][0],refined[i][1]-coarse[i][1])/spacing;
            if(diag_trace)fprintf(diag_trace,"CORNER %u %.17g\n",i,displacement);
            if(displacement>.5){if(diag_trace)fputs("REJECT displacement\n",diag_trace);goto done;}
        }''')
    edit('    free(gray);free(mask);free(tmp);free(score);free(counts);return okay;',
         '    free(gray);free(mask);free(tmp);free(score);free(counts);diag_phase(11);return okay;')
    reversed_source = original
    for old, new in reversed(edits):
        assert reversed_source.count(new) == 1
        reversed_source = reversed_source.replace(new, old)
    return original, reversed_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--private-fixture', required=True, action='append', type=Path)
    parser.add_argument('--targets', choices=['host', 'host,rv32'], default='host,rv32')
    parser.add_argument('--full-control', action='store_true', help='Observe unchanged full240 separately')
    parser.add_argument('--fused', action='store_true', help='Observe the existing fused reduction/consumer implementation')
    args = parser.parse_args()
    if not args.output.absolute().is_relative_to(ROOT / 'build'):
        parser.error('Output must use the private build junction')
    out = workspace_path(args.output)
    if not out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve()):
        parser.error('Private fixture evidence must stay in the private E build directory')
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'linux/picture_new/geometry_locality.c'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    tracked = [source, ROOT/'linux/picture_new/geometry_mask.h', ROOT/'linux/picture_new/geometry_exact.h',
               ROOT/'scripts/diagnose_picture_geometry.py',
               ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c']
    before = {p: sha(p) for p in tracked}
    fixtures = [workspace_path(p) for p in args.private_fixture]
    fixture_before = {p: sha(p) for p in fixtures}
    original_bytes = source.read_bytes()
    original = source.read_text(encoding='utf-8')
    instrumented, reverse = observed_source(original)
    assert reverse == original
    newline = '\r\n' if b'\r\n' in original_bytes else '\n'
    assert reverse.replace('\n', newline).encode('utf-8') == original_bytes
    include = '../../artifacts/vision-model-20261020/geometry/geometry_reference.c'
    instrumented = instrumented.replace(include, wsl_path(tracked[-1]))
    if args.fused:
        from generate_picture_geometry_fused import generate
        reference = out/'geometry-fused-reference.c'
        generate(ROOT, source, reference)
        observed_input = out/'geometry-observed-unfused.c'
        observed_input.write_text(instrumented, encoding='utf-8', newline='\n')
        fused_observed = out/'geometry-fused-observed.c'
        generate(ROOT, observed_input, fused_observed)
        instrumented = fused_observed.read_text()
        anchor = '    else {free(integral);return 0;}\n    free(integral);return 1;'
        assert instrumented.count(anchor) == 1
        instrumented = instrumented.replace(anchor,
            '    else {free(integral);return 0;}\n'
            '    diag_sum_mark(diag_call,3,&diag_at_cpu,&diag_at_wall);\n    free(integral);return 1;')
        source = reference
    generated = out/'geometry-observed.c'
    generated.write_text(PRELUDE+instrumented, encoding='utf-8', newline='\n')
    harness = out/'fixture.c'
    harness.write_text(HARNESS, encoding='utf-8', newline='\n')
    result = dict(status='FAILED_PRESERVED', hardware_used=False, observations_only=True,
                  production_source_sha256=before[tracked[0]], observed_implementation_sha256=sha(source),
                  reverse_observation_exact=True,
                  private_input_hashes_published=False, checks=[])
    result['existing_fused_implementation'] = args.fused
    result['cancellation_disabled_for_subphase_observation'] = True

    def run(label, command, seconds=40):
        log = out/(label+'.log')
        with log.open('xb') as stream:
            proc = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 '+str(seconds)+' '+shlex.join(command)],
                stdout=stream, stderr=subprocess.STDOUT, timeout=seconds+15)
        assert proc.returncode == 0, (label, proc.returncode, log.read_text(errors='replace')[-1500:])
        return log.read_text()

    try:
        includes = ['linux/picture_new', 'linux/vision', 'linux/mac_accel', 'sw/xiangqi',
                    'sw/bootloader', 'artifacts/vision-model-20261020-adapter/runtime']
        flags = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
                 '-ffunction-sections', '-fdata-sections']
        flags += ['-D'+name+'=1' for name in ['XQ_GEOMETRY_FAST', 'XQ_GEOMETRY_ARITH',
                  'XQ_GEOMETRY_GRAY_TABLE', 'XQ_GEOMETRY_COMPACT', 'XQ_GEOMETRY_SELECTIVE',
                  'XQ_GEOMETRY_SEED_BOUND']]
        if args.fused:
            flags.append('-DXQ_GEOMETRY_FUSED=1')
        flags += ['-I'+wsl_path(ROOT/p) for p in includes]
        for target in args.targets.split(','):
            compiler = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
            target_flags = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
            prefix = ['qemu-riscv32'] if target == 'rv32' else []
            for kind in ['original', 'observed']:
                path = source if kind == 'original' else generated
                extra = ['-DDIAG_ENABLED=1'] if kind == 'observed' else []
                exe = out/(target+'-'+kind)
                run(target+'-'+kind+'-build', [compiler, *flags, *target_flags, *extra,
                    '-DDIAG_SOURCE="'+wsl_path(path)+'"', wsl_path(harness),
                    wsl_path(ROOT/'sw/bootloader/crc32_fast.c'), '-Wl,--gc-sections', '-lm', '-o', wsl_path(exe)])
            for index, fixture in enumerate(fixtures):
                for mode in ['fast']+(['full'] if args.full_control and index == 0 else []):
                    label = '%s-%u-%s' % (target, index, mode)
                    bits = []
                    for kind in ['original', 'observed']:
                        destination = out/(label+'-'+kind+'.bin')
                        text = run(label+'-'+kind, [*prefix, wsl_path(out/(target+'-'+kind)),
                            wsl_path(fixture), wsl_path(destination), '-', mode])
                        bits.append(destination.read_bytes())
                    assert bits[0] == bits[1], (label, 'observation changed result bits')
                    phases = [list(map(int, line.split()[1:])) for line in text.splitlines() if line.startswith('PHASE ')]
                    sums = [list(map(int, line.split()[1:])) for line in text.splitlines() if line.startswith('SUM ')]
                    state = next(list(map(int, line.split()[1:])) for line in text.splitlines() if line.startswith('RESULT '))
                    if target == 'host':
                        detail = out/(label+'-detail');detail.mkdir()
                        detail_bits = out/(label+'-detail.bin')
                        run(label+'-detail', [wsl_path(out/'host-observed'), wsl_path(fixture),
                            wsl_path(detail_bits), wsl_path(detail), mode])
                        assert detail_bits.read_bytes() == bits[0], (label, 'dumps changed result bits')
                    result['checks'].append(dict(target=target, case=index, mode=mode,
                        status=state[0], crossings=state[1], inliers=state[2], full_result_bits_equal=True,
                        phase_cpu_wall_ns=phases, sum_cpu_wall_ns=sums, capture_io_excluded=True))
        assert all(sha(p) == h for p, h in before.items())
        assert all(sha(p) == h for p, h in fixture_before.items())
        result.update(status='GEOMETRY_OBSERVATION_EXACT_PHASE_COSTS_PASS_NOT_BOARD',
                      production_sources_and_private_inputs_stable=True,
                      sum_stage_names=['allocation','column_prefix','row_prefix',
                                       'reduction_consumer' if args.fused else 'reduction'],
                      phase_names=['setup','grayscale_mask','contrast_sum','contrast','horizontal_sums',
                                   'horizontal_score','vertical_sums','vertical_score','search','fit','unused','end'])
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
