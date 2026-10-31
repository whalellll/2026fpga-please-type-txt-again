"""Package the checked exact fused-geometry RAM candidate and reproducible source."""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
import zipfile

from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['coach-proof','fusion-proof','cancel-proof','ipc-proof','frames-proof','synthetic-proof','baseline-archive','output']:
        ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
    sha=lambda data:hashlib.sha256(data).hexdigest()
    load=lambda path:json.loads(workspace_path(path).read_text(encoding='utf-8'))
    coach_dir=workspace_path(a.coach_proof);coach=load(coach_dir/'result.json')
    fusion,cancel,ipc,frames,synthetic=[load(getattr(a,n+'_proof')) for n in ['fusion','cancel','ipc','frames','synthetic']]
    assert coach['status']=='PASS' and coach['geometry_fused_candidate'] and coach['geometry_cancel_candidate']
    assert fusion['status']=='GEOMETRY_FUSED_FULL_ARRAYS_PAIRED_BITS_NEGATIVE_CONTROLS_PASS_NOT_BOARD'
    assert cancel['status']=='GEOMETRY_FUSED_CANCEL_13_PHASE_OOM_MEMORY_FULL_BITS_PASS_NOT_BOARD'
    assert ipc['status']=='REAL_GEOMETRY_MID_PREFIX_CANCEL_RELEASE9_IDLE_NEW_GENERATION_FULL_PACKET_PASS_NOT_BOARD' and ipc['geometry_fused']
    assert frames['status']=='R07_FUSED_GEOMETRY_FIVE_PRIVATE_FRAMES_PASS_NOT_BOARD'
    assert synthetic['status']=='SYNTHETIC_CORRESPONDENCE_EIGHT_CONTROLS_FUSED_BITS_PASS_NOT_BOARD'
    assert all(not p['hardware_used'] for p in [coach,fusion,cancel,ipc,frames,synthetic])
    old=a.baseline_archive.resolve();old_bytes=old.read_bytes()
    assert sha(old_bytes)=='a2f107d30590f24aa3ccd4763a961b423de1f85f0a5b1ca39c9e91aca413e496'
    with zipfile.ZipFile(old) as z:
        old_manifest=json.loads(z.read('manifest.json'))
        old_worker=z.read('software/concat-cancel-tail/worker.rv32.elf')
    assert sha(old_worker)=='d6af455b84928e0f7a4f973acb2e13d0cc58f876c4bd1d7f6bab4a9cd57433da'
    combined={}
    for proof in [coach,fusion,cancel,synthetic]:
        for path,digest in proof.get('sources_sha256',proof.get('source_sha256',{})).items():
            assert sha((ROOT/path).read_bytes())==digest,(path,'source drift')
            assert path not in combined or combined[path]==digest
            combined[path]=digest
    # Export the entire previously complete source closure, refreshed to the
    # current inputs. Historical r05 worker identity is independently checked.
    for path in old_manifest['sources_sha256']:
        combined[path]=sha((ROOT/path).read_bytes())
    extras=['scripts/prepare_picture_software_r07.py','scripts/check_picture_software_r07_package.py',
        'scripts/check_picture_geometry_cancel_ipc.py','scripts/picture_workspace.py','scripts/verify_xinyi_elf.py']
    for path in extras:combined[path]=sha((ROOT/path).read_bytes())
    native=coach['native_root'];assert re.fullmatch(r'/var/tmp/picture-coach-[0-9a-f]{32}',native)
    baseline_options=dict(old_manifest['software_options']['concat-cancel-tail'],XQ_GEOMETRY_FUSED='0')
    candidate_options=dict(baseline_options,XQ_GEOMETRY_FUSED='1')
    native_out=native+'/build/r07-default0-'+sha(str(out).encode())[:12]
    with (out/'baseline-build.log').open('xb') as log:
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5','180','env',
            *[k+'='+v for k,v in baseline_options.items()],'sh',native+'/linux/picture_new/build_native_coach.sh',
            native,native_out,native+'/build/models','rv32'],stdout=log,stderr=subprocess.STDOUT,timeout=200)
    assert not r.returncode,(out/'baseline-build.log').read_text(errors='replace')[-2000:]
    names=['xq-coach-worker','runtime-config.txt','source-before.sha256','source-after.sha256','compiler.txt']
    r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','tar','-cf','-','-C',native_out,*names],capture_output=True,timeout=30)
    assert not r.returncode
    baseline=out/'r05-reference';baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:') as tar:
        for member in tar.getmembers():
            assert member.isfile() and member.name in names
            (baseline/member.name).write_bytes(tar.extractfile(member).read())
    assert (baseline/'source-before.sha256').read_bytes()==(baseline/'source-after.sha256').read_bytes()
    models={};compiled_baseline={}
    for line in (baseline/'source-before.sha256').read_text().splitlines():
        digest,path=line.split(maxsplit=1);assert path.startswith(native+'/');path=path[len(native)+1:]
        if path.startswith('build/models/'):models[path.rsplit('/',1)[1]]=digest
        else:
            assert sha((ROOT/path).read_bytes())==digest,path
            combined[path]=digest;compiled_baseline[path]=digest
    assert all(coach['models_sha256'][p]==h for p,h in models.items())
    payload={};binaries={};options={}
    for name,worker,config,settings in [
        ('r05-reference',baseline/'xq-coach-worker',baseline/'runtime-config.txt',baseline_options),
        ('fused-concat-cancel-tail',coach_dir/'worker-coach-qemu/xq-coach-worker',
            coach_dir/'worker-coach-qemu/runtime-config.txt',candidate_options),
    ]:
        directory=out/name;directory.mkdir(exist_ok=True);stripped=directory/'worker.rv32.elf'
        r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','/opt/toolchain/bin/riscv32-linux-musl-strip',
            '--strip-all','-o',wsl_path(stripped),wsl_path(worker)],capture_output=True,timeout=30)
        assert not r.returncode
        before,after=inspect(worker),inspect(stripped)
        assert before['allocated']==after['allocated'] and before['entry']==after['entry'] and before['flags']==after['flags']
        data=stripped.read_bytes()
        if name=='r05-reference':assert data==old_worker,'default0 changed historical r05 bytes'
        payload['software/'+name+'/worker.rv32.elf']=data
        compressed=gzip.compress(data,mtime=0)
        payload['software/'+name+'/worker.rv32.elf.gz']=compressed
        payload['software/'+name+'/runtime-config.txt']=config.read_bytes()
        options[name]=settings
        binaries[name]=dict(sha256=sha(data),bytes=len(data),gzip_sha256=sha(compressed),gzip_bytes=len(compressed),
            allocated_sections_entry_flags_equal=True,detector_jobs=152,new_board_tested=False)
    for path,digest in sorted(combined.items()):
        data=(ROOT/path).read_bytes();assert sha(data)==digest
        payload['source/'+path]=data
    evidence=dict(fusion_arrays_and_four_private_geometry=fusion,
        cancellation_and_memory=cancel,synthetic_correspondence=synthetic,
        five_private_complete_packets=dict(status=frames['status'],cases=frames['cases'],device_drain_mocked=True),
        real_mid_prefix_cancel=dict(status=ipc['status'],geometry_fused=True,device_drain_mocked=True),
        original_failed_frame_not_fixed=True,physical_correct_hdmi_under300s=False)
    payload['evidence/offline-summary.json']=(json.dumps(evidence,indent=2)+'\n').encode()
    commands=[]
    for name,settings in options.items():
        commands.append('env '+' '.join(k+'='+v for k,v in settings.items())+
            ' sh linux/picture_new/build_native_coach.sh "$PWD" "$PWD/build/'+name+'" /absolute/frozen-models rv32')
    payload['README.md']=('''# Offline software r07: exact geometry fusion

Software/source/evidence only. No model packs, photos, positions, real packets,
boot files or installer. Do not install or use devices from this package.
Board operations remain suspended. PN08/r04/r05 and model handoff stay unchanged.

r05-reference: XQ_GEOMETRY_FUSED=0 rebuild is FULL-BYTE IDENTICAL to the
historical r05 concat-cancel-tail worker d6af455b. Same frozen models/thresholds.
fused-concat-cancel-tail: default0 new option, exact window reduction/consumer
fusion and removal of unused tmp. No prefix/QR/RNG/threshold changes. Explicit
cancellation is preserved. Both workers use152 detector jobs.

Host/RV32/sanitizers:18 array/alias cases, four full geometry inputs,13 real
cancel phases/OOM/recovery. Five complete private host packets remain equal;
the older incorrect frame remains incorrect. Device/drain are mocked.
Actual allocator total/peak saves one ROI double buffer (2.67-3.14MB for four
inputs), not observed DDR traffic. Small host/QEMU paired gains are not board
or whole-product latency evidence. No correct physical under300s acceptance.

Rebuild in source/ with the same frozen model files (not included):

```sh
'''+ '\n'.join(commands)+'''
```

Use pinned /opt/toolchain/bin/riscv32-linux-musl-gcc, RV32IMA/ILP32 static musl.
Cancellation overlay is generated first, then fusion. Both transformations
reverse to their exact input source bytes. Exported tests are synthetic or
require separately authorized private fixtures; never access sealed datasets.
Default0 source is current r07, not retroactively attributed to the old r05
source manifest. The exact old-worker comparison establishes rollback bytes.
''').encode()
    manifest=dict(schema='picture-software-offline-r07-v1',status='OFFLINE_R07_NOT_INSTALLED_NOT_BOARD_TESTED',
        date='2026-10-27',hardware_used=False,model_packs_included=False,private_payloads_included=False,
        estimated_board_recommendations_preserved=True,binaries=binaries,model_sha256=models,
        sources_sha256=combined,compiled_baseline_sources_sha256=compiled_baseline,
        compiled_candidate_sources_sha256=coach['sources_sha256'],software_options=options,
        original_r05_archive_sha256=sha(old_bytes),default0_equals_original_r05_worker=True,
        validation=dict(arrays_18_per_target=True,host_rv32_sanitizers=True,four_geometry_inputs_full_bits=True,
            eight_synthetic_controls=True,real_13_phase_cancel_oom_recovery=True,allocator_total_peak_measured=True,
            five_private_complete_packets_equal=True,mid_prefix_cancel_then_next_packet_equal=True,
            device_drain_mocked=True,new_board_validation=False),
        payloads={path:dict(bytes=len(data),sha256=sha(data)) for path,data in sorted(payload.items())})
    payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    assert all(Path(path).suffix.lower() not in {'.png','.jpg','.jpeg','.rgb565','.f32','.xqm','.xqi','.bin'} for path in payload)
    assert all(Path(path).name not in {'request.txt','result.txt','release9.txt'} for path in payload)
    archive=out/'xinyi-software-offline-r07-r01-20261027.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,data in sorted(payload.items()):
            item=zipfile.ZipInfo(path,date_time=(2026,10,27,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            item.external_attr=0o100644<<16;z.writestr(item,data)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None and set(z.namelist())==set(payload)
    assert old.read_bytes()==old_bytes and all(sha((ROOT/p).read_bytes())==h for p,h in combined.items())
    result=dict(status='R07_FUSED_SOFTWARE_PACKAGE_SEALED_NOT_INSTALLED',hardware_used=False,
        archive_bytes=archive.stat().st_size,archive_sha256=sha(archive.read_bytes()),members=len(payload),
        source_entries=len(combined),binaries=binaries,default0_old_r05_full_bytes_equal=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
