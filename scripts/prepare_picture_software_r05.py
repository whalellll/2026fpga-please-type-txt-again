"""Seal checked r05 RAM workers and reproducible sources, without media access."""
import argparse,gzip,hashlib,io,json,re,subprocess,tarfile,zipfile
from pathlib import Path
from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['coach-proof','concat-proof','cancel-proof','ipc-proof','frames-proof','bench-proof','baseline-archive','output']:
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--desktop-directory',type=Path);a=ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sha=lambda b:hashlib.sha256(b).hexdigest();load=lambda p:json.loads(workspace_path(p).read_text())
    coach_dir=workspace_path(a.coach_proof);coach=load(coach_dir/'result.json')
    concat,cancel,ipc,frames,bench=[load(getattr(a,k+'_proof')) for k in ['concat','cancel','ipc','frames','bench']]
    assert coach['status']=='PASS' and coach['hwc_concat_view_candidate'] and coach['geometry_cancel_candidate'] and coach['hwc_tail_columns_candidate']
    assert concat['status']=='CONCAT_VIEW_HOST_RV32_SANITIZERS_FULL_HEADS_LIFETIME_PASS_NOT_BOARD'
    assert cancel['status']=='REAL_GEOMETRY_CANCEL_HOST_RV32_SANITIZERS_EXACT_OOM_RECOVERY_PASS_NOT_BOARD'
    assert ipc['status']=='REAL_GEOMETRY_MID_PREFIX_CANCEL_RELEASE9_IDLE_NEW_GENERATION_FULL_PACKET_PASS_NOT_BOARD'
    assert frames['status']=='R05_CONCAT_CANCEL_FIVE_PRIVATE_FRAMES_PASS_NOT_BOARD'
    assert bench['status']=='CONCAT_PAIRED_CPU_CLUE_EXACT_PACK_BYTES_PASS_NOT_BOARD'
    assert all(not d['hardware_used'] for d in [coach,concat,cancel,ipc,frames,bench])
    old=a.baseline_archive.resolve()
    assert sha(old.read_bytes())=='9cb6a84cdfff7bddb7fa198ed549b7f4c27fb4370320371cf23577b3abb99f04'
    with zipfile.ZipFile(old) as z:old_worker=z.read('software/guard-plan/worker.rv32.elf')
    assert sha(old_worker)=='57d20ea2bfdfbe96167c80b73ad162a7abd5df92c7d3f510f5036a48b98a1058'
    combined={}
    for proof in [coach,concat,cancel,bench]:
        for q,h in proof.get('sources_sha256',proof.get('source_sha256',{})).items():
            assert sha((ROOT/q).read_bytes())==h,(q,'proof source changed')
            assert q not in combined or combined[q]==h;combined[q]=h
    native=coach['native_root'];assert re.fullmatch(r'/var/tmp/picture-coach-[0-9a-f]{32}',native)
    settings={'XQ_HWC_DETECTOR':'1','XQ_GRID_RECOVERY':'1','XQ_GRID_PLAN_FAST':'1','XQ_GRID_MODEL_GUARD':'1',
        'XQ_FAST_FP32_BILINEAR':'1','XQ_GEOMETRY_FAST':'1','XQ_GEOMETRY_ARITH':'1','XQ_GEOMETRY_COMPACT':'1',
        'XQ_GEOMETRY_SELECTIVE':'1','XQ_GEOMETRY_SEED_BOUND':'1','XQ_HWC_WORD_INPUT':'1','XQ_HWC_RGB8_DIRECT':'1',
        'XQ_BOARD_CORNER_TABLE':'1','XQ_HWC_TAIL_COLUMNS':'0','XQ_HWC_CONCAT_VIEW':'0','XQ_GEOMETRY_CANCEL':'0',
        'XQ_HWC_TILE_EXPORT':'0','XQ_DETECTOR_LAZY_BOX':'0','XQ_GEOMETRY_ADD':'0','XQ_GEOMETRY_ROW_LOCAL':'0',
        'XQ_HWC_RGB_QUANT':'0','XQ_GRAPH_PROFILE':'0'}
    native_out=native+'/build/r05-baseline-'+sha(str(out).encode())[:12]
    with (out/'baseline-build.log').open('xb') as f:
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5','180','env',
            *[k+'='+v for k,v in settings.items()],'sh',native+'/linux/picture_new/build_native_coach.sh',native,native_out,native+'/build/models','rv32'],stdout=f,stderr=subprocess.STDOUT,timeout=200)
    assert not r.returncode,(out/'baseline-build.log').read_text(errors='replace')[-2000:]
    names=['xq-coach-worker','runtime-config.txt','source-before.sha256','source-after.sha256','compiler.txt']
    r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','tar','-cf','-','-C',native_out,*names],capture_output=True,timeout=30);assert not r.returncode
    baseline=out/'guard-plan';baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:') as archive:
        for member in archive.getmembers():
            assert member.isfile() and member.name in names
            (baseline/member.name).write_bytes(archive.extractfile(member).read())
    assert (baseline/'source-before.sha256').read_bytes()==(baseline/'source-after.sha256').read_bytes()
    compiled_baseline={};models={}
    for line in (baseline/'source-before.sha256').read_text().splitlines():
        digest,name=line.split(maxsplit=1);assert name.startswith(native+'/');rel=name[len(native)+1:]
        if rel.startswith('build/models/'):models[rel.rsplit('/',1)[1]]=digest
        else:
            assert sha((ROOT/rel).read_bytes())==digest;compiled_baseline[rel]=digest;combined[rel]=digest
    assert all(coach['models_sha256'][q]==h for q,h in models.items())
    payload={};binaries={};options={}
    candidate={**settings,'XQ_HWC_TAIL_COLUMNS':'1','XQ_HWC_CONCAT_VIEW':'1','XQ_GEOMETRY_CANCEL':'1'}
    for name,original,config,selected in [
        ('guard-plan',baseline/'xq-coach-worker',baseline/'runtime-config.txt',settings),
        ('concat-cancel-tail',coach_dir/'worker-coach-qemu/xq-coach-worker',coach_dir/'worker-coach-qemu/runtime-config.txt',candidate)]:
        directory=out/name;directory.mkdir(exist_ok=True);stripped=directory/'worker.rv32.elf'
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','/opt/toolchain/bin/riscv32-linux-musl-strip','--strip-all','-o',wsl_path(stripped),wsl_path(original)],capture_output=True,timeout=30);assert not r.returncode
        before,after=inspect(original),inspect(stripped)
        assert before['allocated']==after['allocated'] and before['entry']==after['entry'] and before['flags']==after['flags']
        data=stripped.read_bytes();compressed=gzip.compress(data,mtime=0)
        if name=='guard-plan':assert data==old_worker,'default-off rebuild changed historical worker'
        payload['software/'+name+'/worker.rv32.elf']=data;payload['software/'+name+'/worker.rv32.elf.gz']=compressed
        payload['software/'+name+'/runtime-config.txt']=config.read_bytes();options[name]=selected
        binaries[name]=dict(sha256=sha(data),bytes=len(data),gzip_sha256=sha(compressed),gzip_bytes=len(compressed),
            allocated_sections_entry_flags_equal=True,historical_same_frame_board_checked=name=='guard-plan',detector_jobs=166 if name=='guard-plan' else 152)
    extras=['scripts/prepare_picture_software_r05.py','scripts/check_picture_software_r05_package.py',
        'scripts/check_picture_geometry_cancel_ipc.py','scripts/picture_workspace.py','scripts/verify_xinyi_elf.py']
    for q in extras:combined[q]=sha((ROOT/q).read_bytes())
    for q,h in sorted(combined.items()):
        data=(ROOT/q).read_bytes();assert sha(data)==h;payload['source/'+q]=data
    validation=dict(real_geometry_13_phase_cancel_oom_recovery=True,host_rv32_sanitizers=True,
        uninterrupted_geometry_four_private_fixtures_bit_equal=True,full_heads_frozen_cpu_equal=True,
        concat_252_cases_per_target=True,missing_storage_cast_mutation_rejected=True,
        real_geometry_cancel_then_same_process_next_packet_equal=True,device_drain_mocked=True,
        five_authorized_private_complete_packets_equal=True,default_off_historical_worker_bytes_equal=True,
        new_board_validation=False,correct_physical_display_under_300s_pending=True)
    payload['evidence/offline-summary.json']=(json.dumps(dict(validation=validation,concat_cost={k:concat[k] for k in ['elided_nodes','elided_bytes','allocated_tensor_bytes','peak_tensor_bytes']},paired_cpu_clue=bench['results']),indent=2)+'\n').encode()
    commands=[]
    for name,selected in options.items():commands.append('env '+' '.join(k+'='+v for k,v in selected.items())+' sh linux/picture_new/build_native_coach.sh "$PWD" "$PWD/build/'+name+'" /absolute/frozen-models rv32')
    payload['README.md']=('''# Offline RAM software r05 - 2026-10-27

No board, media, capture, training, RTL or boot/kernel update. This archive does
not install or activate software. PN08 r02 and the r04 r02 archive stay unchanged.
Frozen weights/scales/thresholds and estimated-board recommendations are retained.

guard-plan: default-off rebuild exactly equals the historical board-checked RAM
worker. Its 242.163s saved-frame worker time excludes GUI/capture/recommendation.
concat-cancel-tail: new offline candidate, 166->152 detector jobs, nine direct
Concat views and cooperative cancellation inside real geometry. Never board-tested.
Materialization elided: 4,300,800 bytes. Tensor peak: 2,457,600 bytes. Host/QEMU
paired CPU clues are subphase measurements, not board/cache or full-board speed.
Correct physical key-to-display under300s remains pending for every candidate.

Rebuild from source/ using the existing SHA-matched frozen models (not included):

```sh
'''+ '\n'.join(commands)+'''
```

Use /opt/toolchain/bin/riscv32-linux-musl-gcc, RV32IMA/ILP32 static musl.
The geometry cancellation overlay is generated during the build and checked to
reverse exactly to its original source; it contains no numeric threshold change.
The archive contains no model packs, images, frames, positions or live packets.
Board operations remain suspended until the user explicitly resumes them.
''').encode()
    manifest=dict(schema='picture-software-offline-r05-v1',status='OFFLINE_CANDIDATE_PREPARED_NOT_INSTALLED',date='2026-10-27',
        board_accessed=False,models_included=False,private_payloads_included=False,estimated_recommendations_preserved=True,
        original_pn08_delivery_unchanged=True,binaries=binaries,model_sha256=models,sources_sha256=combined,
        compiled_baseline_sources_sha256=compiled_baseline,compiled_candidate_snapshot_sha256=coach['sources_sha256'],
        software_options=options,validation=validation,payloads={q:dict(bytes=len(b),sha256=sha(b)) for q,b in sorted(payload.items())})
    payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    forbidden={'.rgb565','.png','.jpg','.jpeg','.f32','.xqm','.xqi','.bin'}
    assert all(Path(q).suffix.lower() not in forbidden and Path(q).name not in ['request.txt','result.txt','release9.txt'] for q in payload)
    archive_path=out/'xinyi-software-offline-r05-r01-20261027.zip'
    with zipfile.ZipFile(archive_path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for q,b in sorted(payload.items()):
            item=zipfile.ZipInfo(q,date_time=(2026,10,27,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16;z.writestr(item,b)
    with zipfile.ZipFile(archive_path) as z:assert z.testzip() is None and set(z.namelist())==set(payload) and all(z.read(q)==b for q,b in payload.items())
    assert all(sha((ROOT/q).read_bytes())==h for q,h in combined.items()) and sha(old.read_bytes())=='9cb6a84cdfff7bddb7fa198ed549b7f4c27fb4370320371cf23577b3abb99f04'
    receipt=dict(status='R05_SOFTWARE_PACKAGE_VERIFIED_NOT_INSTALLED',hardware_used=False,archive_bytes=archive_path.stat().st_size,
        archive_sha256=sha(archive_path.read_bytes()),members=len(payload),source_entries=len(combined),binaries=binaries,manifest=manifest)
    if a.desktop_directory:
        destination=a.desktop_directory/archive_path.name;assert destination.parent.is_dir() and not destination.exists()
        with destination.open('xb') as f:f.write(archive_path.read_bytes())
        assert sha(destination.read_bytes())==receipt['archive_sha256'];receipt['desktop_package']=str(destination)
        with destination.with_suffix('.zip.sha256').open('x') as f:f.write(receipt['archive_sha256']+'  '+destination.name+'\n')
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({q:receipt[q] for q in ['status','archive_bytes','archive_sha256','members','source_entries','binaries']},indent=2))
if __name__=='__main__':main()
