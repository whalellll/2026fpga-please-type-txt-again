"""Independent r07 ZIP export, fused unit test and exact two-worker rebuild."""
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
    for name in ['archive','models','output']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    archive=workspace_path(a.archive);models=workspace_path(a.models);sha=lambda b:hashlib.sha256(b).hexdigest()
    originals={};result=dict(status='FAILED_PRESERVED',hardware_used=False)
    try:
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            m=json.loads(z.read('manifest.json'));assert m['schema']=='picture-software-offline-r07-v1'
            assert set(z.namelist())==set(m['payloads'])|{'manifest.json'}
            for path,info in m['payloads'].items():
                rel=PurePosixPath(path);assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in path and ':' not in path
                data=z.read(path);assert len(data)==info['bytes'] and sha(data)==info['sha256']
                if path.startswith('source/'):
                    target=out/path;target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as f:f.write(data)
            for name,info in m['binaries'].items():
                data=z.read('software/'+name+'/worker.rv32.elf');assert sha(data)==info['sha256']
                assert gzip.decompress(z.read('software/'+name+'/worker.rv32.elf.gz'))==data;originals[name]=data
        assert all(sha((models/path).read_bytes())==digest for path,digest in m['model_sha256'].items())
        source=out/'source'

        def run(name,args,seconds=180):
            with (out/(name+'.log')).open('xb') as f:
                p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                    'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],
                    stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
            assert not p.returncode,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
        for name,options in m['software_options'].items():
            build=source/'build'/('rebuilt-'+name)
            run(name+'-build',['env',*[k+'='+v for k,v in options.items()],'sh',wsl_path(source/'linux/picture_new/build_native_coach.sh'),
                wsl_path(source),wsl_path(build),wsl_path(models),'rv32'])
            elf=out/('rebuilt-'+name+'.elf')
            run(name+'-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(elf),wsl_path(build/'xq-coach-worker')],30)
            assert elf.read_bytes()==originals[name],(name,'full-byte rebuild mismatch')
        generated=out/'fused-unit-source.c'
        run('generate-unit',['python3',wsl_path(source/'scripts/generate_picture_geometry_fused.py'),'--output',wsl_path(generated)])
        includes=['linux/picture_new','linux/vision','linux/mac_accel','sw/xiangqi','sw/bootloader','artifacts/vision-model-20261020-adapter/runtime']
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
        flags+=['-I'+wsl_path(source/p) for p in includes]
        flags+=['-D'+name+'=1' for name in ['XQ_GEOMETRY_GRAY_TABLE','XQ_GEOMETRY_FAST','XQ_GEOMETRY_ARITH',
            'XQ_GEOMETRY_COMPACT','XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND','XQ_GEOMETRY_FUSED']]
        binary=out/'fused-unit'
        run('unit-build',['cc',*flags,'-DGEOMETRY_SOURCE="'+wsl_path(generated)+'"',
            wsl_path(source/'linux/picture_new/test_geometry_fused.c'),wsl_path(source/'sw/bootloader/crc32_fast.c'),
            '-Wl,--gc-sections','-lm','-o',wsl_path(binary)])
        run('unit',[wsl_path(binary)],90)
        result.update(status='R07_EXPORTED_BOTH_WORKERS_BYTE_REPRODUCIBLE_FUSED_UNIT_PASS_NOT_BOARD',
            archive_sha256=sha(archive.read_bytes()),archive_members=len(m['payloads'])+1,
            all_payload_hashes_pass=True,both_exported_rv32_workers_full_bytes_equal=True,
            generated_cancel_and_fused_overlays_rebuilt=True,exported_fused_unit_pass=True,
            unchanged_graph_kernel_loader_suites_not_repeated=True)
    finally:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__=='__main__':main()
