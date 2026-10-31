"""Check/export r11 source and independently reproduce all four RV32 programs."""
import argparse,gzip,hashlib,json,shlex,subprocess,zipfile
from pathlib import Path,PurePosixPath
from picture_workspace import ROOT,workspace_path,wsl_path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['archive','output']:ap.add_argument('--'+n,required=True,type=Path)
    a=ap.parse_args();out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    archive=workspace_path(a.archive);sha=lambda b:hashlib.sha256(b).hexdigest();result=dict(status='FAILED_PRESERVED',hardware_used=False)
    try:
        programs={}
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            m=json.loads(z.read('manifest.json'));assert m['schema']=='xinyi-ui-audio-r11-v1'
            assert set(z.namelist())==set(m['payloads'])|{'manifest.json'}
            for n,r in m['payloads'].items():
                p=PurePosixPath(n);assert not p.is_absolute() and '..' not in p.parts and ':' not in n and '\\' not in n
                b=z.read(n);assert len(b)==r['bytes'] and sha(b)==r['sha256']
                if n.startswith('source/'):
                    f=out/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
            for n,h in m['sources_sha256'].items():assert sha(z.read('source/'+n))==h
            for n,r in m['binaries'].items():
                b=z.read('software/'+n+'/program.rv32.elf');assert sha(b)==r['sha256']
                assert gzip.decompress(z.read('software/'+n+'/program.rv32.elf.gz'))==b;programs[n]=b
            assets=json.loads(z.read('pcm/move/manifest.json'));assert len(assets['files'])==24 and not assets['over_budget']
            for n,r in assets['files'].items():
                b=z.read('pcm/move/'+n);assert sha(b)==r['sha256'] and len(b)==r['samples']*2 and 0<len(b)<=7680
        src=out/'source'
        def run(n,args,limit=180):
            with (out/(n+'.log')).open('xb') as log:
                p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=5 '+str(limit)+' '+shlex.join(args)],
                    stdout=log,stderr=subprocess.STDOUT,timeout=limit+20)
            assert p.returncode==0,(n,(out/(n+'.log')).read_text(errors='replace')[-2000:])
        for n,r in m['binaries'].items():
            speech=r['speech'];variant=int(r['candidate']);folder=src/'build'/n
            env=['XINYI_COACH_MOVE_AUDIO='+str(variant)]
            if not speech:env+=['XINYI_CPU_HZ='+str(r['cpu_hz']),'XINYI_GUI_DOUBLE_BUFFER='+str(variant),'XINYI_UI_FEEDBACK='+str(variant)]
            script='build_speech.sh' if speech else 'build.sh'
            run(n+'-build',['env',*env,'sh',wsl_path(src/'linux/xinyi_board'/script),wsl_path(folder)])
            elf=out/(n+'.elf')
            run(n+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),
                wsl_path(folder/('xinyi-speech-worker' if speech else 'xinyi-one'))],30)
            assert elf.read_bytes()==programs[n],n+' exported rebuild differs'
        result.update(status='UI_AUDIO_R11_ZIP_ALL_FOUR_EXPORTED_BUILDS_BYTE_EQUAL_NOT_BOARD',
            archive_sha256=sha(archive.read_bytes()),members=len(m['payloads'])+1,source_entries=len(m['sources_sha256']),all_four_byte_equal=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
