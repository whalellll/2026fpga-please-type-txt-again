"""Bounded offline closeout; verify receipts, assets and current-source identity."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[2]
B = R/'build/picture-merge-20261023'
E = R/'docs/validation/picture-merge-20261023'
HERE = Path(__file__).resolve().parent


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024), b''):
            h.update(part)
    return h.hexdigest()


def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def git(*args):
    return subprocess.check_output(['git',*args],cwd=R)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full-receipt',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    a = p.parse_args()
    assert not a.receipt.exists()
    deliveries = {}
    for rnd in range(13,18):
        root = B/f'r{rnd}'
        receipt = load(E/f'intake-r{rnd}.json')
        manifest = root/'manifest.json'
        assert sha(manifest) == receipt['manifest_sha256']
        m = load(manifest)
        assert len(m['files']) == receipt['payloads']
        assert {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} == set(m['files'])|{'manifest.json'}
        for name,item in m['files'].items():
            src = root/name
            assert src.resolve().is_relative_to(root.resolve())
            assert src.stat().st_size == item['bytes'] and sha(src) == item['sha256'], (rnd,name)
        deliveries[str(rnd)] = dict(payloads=len(m['files']), all_payloads_unchanged=True,
                                    manifest_sha256=sha(manifest))
    full = load(a.full_receipt)
    assert full['status']=='PASS' and full['full_suite_passed'] and full['source_stable']
    assert not full['hardware_used']
    log = Path(full['log_location'])
    assert sha(log) == full['log_sha256'] and 'SOC_ALL_TESTS_PASS' in log.read_text(errors='replace')
    assert all(sha(R/n)==h for n,h in full['inputs'].items())
    bound = {}
    for name,key in [('numerics-final-r2.json','sources'),('host-regression-r7-final.json','inputs'),
                     ('pinned-models.json','source_sha256'),('target-builds.json','native_source_inputs')]:
        r = load(E/name)
        assert r['status']=='PASS'
        assert all(sha(R/n)==h for n,h in r[key].items()),name
        bound[name]=dict(sha256=sha(E/name), source_bindings_current=True)
    current = load(HERE/'working_combination.json')
    assert current['default_profile']=='working-r14' and current['default_backend']=='fp32'
    assert current['quantized_gate'] is False and current['production_ready'] is False
    assert current['demo_latency_cap_s']==10 and current['latency_waiver_granted']
    profiles = {}
    for name,profile in current['profiles'].items():
        missing=[]
        for model,item in profile['models'].items():
            src=R/profile['root']/item['path']
            if not src.is_file():
                missing.append(model)
            else:
                assert sha(src)==item['sha256'],(name,model)
        if name in ('working-r14','rollback-v3d','working-r12','rollback-v2-band'):
            assert not missing,(name,missing)
        if 'quantized_graph_sha256' in profile:
            assert sha(R/profile['quantized_candidate']/'integer_graph.json')==profile['quantized_graph_sha256']
        profiles[name]=dict(model_hashes_passed=not missing,missing_models=missing)
    frozen = R/'artifacts/vision-model-20261020'
    manifest = load(frozen/'manifest.json')
    missing=[];present=0
    for name,item in manifest['files'].items():
        src=frozen/name
        if not src.is_file():
            missing.append(name)
        else:
            expected=item if isinstance(item,str) else item['sha256']
            assert sha(src)==expected, 'frozen input changed: '+name
            present+=1
    restoration = {}
    if not missing:
        restored = load(E/'frozen-r2-restoration.json')
        rollback = load(E/'frozen-v1-rollback.json')
        vectors = load(E/'frozen-v1-exact-vectors.json')
        assert restored['status']=='PASS' and restored['complete_manifest_and_coverage_verified']
        assert restored['manifest_sha256']==sha(frozen/'manifest.json')
        assert restored['manifest_payloads']==present and restored['missing_payloads_after']==0
        assert rollback['status']=='PASS' and not rollback['hardware_used']
        assert rollback['working_combination_sha256']==sha(HERE/'working_combination.json')
        assert rollback['original_classifier_sha256']==current['profiles']['frozen640-v1']['models']['classifier']['sha256']
        assert vectors['status']=='PASS' and vectors['real_layer_vectors']==316
        assert vectors['delivered_numpy_and_torch_references_checked'] and not vectors['hardware_used']
        restoration={name:sha(E/name) for name in ('frozen-r2-restoration.json','frozen-v1-rollback.json',
                                                 'frozen-v1-exact-vectors.json')}
    assert not git('diff','origin/main','--name-only','--','rtl','ip','pds','config','sw/bootloader').strip()
    assert not git('diff','HEAD','--name-only','--','artifacts/vision-model-20261020','board_detect_v2_round1').strip()
    assert (R/'VERSION').read_text().strip()=='2.1'
    pending=set(git('diff','HEAD','--name-only','-z').decode().split('\0'))
    pending |= set(git('ls-files','--others','--exclude-standard','-z').decode().split('\0'))
    forbidden={'.png','.jpg','.jpeg','.bmp','.rgb565','.pt','.pth','.onnx','.npz','.npy','.sbit','.bin','.zip'}
    assert not [n for n in pending if Path(n).suffix.lower() in forbidden]
    for name in ('rootfs-contents.json','PN02-descriptors.json','offline-package.json','entrypoints-and-replay.json'):
        assert load(E/name)['status']=='PASS'
    package=load(E/'offline-package.json')
    assert not package['board_validated'] and not package['media_written']
    assert sha(Path(package['archive']['path']))==package['archive']['sha256']
    report=dict(status='OFFLINE_CLOSEOUT_PASS',full_regression_receipt=a.full_receipt.name,
                full_suite_passed=True,source_bindings=bound,deliveries=deliveries,profiles=profiles,
                frozen_R2=dict(present_payloads_sha_verified=present,missing_payloads=len(missing),
                               complete_verification=not missing,existing_present_bytes_unchanged=True),
                restoration_receipts_sha256=restoration,
                current_primary_pipeline_offline_complete=True,
                all_historical_assets_complete=not missing,
                all_offline_tasks_complete=not missing,
                offline_input_blocker='restore original frozen R2 ZIP7b41a943' if missing else None,
                main_hardware_exact=True,VERSION='2.1',default='working-r14 FP32',
                integer_acceptance='待新局归因',quantized_gate=False,production_ready=False,
                board_used=False,UART_JTAG_SD_Flash_used=False,game2_images_opened=0,
                game2_inference_runs=0,training_executed=False,push_or_tag=False,
                offline_package_sha256=package['archive']['sha256'],
                remaining=['CPU80 Picture hardware acceptance and measured latency',
                           'fresh-game attribution and independent grid-corner truth',
                           'upstream exact conv ABI/shape extension',
                           *(['restore absent original frozen payloads for full historical replay'] if missing else [])])
    a.receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('OFFLINE_CLOSEOUT_PASS full_suite=true hardware=false')


if __name__=='__main__':
    main()
