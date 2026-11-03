"""Exercise ISA-bound firmware snapshot rejection against an isolated fixture."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    root=Path(__file__).resolve().parents[1];out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    fixture=out/'fixture';fixture.mkdir()
    names=['bootloader','mac_selftest','mac_benchmark','xiangqi_sparse_eval_selftest','xiangqi_fb_demo']
    paths=['scripts/'+n for n in ['build_snapshot.ps1','clock_policy.ps1','timing_scope.ps1','riscv_toolchain.ps1']]
    paths+=['artifacts/'+n+ext for n in names for ext in ['.bin','.elf','.build.json']]
    paths+=['artifacts/bootrom.hex','rtl/cpu/source.json','rtl/cpu/emit-config.json','rtl/cpu/CoreTop.sv']
    for n in paths:
        dst=fixture/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,dst)
    child=out/'check.ps1';child.write_text("param([string]$Root)\n$ErrorActionPreference='Stop'\n. (Join-Path $Root 'scripts/build_snapshot.ps1')\nAssert-FpgaFirmware $Root\nWrite-Output 'ISA_BOUND_FIRMWARE_SNAPSHOT_PASS'\n",encoding='utf-8')
    metadata=fixture/'artifacts/bootloader.build.json';original=metadata.read_bytes()
    cases=[('zbc-valid',True,None),('old-validation-label',False,'label'),('wrong-march',False,'march'),('extra-validation-suffix',False,'suffix'),('rtl-mismatch',False,'rtl'),('emit-mismatch',False,'emit'),('rom-mismatch',False,'rom')]
    rows=[]
    for name,expected,mutation in cases:
        restore={}
        if mutation in ('label','march','suffix'):
            restore[metadata]=original;m=json.loads(original)
            if mutation=='label':m['code_validation']['Result']='RV32IMA mnemonic/width whitelist; no vlenb; rodata excluded by linker symbols'
            elif mutation=='march':m['march']='rv32ima_zicsr_zifencei'
            else:m['code_validation']['Result']+=' invalid'
            metadata.write_text(json.dumps(m),encoding='utf-8')
        elif mutation:
            target=fixture/({'rtl':'rtl/cpu/CoreTop.sv','emit':'rtl/cpu/emit-config.json','rom':'artifacts/bootrom.hex'}[mutation]);restore[target]=target.read_bytes()
            if mutation=='rom':target.write_bytes(b'00000000\n'+restore[target].split(b'\n',1)[1])
            else:target.write_bytes(restore[target]+b'\n')
        r=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(child),'-Root',str(fixture)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        (out/(name+'.log')).write_bytes(r.stdout)
        for target,data in restore.items():target.write_bytes(data)
        assert (r.returncode==0)==expected,(name,r.stdout.decode(errors='replace')[-1500:])
        rows.append(dict(case=name,expected_pass=expected,exit_code=r.returncode,log_sha256=hashlib.sha256(r.stdout).hexdigest()))
    (out/'result.json').write_text(json.dumps(dict(status='ISA_BOUND_FIRMWARE_SNAPSHOT_POSITIVE_AND_SIX_NEGATIVE_CASES_PASS',cases=rows),indent=2)+'\n',encoding='utf-8')
    print('ISA_BOUND_FIRMWARE_SNAPSHOT_TESTS_PASS cases='+str(len(rows)))
if __name__=='__main__':main()
