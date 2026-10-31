"""Exact grid planning differential checks; no board access or quality claim."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    paths=['linux/picture_new/board_grid_recovery.c','linux/picture_new/board_grid_recovery.h',
           'linux/picture_new/test_grid_plan.c','linux/picture_new/test_grid_recovery.c',
           'linux/vision/xq_roi.c','scripts/check_picture_grid_plan.py']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={p:sha(ROOT/p) for p in paths};rows=[]
    result=dict(status='FAILED_PRESERVED',sources_sha256=before,hardware_used=False,runs=rows)
    def run(name,args):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5','180',*args],stdout=f,stderr=subprocess.STDOUT,timeout=200)
        rows.append(dict(name=name,exit=r.returncode));assert not r.returncode,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
    try:
        includes=['-I'+wsl_path(ROOT/p) for p in ['linux/picture_new','linux/vision','sw/xiangqi','sw/bootloader']]
        flags=['-std=c11','-O2','-ffp-contract=off','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror']
        for target in ['host','rv32','sanitizers']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizers':extra=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all','-no-pie']
            prefix=['qemu-riscv32'] if target=='rv32' else []
            for flag in [0,1]:
                name=target+'-'+str(flag);exe=out/(name+'-plan')
                run(name+'-plan-build',[cc,*flags,*extra,*includes,'-DXQ_GRID_PLAN_FAST='+str(flag),wsl_path(ROOT/'linux/picture_new/test_grid_plan.c'),'-lm','-o',wsl_path(exe)])
                run(name+'-plan',[*prefix,wsl_path(exe),wsl_path(out/(name+'-fields.bin'))])
                exe=out/(name+'-recovery')
                run(name+'-recovery-build',[cc,*flags,*extra,*includes,'-DXQ_GRID_PLAN_FAST='+str(flag),*[wsl_path(ROOT/p) for p in ['linux/picture_new/test_grid_recovery.c','linux/picture_new/board_grid_recovery.c','linux/vision/xq_roi.c']],'-Wl,--wrap=calloc,--gc-sections','-lm','-o',wsl_path(exe)])
                run(name+'-recovery',[*prefix,wsl_path(exe),'--synthetic'])
            assert (out/(target+'-0-fields.bin')).read_bytes()==(out/(target+'-1-fields.bin')).read_bytes(),target
        assert (out/'host-0-fields.bin').read_bytes()==(out/'rv32-0-fields.bin').read_bytes()
        assert all(sha(ROOT/p)==h for p,h in before.items())
        result.update(status='GRID_PLAN_HOST_RV32_SANITIZERS_PASS_NOT_BOARD',source_stable=True,internal_cases_per_config=96,full_recovery_guards=True,flag_zero_one_fields_and_order_equal=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
