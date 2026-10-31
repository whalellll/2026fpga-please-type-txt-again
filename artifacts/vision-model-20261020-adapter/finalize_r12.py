"""Bounded final identity/source/authorized-archive checks; no game-2 inference."""
import ast
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OUT=REPO/'docs/validation/picture-r12-engineering-20261022'
BUILD=REPO/'build/picture-r12-20261022'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def verify_manifest(root):
    manifest=load(root/'manifest.json')
    for name,item in manifest['files'].items():
        assert sha(root/name)==(item if isinstance(item,str) else item['sha256']),name
        if isinstance(item,dict) and 'bytes' in item:assert (root/name).stat().st_size==item['bytes'],name
    return len(manifest['files'])


def elf_identity(path):
    data=path.read_bytes()
    assert data[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<H',data,18)[0]==243
    assert struct.unpack_from('<I',data,36)[0]==0,'soft-float/no compressed flags required'
    offset=struct.unpack_from('<I',data,28)[0];size,count=struct.unpack_from('<HH',data,42)
    assert all(struct.unpack_from('<I',data,offset+i*size)[0]!=3 for i in range(count)),'static ELF required'
    return dict(sha256=sha(path),bytes=len(data),ELF='ELF32 little-endian RISC-V',flags=0,static=True)


def main():
    frozen=HERE.parent/'vision-model-20261020'
    old_identity=load(REPO/'docs/validation/picture-r08-offline-20261021/frozen-identity.json')
    assert sha(frozen/'manifest.json')==old_identity['frozen_manifest_sha256']
    assert load(frozen/'manifest.json')['release_version']=='3.0.0-contract'
    counts=dict(frozen_R2=verify_manifest(frozen))
    for release,date in [('r08','20261021'),('r09','20261021'),('r11','20261022'),('r12','20261022')]:
        counts[release]=verify_manifest(REPO/f'build/picture-{release}-{date}/delivery')
    assert counts==dict(frozen_R2=1789,r08=594,r09=876,r11=38,r12=94)
    exact=next((REPO/'build/picture-r08-20261021/delivery').rglob('exact_mm_int64_reference.py'))
    assert sha(exact)==sha(HERE/exact.name)
    intake=load(OUT/'intake.json')
    assert intake['status']=='PASS' and intake['full_manifest_coverage']
    assert sha(BUILD/'delivery/manifest.json')==intake['manifest_sha256']==sha(OUT/'delivery-manifest.json')
    for name,item in intake['archived_payloads'].items():
        assert sha(OUT/name)==sha(BUILD/'delivery'/item['source'])==item['sha256']
    assert len(intake['archived_payloads'])==90
    for path in (OUT/'truth_v2').glob('*.json'):
        value=load(path)
        if isinstance(value,dict) and 'imageData' in value:assert value['imageData'] is None
    assert len(list((OUT/'truth_v2').glob('*.json')))==86
    forbidden={'.png','.jpg','.jpeg','.rgb565','.pt','.onnx','.bin','.elf','.zip','.part'}
    assert not any(p.suffix.lower() in forbidden for p in OUT.rglob('*') if p.is_file())
    policy=load(OUT/'policy-and-official-summary.json')
    assert policy['r11_provisional_results_superseded'] and not policy['latency_waiver_granted']
    assert policy['aggregate_metrics']['E_v1_640_v3c']['strict_usable']==73
    working=load(HERE/'working_combination.json')
    assert working['selected']=='E-v1-640-v3c-r12' and working['default_backend']=='fp32'
    assert not any(working[k] for k in ('production_ready','quantized_main_available','board_deployed','latency_waiver_granted'))
    for name,profile in working['profiles'].items():
        for model,item in profile['models'].items():assert sha(REPO/profile['root']/item['path'])==item['sha256'],(name,model)
    assert load(HERE/'candidates/v2-band-r08/registration.json')['selected'] is False
    for candidate in ('det416-r09','det416mix-r11'):
        assert not load(HERE/'candidates'/candidate/'registration.json')['new_camera_domain_suitable']
    from r12_reference import resolve_selection
    try:resolve_selection(backend='quantized-mac')
    except ValueError as error:assert 'No exact-int64 INT8 payload' in str(error)
    else:raise AssertionError('E INT8 must fail closed')
    entries=load(OUT/'entrypoints-with-exact-rollback.json')
    assert entries['status']=='PASS' and len(entries['checks'])==7 and all(v['passed'] for v in entries['checks'].values())
    runtime=load(OUT/'runtime-controls.json')
    assert runtime['status']=='PASS' and runtime['strict_A_on_off_decisions_and_FEN_equal']
    for receipt in (intake,entries,runtime):assert receipt['game2_images_read']==receipt['game2_inference_runs']==0
    host=load(OUT/'gui-host-regression.json')
    assert host['status']=='PASS' and not host['full_suite_passed']
    assert all(sha(REPO/name)==digest for name,digest in host['inputs'].items())
    bank=load(OUT/'bank-and-budget.json')
    assert bank['actual_weight_bank_lines']==64 and bank['current_zero_RTL_gain_from_raising_capacity']==0
    assert not bank['latency_waiver_granted']
    target=BUILD/'target-r01/gui'
    assert (target/'engine-objects-before.sha256').read_bytes()==(target/'engine-objects-after.sha256').read_bytes()
    elf=(target/'elf-inspection.txt').read_text(encoding='utf-8')
    isa=re.search(r'Tag_RISCV_arch: "([^"]+)"',elf).group(1)
    assert isa.startswith('rv32i') and not re.search(r'(^|_)[cfd]\d',isa)
    compiler=(target/'compiler-identity.txt').read_text(encoding='utf-8')
    assert 'riscv' in compiler.lower() and re.search(r'[0-9a-f]{64}',compiler)
    write(OUT/'target-build.json',dict(status='PASS',scope='offline cross-compile only; not deployed',
        outputs={name:elf_identity(target/name) for name in ('xiangqi-pikafish-gui','xq-camera-capture')},isa=isa,
        compiler_identity=compiler,engine_objects_unchanged=True,
        engine_objects_receipt_sha256=sha(target/'engine-objects-before.sha256'),
        source_receipt='gui-host-regression.json inputs; all current source hashes reverified',
        hardware_used=False,deployed=False,SD_written=False))
    for name in ('runtime/xq_int8_layer.c','runtime/xq_resident_matrix.c'):
        path=HERE/name
        original=subprocess.check_output(['git','show','HEAD:'+path.relative_to(REPO).as_posix()],cwd=REPO)
        assert path.read_bytes().replace(b'\r\n',b'\n')==original.replace(b'\r\n',b'\n')
    scripts=[p for p in HERE.glob('*.py') if 'r12' in p.name or p.name in ('recognize_working.py','recognize_peer.py','r09_reference.py','pc_exact.py')]
    for path in scripts:ast.parse(path.read_text(encoding='utf-8'),filename=path.name)
    subprocess.run(['git','diff','--check'],cwd=REPO,check=True,capture_output=True)
    assert not subprocess.check_output(['git','status','--porcelain','--','rtl','ip','pds','VERSION'],cwd=REPO).strip()
    assert (REPO/'VERSION').read_text().strip()=='2.1'
    # Actual camera identities must stay private. Official r12 truth/report IDs
    # and FEN are specifically authorized acceptance material, not live IPC.
    private=REPO/'build/picture-p21-native/live-sd-r01'
    identities=[sha(private/name) for name in ('frame.png','frame.rgb565')]
    token=(private/'request.txt').read_text().split()[1]
    for path in OUT.rglob('*'):
        if path.is_file():
            content=path.read_text(encoding='utf-8')
            assert not any(value in content for value in identities)
            if len(token)>=9:assert token not in content
    names={p.relative_to(REPO).as_posix() for p in scripts}
    names.update(('AGENTS.md','README.md','docs/Validation.md','docs/PICTURE_NEW_CHECKPOINT_20261020.md',
        'docs/PICTURE_NEW_MODEL_CONTRACT.md','docs/TRAINING_AI_HANDOFF_20261020.md',
        'artifacts/vision-model-20261020-adapter/INTERFACE.md','artifacts/vision-model-20261020-adapter/working_combination.json'))
    names.update(host['inputs'])
    result=dict(status='R12_ENGINEERING_CHECKS_PASS_NATIVE_E_EXTERNAL_DEPENDENCY_PENDING',
        manifest_files_verified=counts,formal_payloads_archived=90,formal_archive_SHA_exact=True,
        default='E frozen640/v3c FP32',E_exact_INT8_available=False,E_deployed=False,
        rollback='640/v2-band explicit FP32 or r08 exact-int64',
        actual_E8_weight_bank_lines=64,zero_RTL_capacity_increase_possible=False,
        latency_waiver_granted=False,game2_images_read=0,game2_inference_runs=0,
        game2_training_tuning_failure_analysis=False,formal_truth_archival_authorized=True,
        frozen_R2_and_v1_and_contract_unchanged=True,exact_reference_unchanged=True,
        source_bindings_match=True,live_photo_identity_scan_pass=True,
        host_regression_passed=True,entrypoint_checks_passed=7,RV32_offline_build_passed=True,
        full_suite_passed=False,full_suite_blocker='Existing GCC16.2 --disable-lto; gate retained',
        RTL_IP_PDS_unchanged=True,SD_written=False,Flash_written=False,new_JTAG_program=False,
        push=False,tag=False,VERSION='2.1',new_BoardRelease=False,production_ready=False,M0_accepted=False,
        git_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),
        source_sha256={name:sha(REPO/name) for name in sorted(names)},
        evidence_sha256={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='closeout.json'},
        remaining=['matching v3c exact-int64 tensors/calibration/graph/reference/manifest',
            'game1/3 true grid corners for geometry diagnosis',
            '512 results and consistent bank64 budget',
            'E numeric acceptance, native build/deployment and clean end-to-end timing',
            'physical Space, RAM retry persistence, fallback and games/moved-board/P50/P95 acceptance',
            'restore LTO-capable toolchain and full regression'])
    write(OUT/'closeout.json',result)
    print('R12_FINAL_IDENTITY_SOURCE_ARCHIVE_PASS',counts,'NATIVE_E_INT8_PENDING')


if __name__=='__main__':main()
