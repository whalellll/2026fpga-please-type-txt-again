"""Seal default-off auxiliary word-input candidate with current source bindings."""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import re
import shlex
import subprocess
import tarfile
import zipfile
from picture_workspace import ROOT,workspace_path,wsl_path
from verify_xinyi_elf import inspect


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ['coach-proof','word-proof','profile-proof','frames-proof','baseline-archive','output']:
        ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve());out.mkdir(exist_ok=False)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    load=lambda p:json.loads(workspace_path(p).read_text(encoding='utf-8'))
    coach=load(a.coach_proof/'result.json');word=load(a.word_proof);profile=load(a.profile_proof);frames=load(a.frames_proof)
    assert coach['status']=='PASS' and coach['exact_word_input_candidate'] and coach['geometry_fused_candidate']
    assert word['status']=='EXACT_WORD_INPUT_77_CASES_AUX_GRAPHS_CPU_IO_CANCEL_RECOVERY_PAIRS_PASS_NOT_BOARD'
    assert profile['status']=='AUX_FROZEN_EXACT_PROFILE_HOST_RV32_HEADS_EQUAL_NOT_BOARD' and profile['exact_word_input']
    assert frames['status']=='R08_EXACT_WORD_INPUT_FIVE_PRIVATE_FRAMES_PASS_NOT_BOARD' and len(frames['cases'])==5
    assert all(row['old_packet_unchanged'] for row in frames['cases'])
    old=workspace_path(a.baseline_archive);oldbytes=old.read_bytes()
    assert sha(oldbytes)=='62f4943edd0b388e024f40d098cf92a5852a39495e84242cc6c8b186b7d408c3'
    with zipfile.ZipFile(old) as z:
        m=json.loads(z.read('manifest.json'));oldworker=z.read('software/fused-concat-cancel-tail/worker.rv32.elf')
    assert sha(oldworker)=='9b431e11dc696e1433723d603d7f4c41a4358f0b1027168ed3a9910af38cbe28'
    sources={}
    for proof in [coach,word,profile]:
        for name,h in proof.get('sources_sha256',proof.get('source_sha256',{})).items():
            assert sha((ROOT/name).read_bytes())==h,(name,'source drift')
            assert name not in sources or sources[name]==h;sources[name]=h
    for name in m['sources_sha256']:sources[name]=sha((ROOT/name).read_bytes())
    for name in ['scripts/prepare_picture_software_r08.py','scripts/check_picture_software_r08_package.py',
        'scripts/verify_xinyi_elf.py','scripts/picture_workspace.py']:
        sources[name]=sha((ROOT/name).read_bytes())
    native=coach['native_root'];assert re.fullmatch(r'/var/tmp/picture-coach-[0-9a-f]{32}',native)
    options0=dict(m['software_options']['fused-concat-cancel-tail'],XQ_EXACT_WORD_INPUT='0')
    options1=dict(options0,XQ_EXACT_WORD_INPUT='1')
    nativeout=native+'/build/r08-default0'
    with (out/'baseline-build.log').open('xb') as f:
        p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','timeout','--kill-after=5','180','env',
            *[k+'='+v for k,v in options0.items()],'sh',native+'/linux/picture_new/build_native_coach.sh',
            native,nativeout,native+'/build/models','rv32'],stdout=f,stderr=subprocess.STDOUT,timeout=200)
    assert not p.returncode,(out/'baseline-build.log').read_text(errors='replace')[-1800:]
    names=['xq-coach-worker','runtime-config.txt','source-before.sha256','source-after.sha256','compiler.txt']
    p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','tar','-cf','-','-C',nativeout,*names],capture_output=True,timeout=30)
    assert not p.returncode
    baseline=out/'r07-reference';baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(p.stdout),mode='r:') as t:
        for item in t:
            assert item.isfile() and item.name in names
            (baseline/item.name).write_bytes(t.extractfile(item).read())
    assert (baseline/'source-before.sha256').read_bytes()==(baseline/'source-after.sha256').read_bytes()
    candidate=workspace_path(a.coach_proof)/'worker-coach-qemu'
    payload={};binaries={};options={}
    for name,folder,opts in [('r07-reference',baseline,options0),('word-input-fused-concat-cancel-tail',candidate,options1)]:
        worker=folder/'xq-coach-worker';stripped=out/(name+'.elf')
        p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','/opt/toolchain/bin/riscv32-linux-musl-strip',
            '--strip-all','-o',wsl_path(stripped),wsl_path(worker)],capture_output=True,timeout=30);assert not p.returncode
        before,after=inspect(worker),inspect(stripped)
        assert before['allocated']==after['allocated'] and before['entry']==after['entry'] and before['flags']==after['flags']
        data=stripped.read_bytes()
        if name=='r07-reference':assert data==oldworker,'default0 differs from old r07'
        compressed=gzip.compress(data,mtime=0)
        payload['software/'+name+'/worker.rv32.elf']=data
        payload['software/'+name+'/worker.rv32.elf.gz']=compressed
        payload['software/'+name+'/runtime-config.txt']=(folder/'runtime-config.txt').read_bytes()
        binaries[name]=dict(bytes=len(data),sha256=sha(data),gzip_bytes=len(compressed),gzip_sha256=sha(compressed),
            allocated_sections_entry_flags_equal=True,detector_jobs=152,new_board_tested=False)
        options[name]=opts
    for name,h in sorted(sources.items()):
        data=(ROOT/name).read_bytes();assert sha(data)==h;payload['source/'+name]=data
    evidence=dict(word_input=word,synthetic_aux_profile=profile,
        worker_ipc=dict(status=coach['status'],host_rv32=True,driver_drain_mocked=True),
        five_private_packets=dict(count=5,all_equal_to_r07=True,old_failure_not_fixed=True,driver_drain_mocked=True),
        geometry_and_detector_unchanged=True,physical_correct_display_under300s=False)
    payload['evidence/offline-summary.json']=(json.dumps(evidence,indent=2)+'\n').encode()
    commands=['env '+' '.join(k+'='+v for k,v in opts.items())+' sh linux/picture_new/build_native_coach.sh "$PWD" "$PWD/build/'+name+'" /absolute/frozen-models rv32' for name,opts in options.items()]
    payload['README.md']=('''# Offline software r08: auxiliary exact word input

Software/source/evidence only; no models, photos, real requests/positions or
packets, boot files or installer. New candidate is not installed/board-tested.
Board operations stay suspended; original PN08/r04/r05/r07 remain preserved.

New default0 XQ_EXACT_WORD_INPUT transposes compact aligned NCHW S8 normal-RAM
inputs to HWC with four-pixel/four-channel words in the existing auxiliary
exact convolution path. Detector HWC word input was already implemented;
this option serves ordinary board/classifier graphs. RGB3, halo/rectangles,
unaligned, overlapping, odd-plane and unsupported shapes retain scalar behavior.
No tensor allocation, quantization, job, lease, cancellation or numeric change.

r07-reference: default0 FULL-BYTE IDENTICAL to r07 9b431e11.
word-input-fused-concat-cancel-tail: new option1;152 detector jobs unchanged.
77 byte/guard cases per target; host/RV32/sanitizers actual frozen auxiliary
graphs vs CPU, classifier batches1/3/8, old capabilities, IO failure, cancel
and same-model recovery. Wrong channel permutation is rejected. Four warm
alternating pack-only CPU pairs are subphase clues, not board/cache/DDR data.
Five private complete host packets equal r07, including the retained old error.
Device/drain remain mocked. No new quality or physical under300s acceptance.

Use pinned RV32IMA/ILP32 static musl compiler, and separately supplied frozen
models whose identities are in manifest.json. From source/:

```sh
'''+ '\n'.join(commands)+'\n```\n').encode()
    manifest=dict(schema='picture-software-offline-r08-v1',date='2026-10-28',status='OFFLINE_R08_NOT_INSTALLED_NOT_BOARD_TESTED',
        hardware_used=False,model_packs_included=False,private_payloads_included=False,
        estimated_board_recommendations_preserved=True,original_r07_archive_sha256=sha(oldbytes),
        default0_equals_original_r07_worker=True,binaries=binaries,software_options=options,
        model_sha256=coach['models_sha256'],sources_sha256=sources,compiled_sources_sha256=coach['sources_sha256'],
        validation=dict(unit_77_host_rv32_sanitizers=True,frozen_aux_graph_cpu_bytes_equal=True,
            same_model_io_cancel_recovery=True,host_rv32_worker_ipc=True,five_private_packets_equal=True,
            geometry_detector_evidence_inherited_from_r07=True,device_drain_mocked=True),
        payloads={n:dict(bytes=len(b),sha256=sha(b)) for n,b in sorted(payload.items())})
    assert all(Path(n).suffix.lower() not in {'.png','.jpg','.rgb565','.f32','.xqm','.xqi','.bin'} for n in payload)
    payload['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=out/'xinyi-software-offline-r08-r01-20261028.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(payload.items()):
            item=zipfile.ZipInfo(n,(2026,10,28,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16;z.writestr(item,b)
    assert old.read_bytes()==oldbytes and all(sha((ROOT/n).read_bytes())==h for n,h in sources.items())
    result=dict(status='R08_WORD_INPUT_PACKAGE_SEALED_NOT_INSTALLED',hardware_used=False,
        archive_bytes=archive.stat().st_size,archive_sha256=sha(archive.read_bytes()),members=len(payload),
        source_entries=len(sources),binaries=binaries,default0_old_r07_full_bytes_equal=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
