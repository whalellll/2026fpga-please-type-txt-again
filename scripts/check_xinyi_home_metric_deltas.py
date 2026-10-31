"""Catch real redundant header stores during a measured home update, offline."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    dirs=['linux/xinyi_board','linux/xinyi','linux/pikafish','linux/pikafish/include','linux/vision','linux/voice',
          'linux/voice_ctc','linux/voice_speech','linux/mac_accel','linux/picture_new','sw/xiangqi','sw/bootloader',
          'artifacts/vision-model-20261020-adapter/runtime']
    sources=['linux/xinyi_board/home_metric_delta_test.c','linux/xinyi/xinyi_product.c',
             'linux/voice/xqvoice_protocol.c','sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_pikafish_link.c']
    result={'status':'FAILED_PRESERVED','hardware_used':False,'runs':[]}
    def run(name,args):
        with (out/(name+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=3 60 '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=75)
        text=(out/(name+'.log')).read_text(errors='replace');assert p.returncode==0,(name,text[-2000:]);return text
    try:
        for target in ['host','rv32']:
            for flag,oom in [(0,0),(1,0),(1,1)]:
                name=f'{target}-flag{flag}-oom{oom}';exe=out/name
                cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
                extra=['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
                flags=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                    '-D_POSIX_C_SOURCE=200809L','-D_DEFAULT_SOURCE',
                    '-DXINYI_CPU_HZ=60000000','-DXINYI_HOME_R13=1','-DXINYI_HOME_R15=1','-DXINYI_BATTLE_R17=1',
                    '-DXINYI_GUI_DOUBLE_BUFFER=1','-DXINYI_UI_FEEDBACK=1','-DXINYI_COACH_MOVE_AUDIO=1',
                    '-DXINYI_GUI_PAGE_DELTAS=1','-DXINYI_GUI_PAIR_DELTAS=1','-DVIDEO_FB_LINUX_MMAP',
                    f'-DXINYI_GUI_METRIC_DELTAS={flag}',*(['-DXINYI_PAIR_CACHE_FORCE_OOM'] if oom else []),
                    '-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h'),*extra,
                    *['-I'+wsl_path(ROOT/d) for d in dirs],*[wsl_path(ROOT/s) for s in sources]]
                deps=run(name+'-deps',[*flags,'-MM']);names={t for t in deps.replace('\\\n',' ').split() if t.startswith(wsl_path(ROOT)+'/')}
                bound={str(n):hashlib.sha256(Path(n[5].upper()+':'+n[6:]).read_bytes()).hexdigest() for n in names}
                run(name+'-build',[*flags,'-lm','-o',wsl_path(exe)])
                text=run(name,[*(['qemu-riscv32'] if target=='rv32' else []),wsl_path(exe)])
                assert f'candidate={flag} unchanged_header_write={1-flag}' in text
                assert bound=={n:hashlib.sha256(Path(n[5].upper()+':'+n[6:]).read_bytes()).hexdigest() for n in bound}
                result['runs'].append({'target':target,'flag':flag,'oom':oom,'source_sha256':bound,'output':text.strip()})
        result['status']='REAL_HEADER_WRITE_BASELINE_RED_CANDIDATE_AND_OOM_GREEN_HOST_RV32'
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
