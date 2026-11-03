"""Reusable GUI/display preflight. This does not program hardware or prove routed STA."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import time


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--tools', type=Path, default=Path('G:/fpga/workspace/tools/msys64/ucrt64/bin'))
    ap.add_argument('--pds', type=Path, default=Path('G:/fpga/PDS_2022.2-SP6.4'))
    ap.add_argument('--distro', default='pikafish-verify')
    ap.add_argument('--theme', choices=['dark','light'], default='light')
    ap.add_argument('--checks', nargs='+', choices=['font','host','preview','controls','pointer','legacy','clock','pll','cpu-reset','rv32','scanout'],
                    default=['font','host','preview','controls','pointer','legacy','clock','pll','cpu-reset','rv32','scanout'])
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env['PATH'] = str(args.tools) + os.pathsep + str(args.tools.parent.parent/'mingw64/bin') + os.pathsep + env['PATH']
    gcc = str(args.tools/'gcc.exe')
    iv = str(args.tools/'iverilog.exe')
    vvp = str(args.tools/'vvp.exe')
    flags = ['-std=gnu11','-O2','-Wall','-Wextra','-Werror',
             '-Ilinux/pikafish/include','-Isw/xiangqi','-Ilinux/voice','-Ilinux/pikafish']
    if args.theme == 'dark':
        flags.append('-DXQ_GUI_DARK_THEME')
    records = []
    inventory = sorted(set(root.glob('rtl/video/*')) | set(root.glob('rtl/soc/*.v')) |
                       set(root.glob('rtl/camera/*.v')) | set(root.glob('linux/pikafish/*.c')) |
                       set(root.glob('linux/pikafish/*.h')) | set(root.glob('linux/pikafish/include/*.h')) |
                       set(root.glob('sw/xiangqi/*.[ch]')) | set(root.glob('sw/video/*.h')) |
                       set(root.glob('config/*.json')) | {root/'pds/soc.fdc', root/'linux/soc.dts',
                       root/'linux/pikafish/build_voice_display_gui.sh'} |
                       {root/'linux/pikafish/relink_gui_display.sh'} |
                       set(root.glob('linux/voice/*.[ch]')) |
                       set(root.glob('linux/pikafish/fonts/*')) |
                       set(root.glob('sim/*gui1080*')) | {Path(__file__),root/'scripts/preview_xiangqi_gui.c',
                       root/'scripts/clock_policy.ps1',root/'scripts/check_clock_config.ps1',
                       root/'scripts/compile_gui1080_rv32.sh',root/'scripts/test_cpu_clock_domains.py',
                       root/'scripts/gen_xiangqi_piece_font.py',
                       root/'scripts/gen_xiangqi_ui_font.py',
                       root/'sim/tb_video_fb_dma.sv'})
    hashes = {str(p.relative_to(root)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in inventory if p.is_file()}
    (out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')

    def run(label, cmd, marker=None, timeout=300, working_dir=None):
        start = time.monotonic()
        result = subprocess.run(cmd,cwd=working_dir or root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        log = result.stdout.decode('utf-8',errors='replace')
        (out/(label+'.log')).write_bytes(result.stdout)
        ok = result.returncode==0 and (marker is None or marker in log) and not re.search(r'(?m)^(ERROR:|FATAL:)',log)
        records.append({'check':label,'command':cmd,'exit_code':result.returncode,'pass':ok,
                        'seconds':round(time.monotonic()-start,3),
                        'log_sha256':hashlib.sha256(result.stdout).hexdigest()})
        print(label+': '+('PASS' if ok else 'FAIL'),flush=True)
        if not ok:
            raise RuntimeError(log[-6000:])

    def rtl(label, top, sources, marker):
        product = str(out/(label+'.vvp'))
        run(label+'-compile',[iv,'-g2012','-s',top,'-o',product,*sources])
        (out/'font8x16.hex').write_bytes((root/'rtl/video/font8x16.hex').read_bytes())
        run(label,[vvp,product],marker,timeout=600,working_dir=out)

    status='GUI1080_OFFLINE_CHECK_INTERRUPTED_NOT_PROGRAMMABLE'
    try:
        if 'font' in args.checks:
            import sys
            run('font',[sys.executable,'-X','utf8','scripts/gen_xiangqi_piece_font.py','--check'],
                'PIECE_FONT_REGENERATION_PASS')
            run('ui-font',[sys.executable,'-X','utf8','scripts/gen_xiangqi_ui_font.py','--check'],
                'UI_FONT_REGENERATION_PASS')
        if 'host' in args.checks:
            binary = str(out/'host.exe')
            run('host-compile',[gcc,*flags,'-DVIDEO_FB_LINUX_MMAP','-include','linux/pikafish/gui1080_config.h',
                'sim/test_gui1080_host.c','linux/voice/xqvoice_protocol.c',
                'sw/xiangqi/xiangqi_mouse_input.c','sw/xiangqi/xiangqi_search.c','-o',binary])
            run('host',[binary],'GUI1080_HOST_PASS')
        if 'preview' in args.checks:
            from PIL import Image
            for label, extra in [('before',[]),('after',['-DXQ_GUI_1080'])]:
                binary = str(out/(label+'.exe'))
                run(label+'-compile',[gcc,*flags,*extra,'scripts/preview_xiangqi_gui.c',
                    'linux/voice/xqvoice_protocol.c','-o',binary])
                run(label,[binary,str(out/(label+'.ppm'))])
                Image.open(out/(label+'.ppm')).save(out/(label+'.png'))
            word_binary = str(out/'after-word.exe')
            run('after-word-compile',[gcc,*flags,'-DXQ_GUI_1080','-DVIDEO_FB_LINUX_MMAP',
                'scripts/preview_xiangqi_gui.c','linux/voice/xqvoice_protocol.c','-o',word_binary])
            run('after-word',[word_binary,str(out/'after-word.ppm')])
            if (out/'after.ppm').read_bytes() != (out/'after-word.ppm').read_bytes():
                raise RuntimeError('Full-word uncached raster differs from the reference raster')
            (out/'word-raster-match.txt').write_text('GUI1080_WORD_STORE_RASTER_MATCH_PASS\n',encoding='utf-8')
            run('voice-preview',[word_binary,str(out/'voice.ppm'),'voice'])
            Image.open(out/'voice.ppm').save(out/'voice.png')
        if 'controls' in args.checks:
            rtl('controls','tb_gui1080_controls',['sim/tb_gui1080_controls.sv',
                'rtl/soc/ch9350_hid_core.v','rtl/video/video_fb_mmio.v'],'GUI1080_CONTROLS_PASS')
        if 'pointer' in args.checks:
            rtl('pointer','tb_gui1080_pointer',['sim/tb_gui1080_pointer.sv',
                'rtl/video/hid_gui_overlay.v','rtl/video/font_rom.v'],'GUI1080_POINTER_PASS')
        if 'legacy' in args.checks:
            rtl('legacy','tb_video_fb_dma',['sim/tb_video_fb_dma.sv','rtl/video/video_fb_dma.v'],'VIDEO_FB_DMA_PASS')
        if 'clock' in args.checks:
            run('clock',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',
                'scripts/check_clock_config.ps1'],'SOC_CLOCK_CONFIG_PASS')
        if 'pll' in args.checks:
            model = args.pds/'arch/vendor/pango/verilog/simulation/GTP_GPLL.v'
            (out/'vendor-model.json').write_text(json.dumps({'path':str(model),
                'sha256':hashlib.sha256(model.read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')
            rtl('pll','tb_gui1080_pll',['sim/tb_gui1080_pll.sv','rtl/video/pll_video.v',str(model)],'GUI1080_VENDOR_PLL_PASS')
        if 'cpu-reset' in args.checks:
            import sys
            run('cpu-reset',[sys.executable,'-X','utf8','scripts/test_cpu_clock_domains.py',
                '--output',str(out/'cpu-reset')],'SOC_ACTUAL_CLOCK_RESET_BLOCK_PASS')
        if 'rv32' in args.checks:
            def wsl_path(p):
                return '/mnt/'+p.drive[0].lower()+'/'+str(p)[3:].replace('\\','/')
            run('rv32',['wsl','-d',args.distro,'--','sh',
                wsl_path(root/'scripts/compile_gui1080_rv32.sh'),wsl_path(root),wsl_path(out/'rv32'),args.theme],
                'GUI1080_RV32_OBJECTS_AND_DTB_PASS_NOT_LINKED_OR_BOARD',timeout=600)
        if 'scanout' in args.checks:
            rtl('scanout','tb_gui1080_scanout',['sim/tb_gui1080_scanout.sv','rtl/video/video_fb_dma.v',
                'rtl/soc/ddr_native_read_arbiter.v'],'GUI1080_SCANOUT_PASS')
        for name, digest in hashes.items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Input changed while checks ran: '+name)
        status='SELECTED_GUI1080_OFFLINE_CHECKS_PASS_NOT_PNR_OR_BOARD'
    except Exception:
        status='GUI1080_OFFLINE_CHECK_FAILED_NOT_PROGRAMMABLE'
        raise
    finally:
        receipt={'schema':1,'status':status,'theme':args.theme,'checks':args.checks,'results':records,
                 'completed_utc':datetime.now(timezone.utc).isoformat(),
                 'inputs_sha256':hashlib.sha256((out/'inputs.json').read_bytes()).hexdigest(),
                 'final_native_sta':'NOT_RUN','board':'NOT_RUN','accelerator_board_performance':'NOT_MEASURED'}
        (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
