"""Select the standard-layout r14 QAT FP32 baseline, register later negative evidence."""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
B=REPO/'build/picture-merge-20261023';E=REPO/'docs/validation/picture-merge-20261023'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 current=load(HERE/'working_combination.json');out=B/'profiles';assert not out.exists();out.mkdir()
 write(out/'previous-working-combination.json',current)
 old=current['profiles']['working-r12'];source=REPO/old['root']
 for rnd,tag,cls,pattern in [(13,'rollback-v3d','v3d','candidate_r13_e_v3d'),(14,'working-r14','v3d-QAT','candidate_r14_e_v3dqat')]:
  intake=load(E/f'intake-r{rnd}.json');assert intake['status']=='PASS'
  candidate=next((B/f'r{rnd}').rglob(pattern));graph=load(candidate/'integer_graph.json')
  identities=graph['model_SHA256'];matches=[p for p in (B/f'r{rnd}').rglob('*.pt') if sha(p)==identities['classifier']];assert len(matches)==1
  assert all(identities[k]==old['models'][k]['sha256'] for k in ('board','detector'))
  if rnd==14:assert identities['classifier'].startswith('d1476f80') and matches[0].name=='best_standard.pt'
  root=out/tag/'software';shutil.copytree(source,root,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  shutil.copyfile(matches[0],root/'weights/classifier.pt');manifest=load(root/'manifest.json')
  for item in manifest['models'].values():item['sha256']=sha(root/item['path'])
  for name in manifest['files']:manifest['files'][name]=sha(root/name)
  manifest['candidate_lineage']='standard-layout r14 QAT baseline or explicit r13 rollback; no training performed';write(root/'manifest.json',manifest)
  profile=dict(old,root=root.relative_to(REPO).as_posix(),classifier=cls,models=manifest['models'],backends=['fp32','quantized-mac'],default_backend='fp32',quantized_candidate=candidate.relative_to(REPO).as_posix(),quantized_graph_sha256=sha(candidate/'integer_graph.json'),quantized_gate=False,integer_acceptance='pending fresh-game attribution')
  current['profiles'][tag]=profile
  write(HERE/f'candidates/{pattern}/registration.json',dict(schema_version=1,selected_for_work=rnd==14,classifier=cls,layout='standard',model_sha256=identities,local_release=profile['root'],local_quantized_candidate=profile['quantized_candidate'],quantized_graph_sha256=profile['quantized_graph_sha256'],quantized_payload_available=True,quantized_gate=False,integer_acceptance='待新局归因',production_ready=False,board_deployed=False,reported_game2_FP32_correct=75,reported_game2_INT_correct=68 if rnd==14 else 69,frames=84,reported_game2_FP32_candidate_board=84 if rnd==14 else 83,source='training-side reported aggregates only; no engineering game2 inference'))
 current.update(selected='candidate_r14_e_v3dqat',registration='candidates/candidate_r14_e_v3dqat/registration.json',default_profile='working-r14',default_backend='fp32',classifier='v3d-QAT',quantized_main_available=True,quantized_gate=False,integer_acceptance='待新局归因',latency_waiver_granted=True,demo_latency_cap_s=10,engineering_latency_cap_s=5,engineering_latency_goal_s=3,board_deployed=False,production_ready=False)
 write(HERE/'working_combination.json',current)
 for rnd,pattern,reason in [(15,'candidate_r15_e_v3dqat2','QAT2 negative; real INT dev37 loss 8.11pp; simulator fidelity mismatch'),(16,'candidate_r16_mixcal','mixed calibration negative; 33/37; do not select')]:
  directory=next((B/f'r{rnd}').rglob(pattern))
  write(HERE/f'candidates/{pattern}/registration.json',dict(selected_for_work=False,production_ready=False,negative_result=True,reason=reason,local_source=directory.relative_to(REPO).as_posix(),source_manifest_sha256=load(E/f'intake-r{rnd}.json')['manifest_sha256']))
 # Preserve original records; mark older selected classifiers as explicit rollback.
 for name in ('E-v1-640-v3c-r12','classifier-v3c-r11'):
  path=HERE/'candidates'/name/'registration.json';value=load(path);value.update(selected_for_work=False,superseded_by='candidate_r14_e_v3dqat');write(path,value)
 infrastructure=next((B/'r16').rglob('selection_set'));selection=load(infrastructure/'selection_manifest.json');assert selection['game2_contact']=='NONE'
 tools={p.name:dict(path=p.relative_to(REPO).as_posix(),sha256=sha(p)) for p in infrastructure.parent.glob('*.py')}
 tools['rescan_int.json']=dict(path=(infrastructure.parent/'rescan_int.json').relative_to(REPO).as_posix(),sha256=sha(infrastructure.parent/'rescan_int.json'))
 write(HERE/'training_infrastructure.json',dict(selection_manifest=selection,selection_root=infrastructure.relative_to(REPO).as_posix(),resources=tools,policy='games1/3 and old/synthetic only; verified originals read-only; no automatic training; no game2',classification='reusable training-side evaluation infrastructure'))
 matrix=load(B/'r17/matrix_full.json');aggregates={k:v for k,v in matrix.items() if not k.startswith('_')}
 assert all(v['fen_equal_vs_fp32']==v['frames']==28 and v['crop_class_agree']==1 for v in aggregates.values())
 write(E/'training-decisions.json',dict(status='R14_STANDARD_FP32_SELECTED_INT_FUNCTIONAL_ONLY',r14_standard_classifier_sha256=current['profiles']['working-r14']['models']['classifier']['sha256'],FP32_reported=dict(dev37_correct=37,game2_correct=75,game2_frames=84,game2_candidate_board=84,game2_conflicts=0),INT_reported=dict(dev37_correct=36,game2_correct=68,game2_frames=84,threshold_correct=73,gate_pass=False,status='待新局归因'),r15_negative='INT dev37 loss 8.11pp; game2 68/84; simulator fidelity mismatch',r16_negative='faithful simulator gradient failed; mixed calibration33/37',r16_classifier_crop_fact='nearly lossless on selection-set; not full-pipeline quality acceptance',r17_matrix=aggregates,r17_scope='reported FEN/crop-class agreement on28 selection frames; not a proof that every intermediate tensor is bit-identical',r17_inference='seven-frame discrepancy remains domain-conditional; await fresh-game attribution, not a proven causal localization',host_FP32_head_fallback_enabled=False,latency_waiver_granted=True,demo_cap_s=10,engineering_cap_s=5,engineering_goal_s=3,training_budget_busy_s=dict(mean=7.33,worst=7.66,scope='historical E8 bank64 static budget; not CPU80 latency'),game2_images_opened=0,game2_inference_runs=0,board_used=False,production_ready=False))
 # Authorized aggregate/interface statements; original reports and payloads stay in build.
 facts=next((B/'r15').glob('*零冲突.md'));shutil.copyfile(facts,E/'r15-interface-fact.md')
 budget=next((B/'r14').rglob('*LATENCY_DECISION.md'));shutil.copyfile(budget,E/'r14-budget-and-512-erratum.md')
 # Current archival closeout survives reconstruction of historical r14 inputs.
 from register_training_closeout import apply_metadata
 apply_metadata()
 print('R14_STANDARD_QAT_MAINLINE_SELECTED_R15_R16_NEGATIVES_R17_REGISTERED')
if __name__=='__main__':main()
