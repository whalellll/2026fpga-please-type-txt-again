"""Real native home renderer and immediate-input differential checks, offline."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--targets',default='host,sanitizer,rv32')
    ap.add_argument('--home-r15',action='store_true')
    ap.add_argument('--page-deltas',action='store_true')
    ap.add_argument('--pair-deltas',action='store_true')
    ap.add_argument('--pair-cache-oom',action='store_true')
    ap.add_argument('--ram-render',action='store_true');a=ap.parse_args()
    out=workspace_path(a.output);assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(parents=True,exist_ok=False)
    dirs=['linux/xinyi_board','linux/xinyi','linux/pikafish','linux/pikafish/include','linux/vision','linux/voice',
          'linux/voice_ctc','linux/voice_speech','linux/mac_accel','linux/picture_new','sw/xiangqi','sw/bootloader',
          'artifacts/vision-model-20261020-adapter/runtime']
    sources=['linux/xinyi_board/home_r13_test.c','linux/xinyi/xinyi_product.c','linux/voice/xqvoice_protocol.c',
             'sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_pikafish_link.c','artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c']
    names=set(sources+['linux/xinyi/xinyi_fb.c',str(Path(__file__).relative_to(ROOT))])
    for d in dirs:names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before={n:sha(ROOT/n) for n in names}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,home_r15=a.home_r15,
        ram_render=a.ram_render,page_deltas=a.page_deltas,pair_deltas=a.pair_deltas,pair_cache_oom=a.pair_cache_oom,runs=[],source_sha256=before)
    def run(name,args,limit=120):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=3 '+str(limit)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=limit+15)
        log=(out/(name+'.log')).read_text(errors='replace');assert not p.returncode,(name,p.returncode,log[-2500:]);return log
    try:
        oracle=None
        for target in [*a.targets.split(','),'scalar-oracle']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie']
            if target=='scalar-oracle':extra=['-DXINYI_SCALAR_GLYPH_ORACLE']
            folder=out/target;folder.mkdir();exe=folder/'test'
            run(target+'-build',[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                '-D_POSIX_C_SOURCE=200809L','-DXINYI_HOME_R13=1','-DXINYI_CPU_HZ=60000000','-DXINYI_GUI_DOUBLE_BUFFER=1',
                '-DXINYI_UI_FEEDBACK=1','-DVIDEO_FB_LINUX_MMAP','-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h'),
                '-DXINYI_HOME_R15='+str(int(a.home_r15)),
                '-DXINYI_GUI_RAM_RENDER='+str(int(a.ram_render)),
                '-DXINYI_GUI_PAGE_DELTAS='+str(int(a.page_deltas)),
                '-DXINYI_GUI_PAIR_DELTAS='+str(int(a.pair_deltas)),
                *(['-DXINYI_PAIR_CACHE_TEST_STATS'] if a.pair_deltas else []),
                *(['-DXINYI_PAIR_CACHE_FORCE_OOM'] if a.pair_cache_oom else []),
                *extra,*['-I'+wsl_path(ROOT/d) for d in dirs],*[wsl_path(ROOT/n) for n in sources],'-lm','-o',wsl_path(exe)])
            log=run(target,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe),wsl_path(folder)],180)
            assert 'R13_RENDER_FULL_PIXELS_TWO_BANKS_LOCAL_FEEDBACK_GUARDS_PASS' in log
            hashes=[line for line in log.splitlines() if line.startswith(('R13_FRAME','R13_GLYPH'))]
            if oracle is None:oracle=hashes
            assert hashes==oracle,(target,'pixel mismatch')
            result['runs'].append(dict(target=target,full_pixel_hash_records=len(hashes),exact=True,executable_sha256=sha(exe)))
        assert before=={n:sha(ROOT/n) for n in names};result['status']='R13_HOME_SELECTED_TARGETS_SCALAR_PIXELS_AND_IMMEDIATE_INPUT_PASS_NOT_BOARD'
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
