"""Build/seal offline UI feedback + compact coach speech, never install."""
import argparse,gzip,hashlib,json,shlex,subprocess,zipfile
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['output','pcm']:ap.add_argument('--'+n,required=True,type=Path)
    ap.add_argument('--proof',required=True,type=Path,action='append');a=ap.parse_args()
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False);pcm=workspace_path(a.pcm)
    sha=lambda b:hashlib.sha256(b).hexdigest();sources={};payload={};proofs=[]
    def bind(n,h):
        assert sha((ROOT/n).read_bytes())==h,n
        assert n not in sources or sources[n]==h,n;sources[n]=h
    for path in a.proof:
        b=workspace_path(path).read_bytes();p=json.loads(b)
        assert 'PASS_NOT_BOARD' in p['status'],p['status']
        for n,h in p['source_sha256'].items():bind(n,h)
        payload['evidence/'+path.parent.name+'.json']=b;proofs.append(p)
    assert any(p.get('ui_feedback') for p in proofs)
    assert any(p.get('status','').startswith('UI_FEEDBACK_REAL_RENDERER') for p in proofs)
    assert any(p.get('status','').startswith('MOVE_PCM_BUDGET') for p in proofs)
    assert any(p.get('status','').startswith('HOST_RV32_RUNTIME') and p.get('move_only') for p in proofs)
    assert {p.get('rv32') for p in proofs if p.get('move_only') and 'SPEECH_TASK_' in p['status']}=={False,True}
    for n in ['scripts/prepare_xinyi_ui_audio_r11.py','scripts/check_xinyi_ui_audio_r11_package.py',
        'scripts/picture_workspace.py','scripts/verify_xinyi_elf.py','config/clocks.json']:
        bind(n,sha((ROOT/n).read_bytes()))
    for p in (ROOT/'artifacts/vision-model-20261020-adapter/runtime').glob('*.h'):
        bind(p.relative_to(ROOT).as_posix(),sha(p.read_bytes()))
    def lexical(p):
        p=p.absolute();assert p.is_relative_to(ROOT/'build');s=p.as_posix();return '/mnt/'+s[0].lower()+s[2:]
    def run(name,argv,seconds=180):
        with (out/(name+'.log')).open('xb') as log:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],
                stdout=log,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert r.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
    binaries={}
    for name,hz,candidate in [('cpu75-reference',75000000,0),('cpu75-feedback',75000000,1),('cpu60-feedback',60000000,1),('speech-move',0,1)]:
        speech=hz==0;script='build_speech.sh' if speech else 'build.sh'
        env=['XINYI_COACH_MOVE_AUDIO='+str(candidate)]
        if not speech:env+=['XINYI_CPU_HZ='+str(hz),'XINYI_GUI_DOUBLE_BUFFER='+str(candidate),'XINYI_UI_FEEDBACK='+str(candidate)]
        run(name+'-build',['env',*env,'sh',wsl_path(ROOT/'linux/xinyi_board'/script),lexical(a.output/name)])
        folder=out/name;assert (folder/'source-before.sha256').read_bytes()==(folder/'source-after.sha256').read_bytes()
        prefix=wsl_path(ROOT)+'/'
        for line in (folder/'source-before.sha256').read_text().splitlines():
            h,n=line.split(None,1);assert n.startswith(prefix);bind(n[len(prefix):],h)
        elf=out/(name+'.elf');original=folder/('xinyi-speech-worker' if speech else 'xinyi-one')
        run(name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),wsl_path(original)],30)
        old,new=inspect(original),inspect(elf);assert old['allocated']==new['allocated'] and old['entry']==new['entry'] and old['flags']==new['flags']
        b=elf.read_bytes();payload['software/'+name+'/program.rv32.elf']=b
        payload['software/'+name+'/program.rv32.elf.gz']=gzip.compress(b,mtime=0)
        binaries[name]=dict(cpu_hz=hz,candidate=bool(candidate),speech=speech,bytes=len(b),sha256=sha(b),allocated_sections_preserved=True)
    prior=ROOT/'build/picture-e42-20261025/gui-offline-delivery-r10-r01/cpu75-reference.elf'
    assert (out/'cpu75-reference.elf').read_bytes()==prior.read_bytes(),'default0 GUI differs from r10 baseline'
    m=json.loads((pcm/'move/manifest.json').read_text(encoding='utf-8'));assert not m['over_budget'] and len(m['files'])==24
    for n,r in m['files'].items():
        b=(pcm/'move'/n).read_bytes();assert sha(b)==r['sha256'] and 0<len(b)<=7680
        payload['pcm/move/'+n]=b
    payload['pcm/move/manifest.json']=(pcm/'move/manifest.json').read_bytes()
    for path in a.proof:
        if 'move-pcm' in path.parent.name:
            for f in workspace_path(path).parent.glob('*.wav'):payload['preview/'+f.name]=f.read_bytes()
    payload['README.md']=b'''# Offline UI/audio r11

Candidate GUI + matching speech helper + pcm/move assets, source and evidence.
No installer, boot payload, kernel, recognition worker, model or private image.
Not installed or board-tested. Preserve the existing PCM root and old helper.
The 24 new files belong under the existing PCM root's move/ subdirectory.
Use a matching CPU60/CPU75 GUI and the new speech helper together.

XINYI_UI_FEEDBACK=1: enabled buttons highlight on hover, depress while held,
flash on release, then activate once. Dragging out cancels. Quick clicks receive
80 ms down + 100 ms release feedback. These use local button redraws and the
existing inactive-page renderer, not a continuous full-frame animation loop.
The new raw HID state comes from the existing coherent status/sequence ABI.

XINYI_COACH_MOVE_AUDIO=1: only image-coach requests omit red/black prefixes.
Voice-battle speech keeps its original request. New wire kind8 is explicit;
an old helper rejects it. Four complete native-rate6 synthesized syllables,
with quiet boundaries removed and 15 ms original context retained, replace
the previous long individual clips. No runtime truncation/resampling. Tokens
over240 ms fail before acquiring audio ownership. Four tokens plus the
unchanged 4 ms FIFO prime are <=964 ms of PCM. No audible/device/startup
latency guarantee follows from that bound. WAV examples are in preview/.
Normal PCM, move legality/disambiguation, underflow reporting, RT-budget
restoration, cancellation and estimated-board recommendations remain.

Flags default0. CPU75 default0 exactly reproduces the old reference GUI.
Build using linux/xinyi_board/build.sh and build_speech.sh with the manifest
variant flags. Existing vision r09 worker/package remains a separate input;
this package does not bind changed headers back to its historical ELF.
'''
    for n,h in sorted(sources.items()):bind(n,h);payload['source/'+n]=(ROOT/n).read_bytes()
    manifest=dict(schema='xinyi-ui-audio-r11-v1',status='OFFLINE_NOT_INSTALLED_NOT_BOARD',hardware_used=False,
        hearing_verified=False,default0_gui_equals_r10=True,binaries=binaries,sources_sha256=sources,
        payloads={n:dict(bytes=len(b),sha256=sha(b)) for n,b in sorted(payload.items())})
    payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=out/'xinyi-ui-audio-offline-r11-r01-20261028.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(payload.items()):
            i=zipfile.ZipInfo(n,(2026,10,28,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,b)
    result=dict(status='UI_AUDIO_R11_SEALED_NOT_INSTALLED_NOT_BOARD',archive_bytes=archive.stat().st_size,
        archive_sha256=sha(archive.read_bytes()),members=len(payload),source_entries=len(sources),binaries=binaries)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
