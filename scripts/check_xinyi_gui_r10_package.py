"""Validate/export the GUI-only ZIP and independently rebuild all three GUIs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path,PurePosixPath
import shlex
import subprocess
import zipfile
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    archive=workspace_path(a.archive);sha=lambda b:hashlib.sha256(b).hexdigest();result=dict(status='FAILED_PRESERVED',hardware_used=False)
    try:
        workers={}
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            m=json.loads(z.read('manifest.json'));assert m['schema']=='xinyi-gui-offline-r10-v1'
            assert set(z.namelist())==set(m['payloads'])|{'manifest.json'}
            for n,info in m['payloads'].items():
                r=PurePosixPath(n);assert not r.is_absolute() and '..' not in r.parts and ':' not in n and '\\' not in n
                b=z.read(n);assert len(b)==info['bytes'] and sha(b)==info['sha256']
                if n.startswith('source/'):
                    target=out/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
            for n,info in m['binaries'].items():
                b=z.read('software/'+n+'/gui.rv32.elf');assert sha(b)==info['sha256']
                assert gzip.decompress(z.read('software/'+n+'/gui.rv32.elf.gz'))==b;workers[n]=b
        src=out/'source'
        def run(name,argv,seconds=180):
            with (out/(name+'.log')).open('xb') as f:
                r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                    'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(argv)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
            assert r.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2500:])
        for name,info in m['binaries'].items():
            build=src/'build'/name
            run(name,['env','XINYI_CPU_HZ='+str(info['cpu_hz']),'XINYI_GUI_DOUBLE_BUFFER='+str(int(info['double_buffer'])),
                'sh',wsl_path(src/'linux/xinyi_board/build.sh'),wsl_path(build)])
            elf=out/(name+'.elf')
            run(name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),wsl_path(build/'xinyi-one')],30)
            assert elf.read_bytes()==workers[name],name+' differs after source export'
        result.update(status='GUI_R10_ZIP_ALL_THREE_EXPORTED_BUILDS_BYTE_EQUAL_NOT_BOARD',
            archive_sha256=sha(archive.read_bytes()),members=len(m['payloads'])+1,
            source_entries=len(m['sources_sha256']),all_three_byte_equal=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
