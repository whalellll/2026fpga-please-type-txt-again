"""Register FP32 r11 candidates; prepare game 3 only, leaving game 2 sealed."""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
import zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--delivery',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--camera-zip',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();delivery=a.delivery.resolve()
    assert out.is_relative_to(REPO/'build') and not out.exists()
    manifest=json.loads((delivery/'manifest.json').read_text(encoding='utf-8'))
    for name,item in manifest['files'].items():
        assert sha(delivery/name)==item['sha256']
    v3=delivery/'classifier_v3/v3c_run/best.pt';mix=delivery/'det416mix/det416mix_run/weights/best.pt'
    result=json.loads((delivery/'classifier_v3/v3c_run/result.json').read_text())
    assert result['best_sha256']==sha(v3) and result['best_epoch']==20
    assert sha(mix).startswith('8230164d')
    out.mkdir(parents=True)
    from r09_reference import selected_paths
    base,_=selected_paths()
    frozen=HERE.parent/'vision-model-20261020/golden/software'
    profiles={}
    for detector in ('det416-r09','det416mix-r11','frozen640'):
        root=out/'profiles'/detector/'software'
        shutil.copytree(base,root,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copyfile(v3,root/'weights/classifier.pt')
        side=640 if detector=='frozen640' else 416
        if detector=='det416mix-r11':shutil.copyfile(mix,root/'weights/detector.pt')
        if detector=='frozen640':
            shutil.copyfile(frozen/'weights/detector.pt',root/'weights/detector.pt')
            runtime=root/'runtime/live_two_stage.py'
            runtime.write_text(runtime.read_text().replace('input_size=416','input_size=640'),encoding='utf-8',newline='\n')
        sm=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        for key in ('classifier','detector'):sm['models'][key]['sha256']=sha(root/sm['models'][key]['path'])
        for name in sm['files']:sm['files'][name]=sha(root/name)
        sm['candidate_lineage']='r11 adapter FP32 candidate; not an accepted release or quantized native payload'
        write(root/'manifest.json',sm)
        profiles[detector]=dict(root=root.relative_to(REPO).as_posix(),detector_input=side,models=sm['models'])
    # Do not extract or read any PNG/metadata from the locked second game.
    frames=[]
    with zipfile.ZipFile(a.camera_zip) as z:
        names=set(z.namelist())
        for index in range(152,235):
            stem=f'IMG{index:05d}';png='CAMERA_new/'+stem+'.PNG';meta='CAMERA_new/'+stem+'.JSON'
            assert png in names and meta in names
            raw=z.read(png);md=json.loads(z.read(meta))
            assert f'{zlib.crc32(raw):08x}'==md['png_crc32']
            dest=out/'game3'/Path(png).name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(raw)
            # Private identifiers/metadata remain in build/ only.
            frames.append(dict(index=index,path=dest.relative_to(REPO).as_posix(),sha256=hashlib.sha256(raw).hexdigest()))
    write(out/'game3-inputs.json',dict(game=3,frames=frames,game2_frames_read=0))
    write(HERE/'candidates/classifier-v3c-r11/registration.json',dict(schema_version=1,candidate='classifier-v3c-r11',
          acceptance_status='待正式验收',selected_for_work=False,default_classifier='v2-band',best_epoch=20,
          model_sha256=sha(v3),training_reported_deploy_recall=.9904777694522676,training_gate_passed=True,
          formal_game2_results='pending human review and training reissue',quantized_payload_available=False,
          production_ready=False,fp32_profiles=profiles))
    write(HERE/'candidates/det416mix-r11/registration.json',dict(schema_version=1,candidate='det416mix-r11',
          acceptance_status='待正式验收',selected_for_work=False,model_sha256=sha(mix),input_side=416,
          quantized_payload_available=False,production_ready=False,quality_latency_decision='pending formal acceptance; no automatic promotion'))
    write(a.receipt,dict(status='PASS_VERIFIED_CANDIDATE_PREPARATION',candidate_manifest_files_verified=len(manifest['files']),
          candidate_weights_verified=True,game3_frames_prepared=len(frames),game2_frames_read=0,
          game2_annotations_read=0,game2_inference_runs=0,default_classifier='v2-band',main_combination_unchanged=True,
          quantized_r11_payload_available=False,production_ready=False,hardware_used=False))
    print('R11_CANDIDATES_AND_GAME3_ONLY_READY',len(frames))

if __name__=='__main__':main()
