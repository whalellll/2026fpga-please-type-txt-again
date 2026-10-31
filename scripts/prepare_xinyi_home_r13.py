"""Build and source-reproduce two offline home GUIs; no installer or hardware."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess,zipfile,shutil
from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--reuse-build',type=Path,help='Reuse unchanged source-bound GUI builds after a packaging-only repair')
    ap.add_argument('--proof',type=Path,action='append',required=True);a=ap.parse_args()
    out=workspace_path(a.output);assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(parents=True,exist_ok=False)
    sha=lambda b:hashlib.sha256(b).hexdigest();sources={};payload={};proofs=[];unused_header_drift=[]
    def bind(n,h):
        n=n.replace('\\','/')
        assert sha((ROOT/n).read_bytes())==h,n
        assert n not in sources or sources[n]==h,n;sources[n]=h
    for path in a.proof:
        p=workspace_path(path);b=p.read_bytes();proof=json.loads(b);assert 'PASS_NOT_BOARD' in proof['status']
        for n,h in proof['source_sha256'].items():
            # These runners conservatively inventory all headers, including
            # the renderer-only page header they never include or compile.
            # Retain their original receipt; do not rebind it after text edits.
            if n.replace('\\','/')=='linux/xinyi/xinyi_home_r13.h' and proof['status'] in [
                'REAL_MAIN_LOOP_HOST_RV32_PASS_NOT_BOARD','HOST_RV32_RUNTIME_INTEGRATION_PASS_NOT_BOARD'] and sha((ROOT/n).read_bytes())!=h:
                unused_header_drift.append(dict(proof=p.parent.name,path=n,original_sha256=h,
                    current_sha256=sha((ROOT/n).read_bytes()),reason='Renderer header is not compiled by this runtime/main fixture'))
            else:bind(n,h)
        proofs.append(proof);payload['evidence/'+p.parent.name+'.json']=b
    assert any({r['target'] for r in p.get('runs',[])}=={'host','sanitizer','rv32','scalar-oracle'} for p in proofs)
    assert any(p.get('gui_double_buffer') and p.get('ui_feedback') for p in proofs)
    assert any('RUNTIME_R13_PREVIEW_EXCLUSIVE_CANCEL_START_DRAIN_FAILURE_RECOVERY_EXIT_PASS' in p.get('tests',[]) for p in proofs)
    def run(n,args,limit=180):
        with (out/(n+'.log')).open('xb') as f:
            p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=3 '+str(limit)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=limit+15)
        assert not p.returncode,(n,(out/(n+'.log')).read_text(errors='replace')[-2400:])
    def lexical(p):
        s=p.absolute().as_posix();assert p.absolute().is_relative_to(ROOT/'build');return '/mnt/'+s[0].lower()+s[2:]
    programs={}
    result=dict(status='FAILED_PRESERVED',hardware_used=False,installed=False,programs=programs)
    try:
        for hz in [60000000,75000000]:
            name='cpu'+str(hz//1000000);folder=out/name
            env=['XINYI_CPU_HZ='+str(hz),'XINYI_HOME_R13=1','XINYI_GUI_DOUBLE_BUFFER=1','XINYI_UI_FEEDBACK=1','XINYI_COACH_MOVE_AUDIO=1']
            if a.reuse_build:
                prior=workspace_path(a.reuse_build)/name
                assert prior.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
                assert 'home_r13=1' in (prior/'gui-config.txt').read_text()
                assert (prior/'cpu-hz.txt').read_text().strip()==str(hz)
                folder.mkdir()
                for n in ['xinyi-one','source-before.sha256','source-after.sha256','gui-config.txt','cpu-hz.txt','compiler.txt']:
                    shutil.copyfile(prior/n,folder/n);assert (prior/n).read_bytes()==(folder/n).read_bytes()
            else:
                run(name+'-build',['env',*env,'sh',wsl_path(ROOT/'linux/xinyi_board/build.sh'),lexical(a.output/name)])
            assert (folder/'source-before.sha256').read_bytes()==(folder/'source-after.sha256').read_bytes()
            for line in (folder/'source-before.sha256').read_text().splitlines():
                h,n=line.split(None,1);prefix=wsl_path(ROOT)+'/';assert n.startswith(prefix);bind(n[len(prefix):],h)
            elf=out/(name+'.elf');run(name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),wsl_path(folder/'xinyi-one')],30)
            old,new=inspect(folder/'xinyi-one'),inspect(elf);assert old['allocated']==new['allocated'] and old['entry']==new['entry'] and old['flags']==new['flags']
            b=elf.read_bytes();payload['software/'+name+'/gui.rv32.elf']=b
            programs[name]=dict(cpu_hz=hz,bytes=len(b),sha256=sha(b),source_bindings_sha256=sha((folder/'source-before.sha256').read_bytes()),elf_sections_preserved=True)
        for n in ['linux/xinyi/gen_font.py','linux/xinyi/gen_home_background.py','linux/xinyi/fonts/XinyiProductSans.ttf',
                  'linux/xinyi/fonts/source.json','linux/xinyi/fonts/glyphs.json','linux/xinyi/fonts/home-background.json',
                  'linux/xinyi/fonts/OFL.txt','scripts/prepare_xinyi_home_r13.py','scripts/verify_xinyi_elf.py','scripts/picture_workspace.py']:
            bind(n,sha((ROOT/n).read_bytes()))
        for n,h in sources.items():
            b=(ROOT/n).read_bytes();assert sha(b)==h;payload['source/'+n]=b
        payload['README.md']=('''# Offline native home r13

CPU60 and CPU75 GUI binaries, exact source inputs and synthetic previews only.
No model, photo, frame, position, recognition worker, audio helper/PCM, kernel,
rootfs, boot selector or installer. Not installed or board-tested.

Build flags: XINYI_HOME_R13=1 XINYI_GUI_DOUBLE_BUFFER=1 XINYI_UI_FEEDBACK=1
XINYI_COACH_MOVE_AUDIO=1. Existing matching r11 speech helper/move PCM required.
CPU60 displays labeled E42 synthesis-subtree references; CPU75 resource fields
remain unbound. Scores/rates and CPU/FPGA speedups without matching measurements
remain pending. Historical P3 ROM data is a separate CoreMark detail view.

The camera menu offers instructions then exclusive full-screen preview. Esc
stops and drains before returning home. Exit releases resources to Linux.
No camera or hardware has been accessed by these offline checks/builds.

Font/background generation uses the recorded Pillow/fontTools environment;
generated headers and the OFL font subset are included for binary rebuilds.
''').encode()
        host=next(workspace_path(p).parent/'host' for p in a.proof if (workspace_path(p).parent/'host/home.rgb565').is_file())
        # Optional preview PNGs are generated by the separate exact renderer
        # conversion; never include raw real frames or private result packets.
        for n in ['home','benchmark','history','camera']:
            if (host/(n+'.png')).is_file():payload['preview/'+n+'.png']=(host/(n+'.png')).read_bytes()
        manifest=dict(schema='xinyi-home-r13/1',hardware_used=False,installed=False,programs=programs,sources_sha256=sources,
            original_proofs_retained_unused_header_drift=unused_header_drift,
            members={n:dict(bytes=len(b),sha256=sha(b)) for n,b in payload.items()})
        payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
        archive=out/'xinyi-home-offline-r13-r01.zip'
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for n,b in sorted(payload.items()):z.writestr(n,b)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for n,row in manifest['members'].items():assert sha(z.read(n))==row['sha256']
            export=out/'exported';export.mkdir();z.extractall(export)
        native=wsl_path(export/'source')
        for hz in [60000000,75000000]:
            name='cpu'+str(hz//1000000);destination=native+'/build/'+name
            run(name+'-export-rebuild',['env','XINYI_CPU_HZ='+str(hz),'XINYI_HOME_R13=1','XINYI_GUI_DOUBLE_BUFFER=1',
                'XINYI_UI_FEEDBACK=1','XINYI_COACH_MOVE_AUDIO=1','sh',native+'/linux/xinyi_board/build.sh',destination])
            rebuilt=out/(name+'-export.elf');run(name+'-export-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all',
                '-o',wsl_path(rebuilt),destination+'/xinyi-one'],30)
            assert rebuilt.read_bytes()==(out/(name+'.elf')).read_bytes(),name
            programs[name]['zip_source_rebuild_byte_equal']=True
        assert all(sha((ROOT/n).read_bytes())==h for n,h in sources.items())
        result.update(status='R13_TWO_GUI_BUILDS_AND_ZIP_SOURCE_EXACT_REBUILDS_PASS_NOT_BOARD',
            source_sha256=sources,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive.read_bytes()),members=len(payload),sha_crc_pass=True))
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
