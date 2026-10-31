"""Same-process, alternating geometry benchmark; never product latency acceptance."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shlex
import statistics
import struct
import subprocess
import zlib
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    choices=['pn08','compact-selective','seed']
    parser.add_argument('--baseline',choices=choices,default='compact-selective')
    parser.add_argument('--candidate',choices=choices,default='seed')
    parser.add_argument('--targets',choices=['host','host,rv32'],default='host,rv32')
    parser.add_argument('--sanitizer',action='store_true')
    parser.add_argument('--private-fixture',type=Path,action='append')
    args=parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);assert not out.exists();out.mkdir(parents=True)
    source=ROOT/'linux/picture_new/geometry_locality.c'
    includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader',
              'artifacts/vision-model-20261020-adapter/runtime']
    files={source,ROOT/'linux/picture_new/test_geometry_pair.c',Path(__file__).resolve(),
           ROOT/'artifacts/vision-model-20261020/geometry/geometry_reference.c',ROOT/'sw/bootloader/crc32_fast.c'}
    for directory in includes:files.update((ROOT/directory).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    rng_file=ROOT/'build/picture-merge-20261023/native-models/refinement_rng.bin'
    rng_bytes=rng_file.read_bytes()
    assert rng_bytes[:8]==b'XQRNG1\0\0'
    count,crc=struct.unpack('<II',rng_bytes[8:16]);rng=rng_bytes[16:]
    assert count==len(rng)==91*240*4 and zlib.crc32(rng)==crc
    fixtures={}
    coarse=struct.pack('<8d',150,100,1050,100,1050,620,150,620)
    for label in ['blank','crosses']:
        rgb=bytearray(b'\xff')*(1280*720*3)
        if label=='crosses':
            for gy in range(9):
                for gx in range(10):
                    x,y=150+gx*100,100+gy*65
                    for d in range(-19,20):
                        for t in range(-1,2):
                            for xx,yy in [(x+d,y+t),(x+t,y+d)]:
                                at=(yy*1280+xx)*3;rgb[at:at+3]=b'\0\0\0'
        fixture=out/(label+'.bin')
        fixture.write_bytes(b'XQGEOM1'+b'\0'+struct.pack('<I',0)+coarse+rng+rgb)
        fixtures[label]=fixture
    private_before={}
    for index,item in enumerate(args.private_fixture or []):
        private=workspace_path(item);private_before[private]=sha(private)
        fixtures['private-'+str(index)]=private
    checks=[]
    result=dict(status='FAILED_PRESERVED',hardware_used=False,source_sha256=before,
        baseline=args.baseline,candidate=args.candidate,clock='CLOCK_PROCESS_CPUTIME_ID_and_MONOTONIC',
        alternating_order=True,warmup_each_variant=True,repeats_per_variant=4,
        private_fixture_used=bool(args.private_fixture),private_input_hash_published=False,
        no_pixel_probes=True,internal_benchmark_concurrency=False,not_whole_product_latency=True)
    def run(label,argv,seconds=90,expected=0):
        with (out/(label+'.log')).open('xb') as log:
            proc=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert proc.returncode==expected,(label,proc.returncode)
        return (out/(label+'.log')).read_text(errors='replace')
    try:
        for target in args.targets.split(',')+(['sanitizer'] if args.sanitizer else []):
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            flags=['-std=c11','-O2','-ffp-contract=off','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror']
            if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
            if target=='sanitizer':flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            flags+=['-I'+wsl_path(ROOT/d) for d in includes]
            objects=[]
            for prefix,mode in [('baseline',args.baseline),('candidate',args.candidate)]:
                renamed=['-Dxnp_'+n+'='+prefix+'_'+n for n in ['filter_candidates','load_rng','coarse','refine','refine_full','finish']]
                renamed+=['-Dxq_training_geometry_cli='+prefix+'_training_cli']
                options=['-DXQ_GEOMETRY_GRAY_TABLE=1','-DXQ_GEOMETRY_FAST=1','-DXQ_GEOMETRY_ARITH=1',
                    '-DXQ_GEOMETRY_COMPACT='+str(int(mode!='pn08')),
                    '-DXQ_GEOMETRY_SELECTIVE='+str(int(mode!='pn08')),
                    '-DXQ_GEOMETRY_SEED_BOUND='+str(int(mode=='seed'))]
                obj=out/(target+'-'+prefix+'.o');objects.append(obj)
                run(target+'-'+prefix+'-build',[cc,*flags,*renamed,*options,'-c',wsl_path(source),'-o',wsl_path(obj)])
            binary=out/(target+'-pair')
            run(target+'-link',[cc,*flags,wsl_path(ROOT/'linux/picture_new/test_geometry_pair.c'),
                *[wsl_path(p) for p in objects],wsl_path(ROOT/'sw/bootloader/crc32_fast.c'),
                '-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
            prefix=['qemu-riscv32'] if target=='rv32' else []
            for case,fixture in fixtures.items():
                text=run(target+'-'+case,[*prefix,wsl_path(binary),wsl_path(fixture)])
                assert 'GEOMETRY_PAIR_FULL_CORNERS_STATISTICS_EQUAL' in text
                if case in ['blank','crosses']:assert 'GEOMETRY_PAIR_REFERENCE okay='+str(int(case=='crosses')) in text
                samples={0:[],1:[]}
                for variant,cpu,wall in re.findall(r'GEOMETRY_PAIR_NS repeat=\d+ variant=(\d+) cpu=(\d+) wall=(\d+)',text):
                    samples[int(variant)].append(dict(cpu=int(cpu),wall=int(wall)))
                assert all(len(v)==4 for v in samples.values())
                checks.append(dict(target=target,case=case,full_corners_statistics_bits_equal=True,
                    samples_ns=samples,median_cpu_ns={k:int(statistics.median(x['cpu'] for x in v)) for k,v in samples.items()},
                    sanitizer_times_excluded_from_speed_ranking=target=='sanitizer',binary_sha256=sha(binary)))
            for kind in ['corner','stats']:
                text=run(target+'-negative-'+kind,[*prefix,wsl_path(binary),wsl_path(fixtures['crosses']),'--negative-'+kind],expected=3)
                assert 'GEOMETRY_PAIR_MISMATCH kind=' in text
        assert all(sha(ROOT/f)==h for f,h in before.items())
        assert all(sha(p)==h for p,h in private_before.items())
        result.update(status='GEOMETRY_PAIRED_ALTERNATING_FULL_BITS_NEGATIVE_CONTROLS_PASS_NOT_BOARD',
            source_stable=True,private_input_stable=True,corner_and_statistics_mutants_rejected=True,
            rng_sha256=sha(rng_file),checks=checks)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
