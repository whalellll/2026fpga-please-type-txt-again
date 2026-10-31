"""Bounded real-renderer/button state checks, no hardware access."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--targets',default='host,sanitizer,rv32');a=ap.parse_args()
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    include=['linux/xinyi_board','linux/xinyi','linux/pikafish','linux/pikafish/include','linux/vision',
        'linux/voice','linux/voice_ctc','linux/voice_speech','linux/mac_accel','linux/picture_new','sw/xiangqi','sw/bootloader']
    sources=['linux/xinyi_board/ui_feedback_test.c','linux/xinyi/xinyi_product.c','linux/voice/xqvoice_protocol.c',
        'sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_pikafish_link.c']
    hid_sources=['linux/xinyi_board/ui_hid_test.c','linux/vision/xq_picture.c']
    names=set(sources+hid_sources+['linux/xinyi_board/platform.c','linux/xinyi/xinyi_fb.c','linux/pikafish/xiangqi_fb_gui_1080.c','scripts/check_xinyi_ui_feedback.py'])
    for d in include:names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={n:sha(ROOT/n) for n in sorted(names)}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,source_sha256=before,runs=[])
    try:
        for target in a.targets.split(','):
            assert target in ['host','sanitizer','rv32'];exe=out/target
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc'
            extra=['-march=rv32ima','-mabi=ilp32','-mstrict-align','-static'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
            args=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D_POSIX_C_SOURCE=200809L',
                '-DXINYI_GUI_DOUBLE_BUFFER=1','-DXINYI_UI_FEEDBACK=1','-DVIDEO_FB_LINUX_MMAP',
                '-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h'),*extra,
                *['-I'+wsl_path(ROOT/n) for n in include],*[wsl_path(ROOT/n) for n in sources],'-lm','-o',wsl_path(exe)]
            for label,cmd,limit in [('build',args,90),('run',(['qemu-riscv32'] if target=='rv32' else [])+[wsl_path(exe)],240)]:
                p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                    'ulimit -c 0\nexec timeout --kill-after=5 '+str(limit)+' '+shlex.join(cmd)],capture_output=True,timeout=limit+15)
                (out/(target+'-'+label+'.log')).write_bytes(p.stdout+p.stderr)
                assert p.returncode==0,(target,label,p.stdout[-1000:],p.stderr[-2000:])
                if label=='run':assert b'UI_FEEDBACK_PASS' in p.stdout
            result['runs'].append(dict(target=target,pass_=True,executable_sha256=sha(exe)))
            hid=out/(target+'-hid')
            args=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',
                '-DXINYI_UI_FEEDBACK=1',*extra,*['-I'+wsl_path(ROOT/n) for n in include],
                *[wsl_path(ROOT/n) for n in hid_sources],'-Wl,--gc-sections','-pthread','-lm','-o',wsl_path(hid)]
            for label,cmd in [('hid-build',args),('hid-run',(['qemu-riscv32'] if target=='rv32' else [])+[wsl_path(hid)])]:
                p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout 90 '+shlex.join(cmd)],capture_output=True,timeout=105)
                (out/(target+'-'+label+'.log')).write_bytes(p.stdout+p.stderr)
                assert p.returncode==0,(target,label,p.stdout[-1000:],p.stderr[-2000:])
            result['runs'].append(dict(target=target+'-actual-hid',pass_=True,executable_sha256=sha(hid)))
        assert before=={n:sha(ROOT/n) for n in before}
        result['status']='UI_FEEDBACK_REAL_RENDERER_FULL_PIXELS_AND_STATE_PASS_NOT_BOARD'
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
