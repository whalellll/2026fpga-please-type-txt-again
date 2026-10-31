"""Synthetic word-I/O ordering checks; no board or physical aperture access."""
from pathlib import Path
import argparse,hashlib,json,subprocess,shlex
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build');o=workspace_path(a.output);assert not o.exists();o.mkdir(parents=True)
    names=['linux/mac_accel/kernel/pango_mac_io32.h','linux/mac_accel/test_io32.c','linux/mac_accel/test_io32_bulk.c','scripts/check_picture_io32_bulk.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={p:sha(ROOT/p) for p in names};checks=[]
    variants=[('baseline-host','host','test_io32.c',[],True),('baseline-rv32','rv32','test_io32.c',[],True),
        ('bulk-host','host','test_io32_bulk.c',[],True),('bulk-rv32','rv32','test_io32_bulk.c',[],True),
        ('bulk-sanitizer','sanitizer','test_io32_bulk.c',[],True),
        ('omit-begin','host','test_io32_bulk.c',['-DPANGO_TEST_OMIT_BEGIN'],False),
        ('omit-end','host','test_io32_bulk.c',['-DPANGO_TEST_OMIT_END'],False)]
    for name,target,source,extra,positive in variants:
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc';flags=['-std=c11','-O2','-Wall','-Wextra','-Werror',*extra]
        if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizer':flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
        exe=o/name
        with (o/(name+'-build.log')).open('xb') as f:r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',cc,*flags,wsl_path(ROOT/'linux/mac_accel'/source),'-o',wsl_path(exe)],stdout=f,stderr=subprocess.STDOUT,timeout=60)
        assert r.returncode==0,(name,(o/(name+'-build.log')).read_text()[-2000:])
        args=(['qemu-riscv32'] if target=='rv32' else [])+[wsl_path(exe)]
        with (o/(name+'-run.log')).open('xb') as f:r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=60)
        assert (r.returncode==0)==positive,(name,r.returncode)
        checks.append(dict(name=name,expected_success=positive,exit=r.returncode))
    assert all(sha(ROOT/p)==s for p,s in before.items())
    (o/'result.json').write_text(json.dumps(dict(status='WORD_SAFE_BULK_BOUNDARIES_HOST_RV32_SANITIZERS_NEGATIVE_CONTROLS_PASS_NOT_BOARD',sources_sha256=before,checks=checks,hardware_used=False),indent=2)+'\n')
    print('WORD_SAFE_BULK_BOUNDARIES_HOST_RV32_SANITIZERS_NEGATIVE_CONTROLS_PASS_NOT_BOARD')
if __name__=='__main__':main()
