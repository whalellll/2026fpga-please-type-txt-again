"""Exact prefix shape/tail/restore tests, synthetic sectors and original bytes."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['candidate','original-entry','loader','output']:ap.add_argument('--'+n,required=True,type=Path)
    a=ap.parse_args();out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    c=a.candidate.resolve();source=ROOT/'linux/xinyi_board/boot/test_console_prefix.c';support=c/'support'
    production=next((c/'obj').glob('*_fat_boot_prefix.c.o'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs=[source,production,a.original_entry,a.loader,support/'fat_boot_prefix.c',support/'fat_boot_prefix.h',support/'fat_camera.h',support/'fat_ro.h',Path(__file__)]
    before={str(p.resolve()):sha(p) for p in inputs};rows=[]
    def run(name,args,good=True):
        q=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',*args],capture_output=True,timeout=40)
        (out/(name+'.log')).write_bytes(q.stdout+q.stderr)
        assert (q.returncode==0)==good,(name,q.returncode,q.stderr[-1500:]);return q
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+wsl_path(support)]
    for target in ['host','sanitizer','rv32']:
        cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
        extra=['-static','-march=rv32ima','-mabi=ilp32'] if target=='rv32' else []
        if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie']
        obj=production if target=='rv32' else support/'fat_boot_prefix.c';exe=out/target
        run(target+'-build',[cc,*flags,*extra,wsl_path(source),wsl_path(obj),'-o',wsl_path(exe)])
        q=run(target,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),wsl_path(a.original_entry),wsl_path(a.loader)])
        assert b'EXACT_ENTRY_PREFIX_TAIL_METADATA_FAILURE_RESTORE_PASS' in q.stdout;rows.append(target)
    mutant=out/'wrong-tail.c';s=(support/'fat_boot_prefix.c').read_text();needle='memcpy(sector,full+i*512u,512);';assert s.count(needle)==1
    mutant.write_text(s.replace(needle,needle+'if(i+1u==blocks && (bytes&511u))memset(sector+(bytes&511u),0,512u-(bytes&511u));'))
    run('mutant-build',['cc',*flags,wsl_path(source),wsl_path(mutant),'-o',wsl_path(out/'mutant')])
    q=run('mutant',['sh','-c','ulimit -c 0\nexec '+shlex.join([wsl_path(out/'mutant'),wsl_path(a.original_entry),wsl_path(a.loader)])],False)
    assert b'memcmp(disk,expected' in q.stderr
    assert before=={str(p.resolve()):sha(p) for p in inputs}
    result=dict(status='PASS',hardware_used=False,sd_written=False,source_sha256=before,targets=rows,
        installer_sha256=sha(c/'entry-installer.bin'),same_gcc16_prefix_object_sha256=sha(production),wrong_tail_negative_control=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('EXACT_PREFIX_HOST_SANITIZER_SAME_GCC16_RV32_AND_WRONG_TAIL_NEGATIVE_PASS')


if __name__=='__main__':main()
