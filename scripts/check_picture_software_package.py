"""Verify and rebuild exported software sources offline, without board access."""
import argparse,gzip,hashlib,json,re,shlex,subprocess,zipfile
from pathlib import Path,PurePosixPath
from picture_workspace import ROOT,workspace_path,wsl_path
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sha=lambda b:hashlib.sha256(b).hexdigest();archive=workspace_path(a.archive)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        manifest=json.loads(z.read('manifest.json'));payload=manifest['payloads']
        assert set(z.namelist())==set(payload)|{'manifest.json'}
        for name,proof in payload.items():
            rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name and ':' not in name
            data=z.read(name);assert len(data)==proof['bytes'] and sha(data)==proof['sha256']
            if name.startswith('source/'):
                q=out/name;q.parent.mkdir(parents=True,exist_ok=True)
                with q.open('xb') as f:f.write(data)
        for name,proof in manifest['binaries'].items():
            data=z.read('software/'+name+'/worker.rv32.elf')
            assert sha(data)==proof['sha256'] and gzip.decompress(z.read('software/'+name+'/worker.rv32.elf.gz'))==data
        original=z.read('software/guard-plan/worker.rv32.elf')
    source=out/'source';models=workspace_path(a.models)
    assert all(sha((models/q).read_bytes())==h for q,h in manifest['model_sha256'].items())
    def run(name,args,seconds=180):
        with (out/(name+'.log')).open('xb') as f:
            r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 '+str(seconds)+' '+shlex.join(args)],stdout=f,stderr=subprocess.STDOUT,timeout=seconds+20)
        assert not r.returncode,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
    includes=['linux/picture_new/hwc_fast','artifacts/vision-model-20261020-adapter/runtime','linux/picture_new','linux/vision','linux/mac_accel','sw/bootloader']
    flags=['-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-ffunction-sections','-fdata-sections']
    inc=['-I'+wsl_path(source/q) for q in includes]
    run('tail-unit-build',['cc',*flags,*inc,wsl_path(source/'linux/picture_new/hwc_fast/tests/test_tail_columns.c'),'-Wl,--gc-sections','-lm','-o',wsl_path(out/'tail-unit')])
    run('tail-unit',[wsl_path(out/'tail-unit')])
    # Compile the exported full-graph oracle as well: this catches headers
    # that are not used by a worker-only rebuild, such as the capture fixture.
    product=['linux/picture_new/hwc_fast/tests/product_adapter.c','linux/picture_new/hwc_fast/adapter.c',
        'linux/picture_new/hwc_fast/tests/picture_new_graph_mock.c','linux/picture_new/graph_runtime.c',
        'linux/picture_new/graph_tensor.c','linux/picture_new/graph_ops.c','linux/picture_new/graph_profile.c',
        'linux/picture_new/vision32_layer.c','linux/picture_new/vision32_backend.c',
        'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c','sw/bootloader/crc32_fast.c']
    extra=['-DXQ_HWC_DETECTOR=1','-DXQ_CLASSIFIER_S16=1','-DXQ_FAST_REQUANT=1','-DXQ_HWC_WORD_INPUT=1',
        '-DXQ_HWC_RGB8_DIRECT=1','-DXQ_HWC_TAIL_COLUMNS=1','-DXQIH_EXPECTED_JOBS=152']
    run('product-oracle-build',['cc',*flags,*inc,*extra,*[wsl_path(source/q) for q in product],
        '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl,--wrap=malloc,--wrap=calloc,--gc-sections','-lm','-o',wsl_path(out/'product-oracle')])
    native_out=source/'build/rebuilt-guard-plan'
    run('guard-plan-rv32-build',['env',*[k+'='+v for k,v in manifest['software_options'].items()],
        'sh',wsl_path(source/'linux/picture_new/build_native_coach.sh'),wsl_path(source),wsl_path(native_out),wsl_path(models),'rv32'])
    stripped=out/'rebuilt-guard-plan.rv32.elf'
    run('guard-plan-strip',['/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(stripped),wsl_path(native_out/'xq-coach-worker')],30)
    assert stripped.read_bytes()==original,'exported sources do not reproduce the board-checked worker'
    result=dict(status='EXPORTED_SOURCE_WORKER_BYTE_REPRODUCIBLE_TEST_DEPENDENCIES_COMPLETE_NOT_BOARD',
        hardware_used=False,archive_sha256=sha(archive.read_bytes()),archive_members=len(payload)+1,
        all_payload_hashes_pass=True,compressed_workers_identical=True,
        exported_tail_unit_pass=True,exported_full_graph_oracle_compiles=True,
        exported_rv32_worker_exact_bytes_equal=True,no_graph_rebenchmark=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
