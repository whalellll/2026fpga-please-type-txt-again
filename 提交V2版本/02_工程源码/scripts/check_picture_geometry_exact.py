"""Check exact geometry arithmetic and mask counts on host, RV32 and sanitizers."""
from pathlib import Path
import argparse,hashlib,json,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build');o=workspace_path(a.output);assert not o.exists();o.mkdir(parents=True)
    names=['linux/picture_new/geometry_exact.h','linux/picture_new/test_geometry_exact.c','scripts/check_picture_geometry_exact.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={p:sha(ROOT/p) for p in names};checks=[]
    for target in ['host','rv32','sanitizer']:
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc';flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off']
        if target=='rv32':flags+=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align']
        if target=='sanitizer':flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
        exe=o/target
        with (o/(target+'-build.log')).open('xb') as f:r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',cc,*flags,wsl_path(ROOT/names[1]),'-lm','-o',wsl_path(exe)],stdout=f,stderr=subprocess.STDOUT,timeout=60)
        assert r.returncode==0,(target,(o/(target+'-build.log')).read_text()[-2000:])
        with (o/(target+'-run.log')).open('xb') as f:r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe)],stdout=f,stderr=subprocess.STDOUT,timeout=120)
        assert r.returncode==0,(target,(o/(target+'-run.log')).read_text()[-2000:])
        checks.append(dict(target=target,result=(o/(target+'-run.log')).read_text().strip()))
    assert all(sha(ROOT/p)==s for p,s in before.items())
    (o/'result.json').write_text(json.dumps(dict(status='GEOMETRY_EXACT_DIV_ADD_MASK_HOST_RV32_ASAN_UBSAN_PASS_NOT_BOARD',source_sha256=before,checks=checks,hardware_used=False),indent=2)+'\n')
    print('GEOMETRY_EXACT_DIV_ADD_MASK_HOST_RV32_ASAN_UBSAN_PASS_NOT_BOARD')
if __name__=='__main__':main()
