"""Verify frozen identities, source binding and redacted r11 closeout evidence."""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OUT=REPO/'docs/validation/picture-r11-offline-20261022'
BUILD=REPO/'build/picture-r11-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_manifest(root):
    manifest=load(root/'manifest.json')
    for name,entry in manifest['files'].items():
        expected=entry if isinstance(entry,str) else entry['sha256']
        assert sha(root/name)==expected,name
    return len(manifest['files'])


def main():
    frozen=HERE.parent/'vision-model-20261020'
    frozen_identity=load(REPO/'docs/validation/picture-r08-offline-20261021/frozen-identity.json')
    assert sha(frozen/'manifest.json')==frozen_identity['frozen_manifest_sha256']
    assert load(frozen/'manifest.json')['release_version']=='3.0.0-contract'
    counts={'frozen_R2':verify_manifest(frozen)}
    for release,date in [('r08','20261021'),('r09','20261021'),('r11','20261022')]:
        root=REPO/('build/picture-'+release+'-'+date+'/delivery')
        counts[release]=verify_manifest(root)
    assert counts==dict(frozen_R2=1789,r08=594,r09=876,r11=38),counts
    exact=next((REPO/'build/picture-r08-20261021/delivery').rglob('exact_mm_int64_reference.py'))
    assert sha(exact)==sha(HERE/exact.name)
    intake=load(OUT/'intake.json')
    assert intake['status']=='MANIFEST_PAYLOADS_PASS_COVERAGE_INCOMPLETE'
    assert not intake['full_manifest_coverage'] and not intake['unmanifested_appendix_read']
    assert not (BUILD/'delivery/acceptance_game2_v3c.json').exists()
    working=load(HERE/'working_combination.json')
    assert working['selected']=='det416-v2-band-r09' and not working['production_ready']
    for candidate in ('classifier-v3c-r11','det416mix-r11'):
        registration=load(HERE/'candidates'/candidate/'registration.json')
        assert not registration['selected_for_work'] and not registration['production_ready']
        assert not registration['quantized_payload_available']
    host=load(OUT/'capture-host.json')
    assert host['status']=='PASS' and not host['full_suite_passed']
    assert all(sha(REPO/name)==digest for name,digest in host['inputs'].items())
    capture=load(OUT/'capture-board.json')
    assert capture['status']=='RAM_CAPTURE_RECOVERY_AND_NATIVE_MODEL_INPUT_PASS'
    assert not capture['SD_written'] and not capture['physical_Space_accepted']
    assert all(sha(REPO/name)==digest for name,digest in capture['source_sha256'].items())
    for name in ('candidates-and-isolation.json','geometry-game3.json','budget-and-switch.json','entrypoints.json'):
        item=load(OUT/name)
        assert item['game2_frames_read']==item['game2_annotations_read']==item['game2_inference_runs']==0
    scripts=[p for p in HERE.glob('*.py') if 'r11' in p.name or p.name in ('recognize_working.py','verify_capture_recovery.py')]
    for path in scripts:ast.parse(path.read_text(encoding='utf-8'),filename=path.name)
    for path in OUT.glob('*.json'):
        # Actual photo IDs, tokens, FEN and live IPC payloads stay private.
        text=path.read_text(encoding='utf-8')
        assert not re.search(r'"(?:token|frame_id|fen|raw_crc32|png_crc32)"\s*:',text),path.name
        assert not re.search(r'IMG00\d{3}',text),path.name
    subprocess.run(['git','diff','--check'],cwd=REPO,check=True,capture_output=True)
    assert not subprocess.check_output(['git','status','--porcelain','--','rtl','ip','pds','VERSION'],cwd=REPO).strip()
    assert (REPO/'VERSION').read_text().strip()=='2.1'
    names={p.relative_to(REPO).as_posix() for p in scripts}
    names.update(capture['source_sha256'])
    names.update(('AGENTS.md','README.md','docs/Validation.md','docs/PICTURE_NEW_CHECKPOINT_20261020.md',
        'docs/TRAINING_AI_HANDOFF_20261020.md','docs/console调试命令.md',
        'docs/validation/picture-r11-offline-20261022/README.md',
        'artifacts/vision-model-20261020-adapter/INTERFACE.md'))
    result=dict(status='ENGINEERING_CHECKS_PASS_EXTERNAL_ACCEPTANCE_PENDING',manifest_files_verified=counts,
        r11_full_manifest_coverage=False,r11_training_reissue_required=True,
        frozen_R2_and_v1_and_3_0_contract_unchanged=True,exact_reference_unchanged=True,
        default_still_r09_v2_band=True,game2_images_annotations_inference_used=False,
        camera_host_and_RAM_native_input_passed=True,physical_Space_accepted=False,
        new_software_on_SD=False,new_software_persistent=False,Flash_written=False,
        full_regression_passed=False,full_regression_blocker='Existing GCC16.2 --disable-lto; gate retained',
        VERSION='2.1',new_BoardRelease=False,production_ready=False,
        git_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),
        source_sha256={n:sha(REPO/n) for n in sorted(names)},
        evidence_sha256={p.name:sha(p) for p in sorted(OUT.glob('*.json')) if p.name!='closeout.json'},
        remaining=['formal manifest coverage and user-reviewed independent game2 results',
            'true game1/3 grid corner labels for geometry diagnosis',
            'model quality/latency choice and corresponding INT8 delivery',
            'physical Space and SD persistence of camera recovery',
            'complete recognition, games, moved-board recovery, clean latency and full LTO suite'])
    (OUT/'closeout.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('R11_FINAL_IDENTITY_PRIVACY_SOURCE_CHECK_PASS',counts)


if __name__=='__main__':main()
