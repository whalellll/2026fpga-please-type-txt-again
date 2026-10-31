"""Verify independent short PCM assets and the actual player preparation path."""
import argparse,hashlib,json,shlex,shutil,subprocess,wave
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['pcm','output']:ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args();pcm=workspace_path(a.pcm);out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    sha=lambda b:hashlib.sha256(b).hexdigest();m=json.loads((pcm/'move/manifest.json').read_text(encoding='utf-8'))
    assert m['sample_rate']==16000 and m['token_max_samples']==3840 and len(m['files'])==24 and not m['over_budget']
    assets={}
    for n,r in m['files'].items():
        b=(pcm/'move'/n).read_bytes();assert len(b)==r['bytes']==r['samples']*2 and sha(b)==r['sha256']
        assert 0<len(b)<=7680;assets[n]=sha(b)
    bad=out/'bad/move';bad.mkdir(parents=True)
    for p in (pcm/'move').glob('*.pcm'):shutil.copyfile(p,bad/p.name)
    (bad/'cannon.pcm').write_bytes(b'\x01\x00'*3841)
    names=['linux/voice_speech/tests/test_move_pcm.c','linux/voice_speech/xq_speech_linux.c','linux/voice_speech/xq_speech.c',
        'linux/voice_speech/xq_speech.h','linux/voice_speech/xq_move_speech.h','linux/xinyi_board/gui_options.h',
        'sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_pikafish_link.c','scripts/check_xinyi_move_pcm.py','scripts/generate_xinyi_move_speech.ps1']
    sources={n:sha((ROOT/n).read_bytes()) for n in names};result=dict(status='FAILED_PRESERVED',hardware_used=False,hearing_verified=False,
        source_sha256=sources,assets_sha256=assets,manifest_sha256=sha((pcm/'move/manifest.json').read_bytes()),runs=[])
    try:
        for target in ['host','sanitizer','rv32']:
            cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'gcc';exe=out/target
            extra=['-march=rv32ima','-mabi=ilp32','-mstrict-align','-static'] if target=='rv32' else []
            if target=='sanitizer':extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie']
            cmd=[cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-DXINYI_COACH_MOVE_AUDIO=1',*extra,
                '-I'+wsl_path(ROOT/'linux/voice_speech'),'-I'+wsl_path(ROOT/'sw/xiangqi'),
                *[wsl_path(ROOT/n) for n in [names[0],names[2],names[6],names[7]]],'-o',wsl_path(exe)]
            for label,args in [('build',cmd),('run',(['qemu-riscv32'] if target=='rv32' else [])+[wsl_path(exe),wsl_path(pcm),wsl_path(out/'bad')])]:
                p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout 90 '+shlex.join(args)],capture_output=True,timeout=105)
                (out/(target+'-'+label+'.log')).write_bytes(p.stdout+p.stderr)
                assert p.returncode==0,(target,label,p.stdout[-1000:],p.stderr[-1600:])
                if label=='run':assert b'MOVE_PCM_PASS' in p.stdout
            result['runs'].append(dict(target=target,pass_=True))
        examples=[('cannon-two-horizontal-five',['cannon','two','horizontal','five']),
                  ('knight-eight-forward-seven',['knight','eight','forward','seven']),
                  ('front-rook-backward-one',['front','rook','backward','one'])]
        result['examples']={}
        for n,tokens in examples:
            b=bytes(128)+b''.join((pcm/'move'/(t+'.pcm')).read_bytes() for t in tokens)
            with wave.open(str(out/(n+'.wav')),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b)
            result['examples'][n]=dict(samples=len(b)//2,duration_ms=len(b)/32,sha256=sha(b))
        assert sources=={n:sha((ROOT/n).read_bytes()) for n in names}
        result['status']='MOVE_PCM_BUDGET_PLAYER_REJECTION_AND_RECOVERY_HOST_RV32_SANITIZERS_PASS_NOT_BOARD'
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
