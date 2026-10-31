"""Build and package checked RAM software only; no device/media access."""
from pathlib import Path
import argparse,gzip,hashlib,io,json,re,shlex,subprocess,tarfile,zipfile
from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['coach-proof','tail-proof','board-checked-worker','output']:
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--historical-proof',type=Path,default=ROOT/'docs/validation/picture-e42-integration-20261026/grid-guard-plan-20261027.json')
    ap.add_argument('--desktop-directory',type=Path)
    ap.add_argument('--revision',choices=['r01','r02'],default='r02')
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sha=lambda data:hashlib.sha256(data).hexdigest()
    read_json=lambda q:json.loads(q.read_text())
    coach=workspace_path(a.coach_proof);tail=read_json(workspace_path(a.tail_proof));checked=read_json(coach/'result.json')
    historical=read_json(a.historical_proof);old=workspace_path(a.board_checked_worker)
    assert checked['status']=='PASS' and not checked['hardware_used'] and checked['hwc_tail_columns_candidate']
    assert tail['status']=='TAIL_COLUMNS_HOST_RV32_SANITIZERS_FULL_HEADS_PASS_NOT_BOARD'
    assert historical['actual_board_same_frame']['packet_equals_correct_cpu']
    assert sha(old.read_bytes())==historical['rv32_stripped_worker_sha256']
    sources=checked['sources_sha256'];assert all(sha((ROOT/q).read_bytes())==h for q,h in sources.items())
    native=checked['native_root'];assert re.fullmatch(r'/var/tmp/picture-coach-[0-9a-f]{32}',native)
    settings={'XQ_HWC_DETECTOR':'1','XQ_GRID_RECOVERY':'1','XQ_GRID_PLAN_FAST':'1','XQ_GRID_MODEL_GUARD':'1',
        'XQ_FAST_FP32_BILINEAR':'1','XQ_GEOMETRY_FAST':'1','XQ_GEOMETRY_ARITH':'1','XQ_GEOMETRY_COMPACT':'1',
        'XQ_GEOMETRY_SELECTIVE':'1','XQ_GEOMETRY_SEED_BOUND':'1','XQ_HWC_WORD_INPUT':'1','XQ_HWC_RGB8_DIRECT':'1',
        'XQ_BOARD_CORNER_TABLE':'1','XQ_HWC_TAIL_COLUMNS':'0','XQ_HWC_TILE_EXPORT':'0','XQ_DETECTOR_LAZY_BOX':'0',
        'XQ_GEOMETRY_ADD':'0','XQ_GEOMETRY_ROW_LOCAL':'0','XQ_HWC_RGB_QUANT':'0','XQ_GRAPH_PROFILE':'0'}
    native_out=native+'/build/offline-tail0-'+sha(str(out).encode())[:12]
    argv=['env',*[k+'='+v for k,v in settings.items()],'sh',native+'/linux/picture_new/build_native_coach.sh',native,native_out,native+'/build/models','rv32']
    with (out/'baseline-build.log').open('xb') as f:
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5','180',*argv],stdout=f,stderr=subprocess.STDOUT,timeout=200)
    assert not r.returncode,(out/'baseline-build.log').read_text(errors='replace')[-2000:]
    names=['xq-coach-worker','runtime-config.txt','source-before.sha256','source-after.sha256','compiler.txt']
    r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','tar','-cf','-','-C',native_out,*names],capture_output=True,timeout=30);assert not r.returncode
    baseline=out/'guard-plan';baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:') as archive:
        for member in archive.getmembers():
            assert member.isfile() and member.name in names
            with (baseline/member.name).open('xb') as f:f.write(archive.extractfile(member).read())
    assert (baseline/'source-before.sha256').read_bytes()==(baseline/'source-after.sha256').read_bytes()
    # Every actual baseline build input is SHA-bound, including frozen model
    # inputs; model bytes are not included in this software-only package.
    baseline_sources={};baseline_models={}
    for line in (baseline/'source-before.sha256').read_text().splitlines():
        digest,name=line.split(maxsplit=1);assert name.startswith(native+'/')
        rel=name[len(native)+1:]
        if rel.startswith('build/models/'):baseline_models[rel.rsplit('/',1)[1]]=digest
        else:
            assert (ROOT/rel).is_file() and sha((ROOT/rel).read_bytes())==digest,rel
            baseline_sources[rel]=digest
    assert all(checked['models_sha256'][q]==h for q,h in baseline_models.items())
    payload={};binaries={}
    for name,original in [('guard-plan',baseline/'xq-coach-worker'),('tail-columns',coach/'worker-coach-qemu/xq-coach-worker')]:
        directory=out/name;directory.mkdir(exist_ok=True);stripped=directory/'worker.rv32.elf'
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(stripped),wsl_path(original)],capture_output=True,timeout=30);assert not r.returncode
        before,after=inspect(original),inspect(stripped)
        assert before['allocated']==after['allocated'] and before['entry']==after['entry'] and before['flags']==after['flags']
        if name=='guard-plan':
            assert stripped.read_bytes()==old.read_bytes(),'current baseline differs from board-checked binary'
        data=stripped.read_bytes();compressed=gzip.compress(data,mtime=0)
        payload['software/'+name+'/worker.rv32.elf']=data;payload['software/'+name+'/worker.rv32.elf.gz']=compressed
        config=(baseline/'runtime-config.txt') if name=='guard-plan' else (coach/'worker-coach-qemu/runtime-config.txt')
        payload['software/'+name+'/runtime-config.txt']=config.read_bytes()
        binaries[name]=dict(sha256=sha(data),bytes=len(data),gzip_sha256=sha(compressed),gzip_bytes=len(compressed),
            allocated_sections_entry_flags_equal=True,detector_jobs=166 if name=='guard-plan' else 152,
            historical_same_frame_board_checked=name=='guard-plan',physical_under_300s_accepted=False)
    combined={**sources,**baseline_sources,**tail['source_sha256']}
    extras=['scripts/prepare_picture_software_offline.py','scripts/check_picture_hwc_tail_columns.py',
        'scripts/check_picture_grid_plan.py','scripts/verify_xinyi_elf.py','scripts/picture_workspace.py',
        'linux/picture_new/hwc_fast/tests/test_tail_columns.c',
        'linux/picture_new/hwc_fast/tests/vision_exact_capture.h',
        'scripts/check_picture_software_package.py']
    combined.update({q:sha((ROOT/q).read_bytes()) for q in extras})
    for q,h in sorted(combined.items()):
        data=(ROOT/q).read_bytes();assert sha(data)==h;payload['source/'+q]=data
    common=' '.join(k+'='+v for k,v in settings.items() if k!='XQ_HWC_TAIL_COLUMNS')
    readme=f'''# Offline RAM software candidates — 2026-10-27

Board/media/capture operations are suspended by the user. This archive does
not install or activate software. Keep the original PN08 r02 package and SD.
Estimated-board display and recommendations after strict failure are retained.
Frozen weights/scales/geometry thresholds and integer math remain unchanged.

guard-plan: freshly rebuilt bytes exactly equal the historical RAM worker that
replayed the actual missing-rook frame correctly on e42. Worker242.163s is not
physical key-to-display timing; correct full-board<300s is still unaccepted.
tail-columns: same guard/plan software plus default-off first-layer narrow-column
planning (166->152 detector jobs). Complete synthetic heads and host/RV32 checks
pass. This candidate has never been tested on the board; no board speed claim.

Rebuild offline from source/ with the existing SHA-matched frozen models:

```sh
env {common} XQ_HWC_TAIL_COLUMNS=0 sh linux/picture_new/build_native_coach.sh "$PWD" "$PWD/build/guard-plan" /absolute/frozen-models rv32
env {common} XQ_HWC_TAIL_COLUMNS=1 sh linux/picture_new/build_native_coach.sh "$PWD" "$PWD/build/tail-columns" /absolute/frozen-models rv32
```

The checked static RV32IMA/ILP32 toolchain is /opt/toolchain/bin/
riscv32-linux-musl-gcc. Frozen model hashes, sources, selected options and binary
hashes are in manifest.json. This software-only archive contains no model packs,
photos, frames, requests, positions or live result packets. No new boot image,
kernel, RTL or SD update is created. Resume board work only after the user asks;
freshly audit link/runtime identity and engine/camera drain before any operation.
'''
    payload['README.md']=readme.encode()
    manifest=dict(schema='picture-software-offline-r04-v1',status='OFFLINE_CANDIDATES_PREPARED_NOT_INSTALLED',
        date='2026-10-27',board_accessed=False,sd_or_flash_written=False,models_included=False,
        private_payloads_included=False,training_or_rtl_changed=False,estimated_recommendations_preserved=True,
        original_pn08_delivery_unchanged=True,binaries=binaries,model_sha256=baseline_models,sources_sha256=combined,
        baseline_compiled_sources_sha256=baseline_sources,tail_compiled_sources_sha256=sources,
        software_options=settings,revision=a.revision,
        validation=dict(tail_heads_and_faults_pass=True,host_rv32_ipc_cancel_reuse_drain_pass=True,
            historical_same_frame_board_checked_binary_identical=True,new_board_validation=False,
            correct_physical_display_under_300s_pending=True),
        payloads={q:dict(bytes=len(data),sha256=sha(data)) for q,data in sorted(payload.items())})
    payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    forbidden={'.rgb565','.png','.jpg','.jpeg','.f32','.xqm','.xqi'}
    assert all(Path(q).suffix.lower() not in forbidden and Path(q).name not in ['request.txt','result.txt','release9.txt'] for q in payload)
    archive_path=out/('xinyi-software-offline-r04-'+a.revision+'-20261027.zip')
    with zipfile.ZipFile(archive_path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for q,data in sorted(payload.items()):
            item=zipfile.ZipInfo(q,date_time=(2026,10,27,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            item.external_attr=0o100644<<16;z.writestr(item,data)
    with zipfile.ZipFile(archive_path) as z:
        assert z.testzip() is None and set(z.namelist())==set(payload)
        assert all(z.read(q)==data for q,data in payload.items())
    assert all(sha((ROOT/q).read_bytes())==h for q,h in combined.items())
    receipt=dict(status='SOFTWARE_OFFLINE_PACKAGE_VERIFIED_NOT_INSTALLED',hardware_used=False,
        archive_bytes=archive_path.stat().st_size,archive_sha256=sha(archive_path.read_bytes()),
        members=len(payload),source_entries=len(combined),binaries=binaries,manifest=manifest,
        archive_no_private_payloads=True,original_board_checked_worker_unchanged=True)
    if a.desktop_directory:
        destination=a.desktop_directory/archive_path.name;assert destination.parent.is_dir() and not destination.exists()
        with destination.open('xb') as f:f.write(archive_path.read_bytes())
        assert sha(destination.read_bytes())==receipt['archive_sha256'];receipt['desktop_package']=str(destination)
        with destination.with_suffix('.zip.sha256').open('x') as f:f.write(receipt['archive_sha256']+'  '+destination.name+'\n')
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({q:receipt[q] for q in ['status','archive_bytes','archive_sha256','members','source_entries']},indent=2))
if __name__=='__main__':main()
