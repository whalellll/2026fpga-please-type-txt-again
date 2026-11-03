"""Exercise the real product main loop with explicit off-board events."""
import argparse,hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def wsl(p):
    s=p.resolve().as_posix()
    return '/mnt/'+s[0].lower()+s[2:]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-ref')
    args=parser.parse_args()
    from picture_workspace import workspace_path
    assert args.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(args.output);assert not out.exists()
    out.mkdir(parents=True)
    sources=[ROOT/'linux/xinyi_board/main.c',ROOT/'linux/xinyi_board/main_loop_test.c',
             ROOT/'linux/xinyi_board/coach_task.c',ROOT/'linux/xinyi_board/coach_diagnostic_test.c',
             Path(__file__).resolve()]
    include=['linux/xinyi_board','linux/xinyi','linux/pikafish','linux/vision',
             'linux/voice_ctc','linux/voice_speech','linux/voice','linux/mac_accel',
             'linux/picture_new','sw/xiangqi','sw/bootloader']
    headers={p for name in include for p in (ROOT/name).rglob('*.h')}
    before={p.relative_to(ROOT).as_posix():sha(p) for p in [*sources,*headers]}
    rows=[]
    def run(argv):
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',*argv],capture_output=True,timeout=30)
        assert r.returncode==0,(argv,r.stdout[-1000:],r.stderr[-1000:])
        return r
    def build(name,cc,flags,source):
        common=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-builtin-printf',*flags,
                *[a for p in include for a in ('-I',wsl(ROOT/p))]]
        obj=out/(name+'.o');exe=out/name
        run([cc,*common,'-Dmain=xinyi_product_entry','-c',wsl(source),'-o',wsl(obj)])
        run([cc,*common,wsl(sources[1]),wsl(obj),'-Wl,--wrap=memcmp,--wrap=printf,--wrap=__printf_chk','-o',wsl(exe)])
        return exe
    if args.baseline_ref:
        old=out/'baseline-main.c'
        old.write_bytes(subprocess.check_output(['git','-C',str(ROOT),'show',
                                                args.baseline_ref+':linux/xinyi_board/main.c'],timeout=20))
        exe=build('baseline-host','gcc',[],old)
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','prlimit',
                          '--core=0','--',wsl(exe)],capture_output=True,timeout=10)
        (out/'baseline.log').write_bytes(r.stdout+r.stderr)
        assert r.returncode and b'whole_compares' in r.stderr,(r.returncode,r.stdout,r.stderr)
        rows.append(dict(name='baseline_full_state_scan',expected_failure=True,source_ref=args.baseline_ref,
                         source_sha256=sha(old),returncode=r.returncode))
    for name,cc,flags in [('host','gcc',[]),('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc',
                                         ['-march=rv32ima','-mabi=ilp32','-mstrict-align','-static'])]:
        exe=build(name,cc,flags,sources[0])
        r=run([*(['qemu-riscv32'] if name=='rv32' else []),wsl(exe)])
        assert b'PRODUCT_MAIN_LOOP_DIRTY_EVENTS_THROTTLE_RETENTION_CANCEL_AND_NO_LOG_SCAN_PASS_NOT_BOARD' in r.stdout
        assert b'PRODUCT_PHOTO_PRESENT_AFTER_SUBMIT_ONCE_CANCEL_AND_INVALID_CLOCK_PASS_NOT_BOARD' in r.stdout
        (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
        rows.append(dict(name=name,pass_=True,executable_sha256=sha(exe)))
        diagnostic=out/('stage-filter-'+name)
        run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread',
             '-ffunction-sections','-fdata-sections',*flags,
             *[a for p in include for a in ('-I',wsl(ROOT/p))],wsl(sources[3]),
             '-Wl,--gc-sections','-o',wsl(diagnostic)])
        checked=run([*(['qemu-riscv32'] if name=='rv32' else []),wsl(diagnostic)])
        assert b'COACH_REAL_PIPE_STAGE_FILTER_ONLY_COUNTERS_NO_LIVE_TEXT_PASS_NOT_BOARD' in checked.stdout
        (out/('stage-filter-'+name+'.log')).write_bytes(checked.stdout+checked.stderr)
        rows.append(dict(name='stage-filter-'+name,pass_=True,executable_sha256=sha(diagnostic)))
    assert before=={p.relative_to(ROOT).as_posix():sha(p) for p in [*sources,*headers]}
    row=dict(status='REAL_MAIN_LOOP_HOST_RV32_PASS_NOT_BOARD',hardware_used=False,
             actual_inference=False,platform_runtime_renderer='explicit event fixtures',
             display_submit_timing_verified=True,invalid_clock_rejected=True,
             cancel_never_reported_as_capture_completion=True,
             tests=rows,source_sha256=before)
    (out/'result.json').write_text(json.dumps(row,indent=2)+'\n')
    print(row['status'])

if __name__=='__main__':main()
