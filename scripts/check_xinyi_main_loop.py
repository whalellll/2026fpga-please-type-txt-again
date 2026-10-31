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
    parser.add_argument('--gui-double-buffer',action='store_true')
    parser.add_argument('--ui-feedback',action='store_true')
    parser.add_argument('--home-r13',action='store_true')
    parser.add_argument('--battle-r17',action='store_true')
    parser.add_argument('--metric-deltas',action='store_true')
    parser.add_argument('--fast-nav',action='store_true')
    parser.add_argument('--idle-nav-case',action='store_true')
    parser.add_argument('--expect-front-write',action='store_true')
    args=parser.parse_args()
    assert not args.metric_deltas or args.battle_r17
    assert not args.ui_feedback or args.gui_double_buffer
    assert not args.expect_front_write or (args.gui_double_buffer and not args.baseline_ref)
    assert not args.baseline_ref or not args.gui_double_buffer
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
    rows=[];compiled=set()
    def run(argv):
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',*argv],capture_output=True,timeout=30)
        assert r.returncode==0,(argv,r.stdout[-1000:],r.stderr[-1000:])
        return r
    def dependencies(name,command):
        data=run([*command,'-MM']).stdout
        (out/(name+'-dependencies.d')).write_bytes(data)
        prefix=wsl(ROOT)+'/'
        for token in data.decode().replace('\\\n',' ').split():
            if token.startswith(prefix):
                path=(ROOT/token[len(prefix):]).resolve()
                assert path.is_relative_to(ROOT)
                compiled.add(path.relative_to(ROOT).as_posix())
    def build(name,cc,flags,source):
        common=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-builtin-printf',*flags,
                '-DXINYI_GUI_DOUBLE_BUFFER='+str(int(args.gui_double_buffer)),
                '-DXINYI_UI_FEEDBACK='+str(int(args.ui_feedback)),
                '-DXINYI_HOME_R13='+str(int(args.home_r13)),
                '-DXINYI_BATTLE_R17='+str(int(args.battle_r17)),
                '-DXINYI_GUI_METRIC_DELTAS='+str(int(args.metric_deltas)),
                '-DXINYI_GUI_FAST_NAV_R21='+str(int(args.fast_nav)),
                '-DXINYI_TEST_IDLE_NAV='+str(int(args.idle_nav_case)),
                *[a for p in include for a in ('-I',wsl(ROOT/p))]]
        obj=out/(name+'.o');exe=out/name
        dependencies(name+'-product',[cc,*common,'-Dmain=xinyi_product_entry',wsl(source)])
        dependencies(name+'-fixture',[cc,*common,wsl(sources[1])])
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
        if args.expect_front_write:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','prlimit','--core=0','--',wsl(exe)],capture_output=True,timeout=10)
            (out/'old-front-write.log').write_bytes(r.stdout+r.stderr)
            assert r.returncode and b'fb!=pixels[front_page]' in r.stderr,(r.returncode,r.stderr)
            (out/'result.json').write_text(json.dumps(dict(status='ORIGINAL_MAIN_FRONT_BUFFER_WRITE_REPRODUCED_NOT_CANDIDATE_PASS',sources_sha256=before,hardware_used=False),indent=2)+'\n')
            print('ORIGINAL_MAIN_FRONT_BUFFER_WRITE_REPRODUCED_NOT_CANDIDATE_PASS');return
        r=run([*(['qemu-riscv32'] if name=='rv32' else []),wsl(exe)])
        assert b'PRODUCT_MAIN_LOOP_DIRTY_EVENTS_THROTTLE_RETENTION_CANCEL_AND_NO_LOG_SCAN_PASS_NOT_BOARD' in r.stdout
        assert b'PRODUCT_PHOTO_PRESENT_AFTER_SUBMIT_ONCE_CANCEL_AND_INVALID_CLOCK_PASS_NOT_BOARD' in r.stdout
        if args.gui_double_buffer:assert b'PRODUCT_BACK_PAGE_RENDER_FRONT_UNCHANGED_DELAYED_FLIP_DIRTY_RETAINED_PASS_NOT_BOARD' in r.stdout
        if args.ui_feedback:assert b'PRODUCT_REAL_MAIN_UI_DOWN_RELEASE_PRESENT_BEFORE_SINGLE_ACTION_PASS_NOT_BOARD' in r.stdout
        if args.battle_r17:assert b'PRODUCT_R17_REAL_MAIN_REG_STATUS_FRAME_TIME_AND_SUBMIT_AFTER_PRESENT_PASS_NOT_BOARD' in r.stdout
        if args.battle_r17:assert b'PRODUCT_R17_RESTART_INTERNAL_HOME_NEVER_RENDERED_DIRTY_PRESERVED_GAME_RETURN_PASS_NOT_BOARD' in r.stdout
        if args.idle_nav_case:assert b'PRODUCT_R21_IDLE_NAV_COALESCED_CANCEL_VISIBLE_DIRTY_AND_TARGET_PASS' in r.stdout
        (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
        rows.append(dict(name=name,pass_=True,executable_sha256=sha(exe)))
        diagnostic=out/('stage-filter-'+name)
        diagnostic_command=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread',
             '-ffunction-sections','-fdata-sections',*flags,
             *[a for p in include for a in ('-I',wsl(ROOT/p))],wsl(sources[3])]
        dependencies('stage-filter-'+name,diagnostic_command)
        run([*diagnostic_command,'-Wl,--gc-sections','-o',wsl(diagnostic)])
        checked=run([*(['qemu-riscv32'] if name=='rv32' else []),wsl(diagnostic)])
        assert b'COACH_REAL_PIPE_STAGE_FILTER_ONLY_COUNTERS_NO_LIVE_TEXT_PASS_NOT_BOARD' in checked.stdout
        (out/('stage-filter-'+name+'.log')).write_bytes(checked.stdout+checked.stderr)
        rows.append(dict(name='stage-filter-'+name,pass_=True,executable_sha256=sha(diagnostic)))
    compiled.add(Path(__file__).resolve().relative_to(ROOT).as_posix())
    actual={n:before[n] for n in sorted(compiled)}
    assert actual=={n:sha(ROOT/n) for n in actual},'Compiled input drift'
    drift=[dict(path=n,original_sha256=h,current_sha256=sha(ROOT/n))
           for n,h in before.items() if n not in compiled and sha(ROOT/n)!=h]
    row=dict(ui_feedback=args.ui_feedback,battle_r17=args.battle_r17,status='REAL_MAIN_LOOP_HOST_RV32_PASS_NOT_BOARD',hardware_used=False,
             gui_double_buffer=args.gui_double_buffer,
             actual_inference=False,platform_runtime_renderer='explicit event fixtures',
             display_submit_timing_verified=True,invalid_clock_rejected=True,
             cancel_never_reported_as_capture_completion=True,
             tests=rows,source_sha256=actual,source_inventory_sha256=before,
             uncompiled_inventory_drift=drift)
    (out/'result.json').write_text(json.dumps(row,indent=2)+'\n')
    print(row['status'])

if __name__=='__main__':main()
