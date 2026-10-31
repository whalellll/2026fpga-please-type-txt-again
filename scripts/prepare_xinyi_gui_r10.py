"""Build/seal software-only GUI double-buffer candidates, never install."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import zipfile
from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['loop-proof','render-proof','output']:ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    loop=json.loads(workspace_path(a.loop_proof).read_text());render=json.loads(workspace_path(a.render_proof).read_text())
    assert loop['status']=='REAL_MAIN_LOOP_HOST_RV32_PASS_NOT_BOARD' and loop['gui_double_buffer']
    assert render['status']=='GUI_TWO_BANK_FULL_PIXELS_FONT_WORD_COUNTS_AND_PLATFORM_ACK_PASS_NOT_BOARD'
    sources={}
    for proof in [loop,render]:
        for n,h in proof['source_sha256' if 'source_sha256' in proof else 'sources_sha256'].items():
            assert sha((ROOT/n).read_bytes())==h,n
            assert n not in sources or sources[n]==h;sources[n]=h
    for name in ['scripts/prepare_xinyi_gui_r10.py','scripts/check_xinyi_gui_r10_package.py',
                 'scripts/picture_workspace.py','scripts/verify_xinyi_elf.py','config/clocks.json']:
        sources[name]=sha((ROOT/name).read_bytes())
    for p in (ROOT/'artifacts/vision-model-20261020-adapter/runtime').glob('*.h'):
        sources[p.relative_to(ROOT).as_posix()]=sha(p.read_bytes())
    def lexical(path):
        p=path.absolute();assert p.is_relative_to(ROOT/'build');s=p.as_posix();return '/mnt/'+s[0].lower()+s[2:]
    def run(name,argv,seconds=180):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert r.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2500:])
    binaries={};payload={};variants=[('cpu75-reference',75000000,0),('cpu75-double',75000000,1),('cpu60-double',60000000,1)]
    for name,hz,double in variants:
        logical=a.output.absolute()/name;folder=out/name
        run(name+'-build',['env','XINYI_CPU_HZ='+str(hz),'XINYI_GUI_DOUBLE_BUFFER='+str(double),
            'sh',wsl_path(ROOT/'linux/xinyi_board/build.sh'),lexical(logical)])
        assert (folder/'source-before.sha256').read_bytes()==(folder/'source-after.sha256').read_bytes()
        prefix=wsl_path(ROOT)+'/'
        for line in (folder/'source-before.sha256').read_text().splitlines():
            h,n=line.split(None,1);assert n.startswith(prefix),n;relative=n[len(prefix):]
            assert sha((ROOT/relative).read_bytes())==h;assert relative not in sources or sources[relative]==h;sources[relative]=h
        elf=out/(name+'.elf')
        run(name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),wsl_path(folder/'xinyi-one')],30)
        before,after=inspect(folder/'xinyi-one'),inspect(elf)
        assert before['allocated']==after['allocated'] and before['entry']==after['entry'] and before['flags']==after['flags']
        b=elf.read_bytes();payload['software/'+name+'/gui.rv32.elf']=b
        payload['software/'+name+'/gui.rv32.elf.gz']=gzip.compress(b,mtime=0)
        binaries[name]=dict(cpu_hz=hz,double_buffer=bool(double),bytes=len(b),sha256=sha(b),allocated_sections_preserved=True)
    old=ROOT/'build/picture-e42-20261025/main-integration-20261028-r01/product-cpu75/product/xinyi-one-stripped'
    assert sha(old.read_bytes())=='f50801c5636560a159a91b87b4664f1d9cc5b45bb42e32a71c071bfddd77d23d'
    reference_equal=(out/'cpu75-reference.elf').read_bytes()==old.read_bytes()
    for n,h in sorted(sources.items()):
        b=(ROOT/n).read_bytes();assert sha(b)==h;payload['source/'+n]=b
    payload['evidence/checks.json']=(json.dumps(dict(loop=loop,render=render,hardware_used=False),indent=2)+'\n').encode()
    payload['README.md']=b'''# Offline GUI r10: draw behind the visible page

GUI binaries/source/evidence only. No model, photo, position, worker, kernel,
rootfs, boot selector or installer. Uninstalled and not board-tested.
Use matching CPU60/CPU75 identity; existing strict MMIO guards remain.

XINYI_GUI_DOUBLE_BUFFER defaults0. Candidate1 renders the inactive GUI bank,
submits only complete frames, waits for active-bank/frame acknowledgement
before reuse, and keeps dirty state while submission is deferred. Camera
preview remains exclusive; cancellation and undrained protection remain.
Each of the two GUI banks owns its dirty-render history. Font pixels and
recognition/recommendation policy are unchanged. No new RTL is required.

The original real main loop fails the visible-bank-write observer. New
host/RV32 loop, 253 host/sanitizer pixel states, reduced RV32 pixel matrix,
and host/RV32/sanitizer platform flip/error/camera tests pass offline.
Word-access counts do not measure physical DDR bandwidth or button latency.
Physical visibility and whole-board correctness/latency still need testing.

From source/ with the pinned RV32IMA musl toolchain, build each variant:
env XINYI_CPU_HZ=75000000 XINYI_GUI_DOUBLE_BUFFER=0 sh linux/xinyi_board/build.sh "$PWD/build/gui75-reference"
env XINYI_CPU_HZ=75000000 XINYI_GUI_DOUBLE_BUFFER=1 sh linux/xinyi_board/build.sh "$PWD/build/gui75-double"
env XINYI_CPU_HZ=60000000 XINYI_GUI_DOUBLE_BUFFER=1 sh linux/xinyi_board/build.sh "$PWD/build/gui60-double"
'''
    manifest=dict(schema='xinyi-gui-offline-r10-v1',status='OFFLINE_GUI_NOT_INSTALLED_NOT_BOARD',
        hardware_used=False,model_or_private_payloads=False,fonts_changed=False,
        cpu75_default0_equals_prior_gui=reference_equal,prior_cpu75_gui_sha256=sha(old.read_bytes()),
        binaries=binaries,sources_sha256=sources,
        payloads={n:dict(bytes=len(b),sha256=sha(b)) for n,b in sorted(payload.items())})
    assert all(Path(n).suffix.lower() not in {'.png','.jpg','.rgb565','.f32','.xqm','.xqi','.bin'} for n in payload)
    payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=out/'xinyi-gui-offline-r10-r01-20261028.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(payload.items()):
            info=zipfile.ZipInfo(n,(2026,10,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
    result=dict(status='GUI_R10_SEALED_NOT_INSTALLED_NOT_BOARD',archive_bytes=archive.stat().st_size,
        archive_sha256=sha(archive.read_bytes()),members=len(payload),source_entries=len(sources),
        cpu75_default0_equals_prior_gui=reference_equal,binaries=binaries)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
