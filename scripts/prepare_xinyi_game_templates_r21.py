"""Generate static game pixels from the real scalar renderer; no device access."""
from pathlib import Path
import argparse,hashlib,json,re,shlex,struct,subprocess
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    names=['linux/xinyi/game_template_export_r21.c','linux/xinyi/xinyi_product.c',
           'linux/voice/xqvoice_protocol.c','sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_pikafish_link.c']
    dirs=['linux/xinyi_board','linux/xinyi','linux/pikafish','linux/pikafish/include','linux/vision',
          'linux/voice','linux/voice_ctc','linux/voice_speech','linux/mac_accel','linux/picture_new','sw/xiangqi','sw/bootloader',
          'artifacts/vision-model-20261020-adapter/runtime']
    flags=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
           '-D_POSIX_C_SOURCE=200809L','-DXINYI_CPU_HZ=60000000','-DXINYI_HOME_R13=1','-DXINYI_HOME_R15=1',
           '-DXINYI_BATTLE_R17=1','-DXINYI_GUI_DOUBLE_BUFFER=1','-DXINYI_UI_FEEDBACK=1','-DXINYI_COACH_MOVE_AUDIO=1',
           '-DXINYI_SCALAR_GLYPH_ORACLE','-DXINYI_GUI_FAST_NAV_R21=0','-DVIDEO_FB_LINUX_MMAP',
           '-include',wsl_path(ROOT/'linux/pikafish/gui1080_config.h'),
           *['-I'+wsl_path(ROOT/d) for d in dirs],*[wsl_path(ROOT/n) for n in names]]
    def run(label,args):
        p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
            'ulimit -c 0\nexec timeout 120 '+shlex.join(args)],capture_output=True,timeout=135)
        (out/(label+'.log')).write_bytes(p.stdout+p.stderr);assert not p.returncode,(label,p.stderr[-2000:]);return p.stdout
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    deps=run('dependencies',[*flags,'-MM']).decode();prefix=wsl_path(ROOT)+'/'
    sources={t[len(prefix):] for t in deps.replace('\\\n',' ').split() if t.startswith(prefix)}
    sources.add('scripts/prepare_xinyi_game_templates_r21.py');before={n:sha(ROOT/n) for n in sorted(sources)}
    run('build',[*flags,'-lm','-o',wsl_path(out/'export')]);run('export',[wsl_path(out/'export'),wsl_path(out)])
    lines=['/* Generated from the independent scalar game renderer. */','#ifndef XINYI_GAME_TEMPLATES_R21_H',
           '#define XINYI_GAME_TEMPLATES_R21_H','#include "xinyi_ui_copy_r20.h"','#include "xinyi_battle_speedups_r17.h"']
    for header in ['xinyi_ui_copy_r20.h','xinyi_battle_speedups_r17.h']:
        values=re.findall(r'^#define (XY(?:20|17)_\w+) ("[^"\n]*"|[0-9.eE+-]+)$',
                          (ROOT/'linux/xinyi'/header).read_text(encoding='utf8'),re.M)
        for key,value in values:
            expression=f'__builtin_strcmp({key},{value})==0' if value.startswith('"') else f'{key}=={value}'
            lines.append(f'_Static_assert({expression},"Regenerate R21 game cache");')
    rows=[];left_words=None
    for mode in range(3):
        path=out/f'game-{mode}.rgb565';words=struct.unpack('<1036800I',path.read_bytes())
        left=tuple(v for row in range(1080) for v in words[row*960:row*960+479])
        right=tuple(v for row in range(1080) for v in words[row*960+479:(row+1)*960])
        if left_words is None:left_words=left
        else:assert left==left_words,'The three empty board backgrounds must match'
        parts=[('xy21_game_right_'+str(mode),right)]
        if mode==0:parts.insert(0,('xy21_game_left',left))
        for name,part in parts:
            runs=[];i=0
            while i<len(part):
                end=i+1
                while end<len(part) and part[end]==part[i]:end+=1
                runs.append((end-i,part[i]));i=end
            lines.append(f'static const xy15_run {name}[]={{')
            lines.extend(','.join('{%du,0x%08xu}'%v for v in runs[i:i+4])+',' for i in range(0,len(runs),4));lines.append('};')
            rows.append(dict(name=name,mode=mode,source_frame_sha256=sha(path),runs=len(runs),rom_bytes=len(runs)*8))
    lines+=['static const xy15_run *const xy21_game_right[3]={xy21_game_right_0,xy21_game_right_1,xy21_game_right_2};','#endif','']
    assert before=={n:sha(ROOT/n) for n in before}
    header=ROOT/'linux/xinyi/xinyi_game_templates_r21.h';header.write_bytes('\n'.join(lines).encode())
    (out/'result.json').write_text(json.dumps(dict(status='R21_GAME_SCALAR_CACHE_SOURCE_BOUND_NOT_BOARD',
        hardware_used=False,source_sha256=before,pages=rows,header_sha256=sha(header)),indent=2)+'\n')
    print('R21_GAME_SCALAR_CACHE_SOURCE_BOUND_NOT_BOARD',sum(r['rom_bytes'] for r in rows))

if __name__=='__main__':main()
