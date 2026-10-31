"""Independently export r09 ZIP and reproduce both RV32 workers plus word unit."""
from pathlib import Path,PurePosixPath
import argparse
import gzip
import hashlib
import json
import shlex
import subprocess
import zipfile
from picture_workspace import ROOT,workspace_path,wsl_path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['archive','models','output']:ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(exist_ok=False)
    archive=workspace_path(a.archive);models=workspace_path(a.models);sha=lambda b:hashlib.sha256(b).hexdigest()
    result=dict(status='FAILED_PRESERVED',hardware_used=False)
    try:
        originals={}
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            m=json.loads(z.read('manifest.json'));assert m['schema']=='picture-software-offline-r09-v1'
            assert set(z.namelist())==set(m['payloads'])|{'manifest.json'}
            for name,info in m['payloads'].items():
                rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name and '\\' not in name
                b=z.read(name);assert len(b)==info['bytes'] and sha(b)==info['sha256']
                if name.startswith('source/'):
                    p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            for name,info in m['binaries'].items():
                b=z.read('software/'+name+'/worker.rv32.elf');assert sha(b)==info['sha256']
                assert gzip.decompress(z.read('software/'+name+'/worker.rv32.elf.gz'))==b;originals[name]=b
        assert all(sha((models/n).read_bytes())==h for n,h in m['model_sha256'].items())
        source=out/'source'
        def run(name,args,seconds=180):
            with (out/(name+'.log')).open('xb') as f:
                p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                    'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                    stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
            assert not p.returncode,(name,(out/(name+'.log')).read_text(errors='replace')[-1800:])
        for name,opts in m['software_options'].items():
            build=source/'build'/('rebuilt-'+name)
            run(name+'-build',['env',*[k+'='+v for k,v in opts.items()],'sh',wsl_path(source/'linux/picture_new/build_native_coach.sh'),wsl_path(source),wsl_path(build),wsl_path(models),'rv32'])
            elf=out/('rebuilt-'+name+'.elf')
            run(name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),wsl_path(build/'xq-coach-worker')],30)
            assert elf.read_bytes()==originals[name],name+' rebuild mismatch'
        unit=out/'exported-word-unit'
        run('word-unit-build',['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-I'+wsl_path(source/'linux/picture_new'),wsl_path(source/'linux/picture_new/test_exact_word_output.c'),'-o',wsl_path(unit)])
        run('word-unit',[wsl_path(unit)],30)
        result.update(status='R09_EXPORTED_BOTH_WORKERS_BYTE_REPRODUCIBLE_WORD_UNIT_PASS_NOT_BOARD',
            archive_sha256=sha(archive.read_bytes()),members=len(m['payloads'])+1,
            all_payload_hashes_pass=True,both_rv32_full_bytes_equal=True,exported_word_unit_pass=True,
            generated_geometry_cancel_fused_overlays_rebuilt=True,unrelated_heavy_suites_not_repeated=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
