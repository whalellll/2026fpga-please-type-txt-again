"""Validate the actual optional search loop against independent brute force."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);assert not out.exists();out.mkdir(parents=True)
    files=['linux/picture_new/geometry_locality.c','linux/picture_new/test_geometry_seed.c',
           'scripts/check_picture_geometry_seed.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={f:sha(ROOT/f) for f in files}
    text=(ROOT/files[0]).read_text()
    begin='/* XQGEOM_SEARCH_WINDOW_BEGIN */\n';end='/* XQGEOM_SEARCH_WINDOW_END */'
    assert text.count(begin)==text.count(end)==1
    fragment=text.split(begin)[1].split(end)[0]
    (out/'search.inc').write_text(fragment,newline='\n')
    assert fragment.count('upper<seed_bound')==1
    (out/'search-wrong-tie.inc').write_text(fragment.replace('upper<seed_bound','upper<=seed_bound'),newline='\n')
    checks=[]
    def run(name,argv,seconds=90,fail=False):
        with (out/(name+'.log')).open('xb') as log:
            proc=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert (proc.returncode!=0 if fail else proc.returncode==0),(name,proc.returncode)
        return (out/(name+'.log')).read_text(errors='replace')
    flags=['-std=c11','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror']
    for target in ['host','rv32','sanitizer']:
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
        options=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
        if target=='sanitizer':options+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        for selected in [0,1]:
            name=target+'-'+str(selected);binary=out/name
            run(name+'-build',[cc,*flags,*options,'-DXQ_GEOMETRY_SEED_BOUND='+str(selected),
                '-DGEOMETRY_SEARCH_WINDOW_SOURCE="'+wsl_path(out/'search.inc')+'"',
                wsl_path(ROOT/files[1]),'-lm','-o',wsl_path(binary)])
            t=run(name,(['qemu-riscv32'] if target=='rv32' else [])+[wsl_path(binary)])
            assert 'GEOMETRY_SEED_ACTUAL_SEARCH_FROZEN_BRUTE_BITS_TIES_EMPTY_SPECIALS_PASS' in t
            checks.append(dict(target=target,selected=selected,result=t.strip()))
    bad=out/'wrong-tie'
    run('wrong-tie-build',['gcc',*flags,'-DGEOMETRY_SEARCH_WINDOW_SOURCE="'+wsl_path(out/'search-wrong-tie.inc')+'"',
        wsl_path(ROOT/files[1]),'-lm','-o',wsl_path(bad)])
    t=run('wrong-tie',[wsl_path(bad)],fail=True)
    assert 'Assertion' in t or 'assertion' in t
    assert all(sha(ROOT/f)==h for f,h in before.items())
    result=dict(status='GEOMETRY_SEED_ACTUAL_LOOP_BRUTE_BITS_HOST_RV32_SANITIZERS_TIE_MUTANT_PASS_NOT_BOARD',
        hardware_used=False,photos_accessed=False,source_sha256=before,source_stable=True,
        checks=checks,strict_tie_mutant_rejected=True,performance_measured=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
