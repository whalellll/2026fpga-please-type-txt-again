"""Select the user-chosen E FP32 baseline; retain explicit historical fallbacks."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to(REPO/'build') or out.exists():raise ValueError('fresh build/ directory required')
    official=load(args.evidence/'policy-and-official-summary.json')
    assert official['selected']=='E_v1_640_v3c' and not official['latency_waiver_granted']
    previous=load(HERE/'working_combination.json');out.mkdir(parents=True)
    write(out/'previous-working-combination.json',previous)
    v3_path=HERE/'candidates/classifier-v3c-r11/registration.json';v3=load(v3_path)
    v2_path=HERE/'candidates/v2-band-r08/registration.json';v2=load(v2_path)
    v2_weight=REPO/v2['local_checkpoint'];assert sha(v2_weight)==v2['checkpoint_sha256']
    profiles={}
    for name,detector,classifier in [('working-r12','frozen640','v3c'),('rollback-v2-band','frozen640','v2-band'),('legacy-416mix-v2-band','det416mix-r11','v2-band')]:
        source=REPO/v3['fp32_profiles'][detector]['root'];root=out/name/'software'
        shutil.copytree(source,root,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        if classifier=='v2-band':shutil.copyfile(v2_weight,root/'weights/classifier.pt')
        manifest=load(root/'manifest.json')
        for key,item in manifest['models'].items():item['sha256']=sha(root/item['path'])
        for path in manifest['files']:manifest['files'][path]=sha(root/path)
        manifest['candidate_lineage']='r12 E working FP32 baseline or explicit rollback; no v3c INT8 payload'
        write(root/'manifest.json',manifest)
        profiles[name]=dict(detector=detector,classifier=classifier,detector_input=640 if detector=='frozen640' else 416,
            root=root.relative_to(REPO).as_posix(),models=manifest['models'],backends=['fp32'],default_backend='fp32',
            candidate_filter=True,refinement='B',domain_suitable=detector=='frozen640')
    rollback=profiles['rollback-v2-band']
    graph_path=REPO/v2['local_quantized_candidate']/'integer_graph.json'
    graph=load(graph_path)
    assert graph['model_SHA256']=={k:v['sha256'] for k,v in rollback['models'].items()}
    rollback.update(backends=['fp32','quantized-mac'],quantized_candidate=v2['local_quantized_candidate'],
        quantized_graph_sha256=sha(graph_path))
    r09=load(HERE/'candidates/det416-r09/registration.json')
    profiles['working-r09']=dict(detector='det416-r09',classifier='v2-band',detector_input=416,
        root=r09['local_release'],quantized_candidate=r09['local_quantized_candidate'],
        models=load(REPO/r09['local_release']/'manifest.json')['models'],backends=['quantized-mac','fp32'],
        default_backend='quantized-mac',candidate_filter=True,refinement='B',domain_suitable=False)
    for detector in ('det416-r09','det416mix-r11'):
        base=v3['fp32_profiles'][detector]
        profiles['legacy-'+detector+'-v3c']=dict(detector=detector,classifier='v3c',detector_input=416,
            root=base['root'],models=base['models'],backends=['fp32'],default_backend='fp32',
            candidate_filter=True,refinement='B',domain_suitable=False)
    frozen='artifacts/vision-model-20261020/golden/software'
    profiles['frozen640-v1']=dict(detector='frozen640',classifier='v1',detector_input=640,root=frozen,
        quantized_candidate='artifacts/vision-model-20261020/golden/quantization/candidate_v1',
        models=load(REPO/frozen/'manifest.json')['models'],backends=['quantized-mac','fp32'],
        default_backend='quantized-mac',candidate_filter=False,refinement='full',domain_suitable=True)
    selected=profiles['working-r12']
    composite=dict(schema_version=1,candidate='E-v1-640-v3c-r12',selected_for_work=True,
        acceptance_status='正式FP32数字门通过；量化、时延和整体M0未验收',
        model_sha256={k:v['sha256'] for k,v in selected['models'].items()},
        local_release=selected['root'],detector_input=640,candidate_filter=True,refinement='B_trials80_bbox',
        official_source='docs/validation/picture-r12-engineering-20261022/official_acceptance_game2.json',
        formal_FP32=dict(frames=84,fen_exact=73,strict_usable=73,candidate_board=83,cell_conflict=1),
        quantized_payload_available=False,latency_waiver_granted=False,production_ready=False,full_integer_pipeline=False)
    write(HERE/'candidates/E-v1-640-v3c-r12/registration.json',composite)
    write(HERE/'working_combination.json',dict(schema_version=2,selected=composite['candidate'],default_profile='working-r12',
        registration='candidates/E-v1-640-v3c-r12/registration.json',default_backend='fp32',detector_input=640,
        classifier='v3c',candidate_filter=True,refinement='B_trials80_bbox',quantized_main_available=False,
        integer_reference_when_available='exact-int64 after platform probe; never _int_mm',
        profiles=profiles,production_ready=False,board_deployed=False,latency_waiver_granted=False))
    v3.update(selected_for_work=True,selected_by_combination=composite['candidate'],default_classifier='v3c',
        formal_game2_results='r12 truth_v2 official FP32; combination-specific',
        acceptance_status='E组合正式FP32数字门通过；待量化/时延/整体验收')
    write(v3_path,v3)
    v2.update(runtime_role='explicit rollback',superseded_by_classifier='v3c under E combination; frozen weights unchanged')
    write(v2_path,v2)
    r09.update(selected_for_work=False,acceptance_status='r12正式新相机域未达标；保留历史代码路径',
        new_camera_domain_suitable=False,superseded_by=composite['candidate'])
    write(HERE/'candidates/det416-r09/registration.json',r09)
    mix_path=HERE/'candidates/det416mix-r11/registration.json';mix=load(mix_path)
    mix.update(acceptance_status='r12正式新相机域未达标',new_camera_domain_suitable=False,
        quality_latency_decision='E selected; 512 training-side experiment parallel, no latency waiver')
    write(mix_path,mix)
    write(args.evidence/'mainline-selection.json',dict(status='E_FP32_MAIN_SELECTED',current=composite,
        explicit_rollback='frozen640/v2-band FP32 or r08 exact-int64 quantized reference',legacy_det416_paths_preserved=True,
        frozen_weights_modified=False,game2_images_read=0,game2_inference_runs=0,hardware_used=False))
    print('R12_E_MAINLINE_REGISTERED default=FP32 no_INT8_substitution=true')


if __name__=='__main__':main()
