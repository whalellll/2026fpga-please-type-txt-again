"""Prepare GCC9/GCC16 algorithm comparisons with the same Linux POSIX port.

No device access. Unchanged official algorithm files, no LTO, RV32IMA softfloat.
GCC16 is the verified bare-metal compiler; only its five algorithm objects are
linked into the existing musl9 runtime. Compiler labels describe this mixture.
"""
from pathlib import Path
import argparse, gzip, hashlib, json, subprocess
from verify_xinyi_elf import inspect

ROOT=Path(__file__).resolve().parents[1]
NAMES=['core_main','core_list_join','core_matrix','core_state','core_util']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def wsl(p):
    s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--gcc16',type=Path,default=Path('D:/p17-gcc16-lto/native/bin/riscv32-unknown-elf-gcc.exe'))
    ap.add_argument('--distribution',default='Ubuntu-22.04')
    a=ap.parse_args();out=a.output.resolve()
    assert out.is_relative_to(ROOT/'build') and not out.exists()
    assert sha(a.gcc16)=='31f705044780855851e69609aec27a16d71969f51bac1d7a55d03e4f0aad1dea'
    out.mkdir(parents=True);(out/'obj').mkdir()
    sources=[ROOT/'sw/coremark'/f'{n}.c' for n in NAMES]
    sources += [ROOT/'sw/coremark/coremark.h',ROOT/'linux/xinyi/coremark/benchmark.c',ROOT/'linux/xinyi/coremark/core_portme.h',Path(__file__)]
    before={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    commands=[]
    def run(argv,name):
        p=subprocess.run(list(map(str,argv)),capture_output=True,timeout=60)
        (out/(name+'.log')).write_bytes(p.stdout+p.stderr)
        commands.append(dict(name=name,exit_code=p.returncode,log_sha256=sha(out/(name+'.log'))))
        assert p.returncode==0,(p.stdout+p.stderr).decode(errors='replace')[-2000:]
    common=['wsl.exe','-d',a.distribution,'--']
    cc='/opt/toolchain/bin/riscv32-linux-musl-gcc'
    flags=['-std=c11','-O2','-Wall','-Wextra','-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mstrict-align',
        '-I',ROOT/'sw/coremark','-include',ROOT/'linux/xinyi/coremark/core_portme.h',
        '-DCOMPILER_FLAGS="algorithm GCC16.2 -O2 rv32ima; POSIX port/libc GCC9.4; CLOCK_MONOTONIC_RAW"']
    objects=[]
    for n in NAMES:
        obj=out/'obj'/f'{n}.o';objects.append(obj)
        run([a.gcc16,*flags,*(['-Dmain=xy_cm_upstream_main'] if n=='core_main' else []),'-c',ROOT/'sw/coremark'/f'{n}.c','-o',obj],n)
    run([*common,cc,'-std=c11','-D_POSIX_C_SOURCE=200809L','-O2','-Wall','-Wextra','-march=rv32ima',
        '-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mstrict-align','-static',
        '-I',wsl(ROOT/'sw/coremark'),'-include',wsl(ROOT/'linux/xinyi/coremark/core_portme.h'),
        wsl(ROOT/'linux/xinyi/coremark/benchmark.c'),*map(wsl,objects),'-o',wsl(out/'xinyi-coremark-debug')],'link')
    run([*common,'/opt/toolchain/bin/riscv32-linux-musl-strip','-o',wsl(out/'xinyi-coremark'),wsl(out/'xinyi-coremark-debug')],'strip')
    before_elf,final=inspect(out/'xinyi-coremark-debug'),inspect(out/'xinyi-coremark')
    assert before_elf['allocated']==final['allocated'] and before_elf['entry']==final['entry']
    assert before=={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    (out/'xinyi-coremark.gz').write_bytes(gzip.compress((out/'xinyi-coremark').read_bytes(),mtime=0))
    record=dict(status='GCC16_ALGORITHM_LINUX_COMPARISON_PREPARED_NOT_BOARD',algorithm_compiler_sha256=sha(a.gcc16),
        algorithm_flags=list(map(str,flags)),port='unchanged GCC9 POSIX CLOCK_MONOTONIC_RAW and musl libc',
        source_sha256=before,sha256=final['sha256'],bytes=final['bytes'],gzip_sha256=sha(out/'xinyi-coremark.gz'),
        static_rv32ima_flags0=True,strip_allocated_equal=True,hardware_tested=False,commands=commands)
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'])
if __name__=='__main__':main()
