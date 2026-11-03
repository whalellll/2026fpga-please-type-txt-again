"""Compare all RGB565 pixels with the frozen renderer, including dirty and full paths."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
from workspace_paths import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=workspace_path(a.output);o.mkdir(parents=True,exist_ok=False);(o/'tmp').mkdir()
base=o/'baseline-source.c'
base.write_bytes(subprocess.check_output(['git','-C',str(R),'show','e73cb3b9:linux/pikafish/xiangqi_fb_gui_1080.c']))
inputs=[R/'sim/test_gui1080_host.c',R/'linux/pikafish/xiangqi_fb_gui_1080.c',base]
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
bound={str(f):sha(f) for f in inputs};(o/'inputs.json').write_text(json.dumps(bound,indent=2)+'\n')
for label,f in [('baseline',base),('candidate',inputs[1])]:
 t=f.read_text(encoding='utf-8-sig');t=re.sub(r'words\[([^\]]+)\]\s*=\s*(.*?);',lambda m:'gui_fb_write(words,'+m[1]+','+m[2]+');',t,flags=re.S)
 t=re.sub(r'words\[([^\]]+)\]',lambda m:'gui_fb_read(words,'+m[1]+')',t)
 helpers='''#include <stdint.h>
static uint64_t gui_fb_reads,gui_fb_writes;
static inline uint32_t gui_fb_read(volatile uint32_t *p,unsigned i){gui_fb_reads++;return p[i];}
static inline void gui_fb_write(volatile uint32_t *p,unsigned i,uint32_t v){gui_fb_writes++;p[i]=v;}
'''
 (o/(label+'.c')).write_text(helpers+t,encoding='utf-8',newline='\n')
commands=[]
for label in ['baseline','candidate','candidate-sanitize']:
 source='candidate' if label.startswith('candidate') else 'baseline'
 flags='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' if 'sanitize' in label else '-O2'
 command=f'''set -eu
export TMPDIR='{wsl_path(o/'tmp')}' TMP='{wsl_path(o/'tmp')}' TEMP='{wsl_path(o/'tmp')}'
cd '{wsl_path(R)}'
gcc -std=gnu11 {flags} -Wall -Wextra -Werror -include linux/pikafish/gui1080_config.h -DVIDEO_FB_LINUX_MMAP -DGUI_FB_COUNTED '-DXQ_RENDERER_SOURCE="{wsl_path(o/(source+'.c'))}"' -Ilinux/pikafish/include -Isw/xiangqi -Isw/video -Ilinux/voice -Ilinux/pikafish sim/test_gui1080_host.c linux/voice/xqvoice_protocol.c sw/xiangqi/xiangqi_mouse_input.c sw/xiangqi/xiangqi_search.c -o '{wsl_path(o/label)}'
ASAN_OPTIONS=detect_leaks=1 '{wsl_path(o/label)}'
'''
 (o/(label+'.sh')).write_text(command,newline='\n')
 q=subprocess.run(['wsl.exe','-d','pikafish-verify','--','sh',wsl_path(o/(label+'.sh'))],capture_output=True,timeout=240);(o/(label+'.log')).write_bytes(q.stdout+q.stderr)
 assert q.returncode==0 and b'GUI1080_HOST_PASS' in q.stdout,(label,(q.stdout+q.stderr)[-2000:])
 commands.append(label)
b=(o/'baseline.log').read_bytes();c=(o/'candidate.log').read_bytes()
frames=lambda x:re.findall(rb'^GUI_FRAME.*$',x,re.M)
assert len(frames(b))==96 and frames(b)==frames(c)==frames((o/'candidate-sanitize.log').read_bytes())
counts=lambda x:[tuple(map(int,v)) for v in re.findall(rb'GUI_IO step=\d+ reads=(\d+) writes=(\d+)',x)]
before=tuple(map(sum,zip(*counts(b))));after=tuple(map(sum,zip(*counts(c))))
assert all(sha(Path(f))==h for f,h in bound.items())
d=dict(status='GUI_FINE_96_FULL_FRAME_AND_FROZEN_BASELINE_EXACT_ASAN_UBSAN_PASS_NOT_BOARD',frames=96,baseline_reads=before[0],baseline_writes=before[1],candidate_reads=after[0],candidate_writes=after[1],sources_sha256=bound,fpga_changes=False)
(o/'result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
