import argparse,hashlib,json,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise FileExistsError(a.out)
root=REPO/'docs/validation/picture-p20-combined-20261020'
files={'TRAINING_AI_HANDOFF_20261020.md':REPO/'docs/TRAINING_AI_HANDOFF_20261020.md'}
for name in ('M0.json','classification-correction-mismatches.json','classification-correction-mismatches.csv','pip-freeze.txt','original-requirements-conflict.txt'):
    files['evidence/historical/'+name]=root/name
for backend in ('fp32','quantized-mac'):
    for name in ('metrics_summary.json','per_frame.json','end_to_end_per_frame.json','inputs.json'):
        files['evidence/historical/'+backend+'/'+name]=root/backend/name
current=REPO/'docs/validation/picture-p20-original-labels-20261020-r03'
for path in current.rglob('*.json'):
    files['evidence/current/'+path.relative_to(current).as_posix()]=path
files['evidence/current/README.md']=current/'README.md'
for name in ('user_game3_truth.py','run_user_game3_evaluation.py','rescore_retained_missing.py'):
    files['adapter/'+name]=HERE/name
for path in (HERE/'label-policy-user-original-game3-20261020').rglob('*.json'):
    files['adapter/'+path.relative_to(HERE).as_posix()]=path
probe=REPO/'docs/validation/picture-p21-runtime-20261020/cpu-mm-probe.json'
files['evidence/cpu-mm-probe.json']=probe
for name in ('probe_cpu_mm.py','diagnose_first_layer.py','evaluate_combined.py',
             'run_live_references.py','diagnose_live_int32.py'):
    files['adapter/'+name]=HERE/name
for name in ('adapter_manifest.json','dataset_corrections.json','fen_gt.json','evaluation/r1_test_eval_t1.py'):
    files['adapter/'+name]=HERE/name
for directory in ('evaluation','geometry','geometry_fallback'):
    for path in (HERE/directory).rglob('*.py'):
        files['adapter/'+path.relative_to(HERE).as_posix()]=path
for name in ('assemble.py','prepare_runtime_requirements.py','requirements-pc-reference.txt'):
    files['adapter/'+name]=HERE/name
files['evidence/dense-plan-bank64.json']=root/'dense-plan-bank64.json'
for name in ('device-golden-binding.json','golden-device-r04.json','native-device-replay.json'):
    files['evidence/native/'+name]=REPO/'docs/validation/picture-p21-runtime-20261020'/name
for path in (REPO/'docs/validation/picture-p21-runtime-20261020/piece-fit-device-r01').iterdir():
    if path.is_file():files['evidence/native/piece-fit-device-r01/'+path.name]=path
for name in ('result.json','engineering-redacted.log','README.md'):
    files['evidence/native/live-native-sd-r01/'+name]=REPO/'docs/validation/picture-p21-runtime-20261020/live-native-sd-r01'/name
for name in ('boot-r03/result.json','human-display-confirmation-20261020.json'):
    files['evidence/native/sd-deployment/'+name]=REPO/'docs/validation/picture-native-sd-20261020'/name
files['adapter/archive_live_native.py']=HERE/'archive_live_native.py'
for name in ('build_piece_fit_probe.sh','prepare_piece_fit_resume.py','archive_piece_fit_probe.py','runtime/xq_piece_fit_probe.c'):
    files['adapter/'+name]=HERE/name
for name in ('INTERFACE.md','result_contract.py','runtime/automatic_orientation.py'):
    files['training-interface/'+name]=REPO/'artifacts/vision-model-20261020/golden/software'/name
manifest={name:dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for name,path in files.items()}
with zipfile.ZipFile(a.out,'x',compression=zipfile.ZIP_DEFLATED) as z:
    for name,path in files.items():z.writestr(name,path.read_bytes())
    z.writestr('SHA256_MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
with zipfile.ZipFile(a.out) as z:
    assert set(z.namelist())==set(manifest)|{'SHA256_MANIFEST.json'}
    for name,entry in manifest.items():
        content=z.read(name)
        assert len(content)==entry['bytes'] and hashlib.sha256(content).hexdigest()==entry['sha256']
print('TRAINING_HANDOFF_ZIP_PASS',str(a.out),a.out.stat().st_size,hashlib.sha256(a.out.read_bytes()).hexdigest())
