"""Test benchmark clock initialization/failure handling without a board."""
from pathlib import Path
import argparse,hashlib,json,subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--bench',type=Path,required=True)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    w=lambda p:'/mnt/'+p.resolve().as_posix()[0].lower()+p.resolve().as_posix()[2:]
    mock=out/'mock.c';mock.write_text('''#define _POSIX_C_SOURCE 200809L
#include <time.h>
#include <stdlib.h>
int clock_getres(clockid_t id, struct timespec *t){(void)id;const char *s=getenv("CLOCK_TEST");int n=s?atoi(s):0;t->tv_sec=0;t->tv_nsec=n;return n==-2?-1:0;}
int main(void){return 7;}
''')
    records=[]
    def run(name,args,expected):
        p=subprocess.run(['wsl','-d','pikafish-verify','--']+args,capture_output=True)
        log=out/(name+'.log');log.write_bytes(p.stdout+p.stderr)
        assert p.returncode==expected,(name,p.returncode,p.stderr)
        records.append(dict(name=name,command=args,exit=p.returncode,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
    source=ROOT/'linux/voice/xqvoice_bench_clock.c'
    run('compile',['gcc','-std=c11','-Wall','-Wextra','-Werror',w(source),w(mock),'-o',w(out/'mock')],0)
    for value,code in [('21',7),('4000000',90),('0',90),('-1',90),('-2',90)]:
        run('clock-'+value,['env','CLOCK_TEST='+value,w(out/'mock')],code)
    for value,code in [('linux',2),('bad',90)]:
        run('rv32-'+value,['env','NNUE_CLOCKSOURCE='+value,'qemu-riscv32',w(a.bench)],code)
    result=dict(status='VOICE_BENCH_CLOCK_PREINIT_AND_COARSE_FAILURE_REJECTION_PASS_NOT_BOARD',
                records=records,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                bench_sha256=hashlib.sha256(a.bench.read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])

if __name__=='__main__':main()
