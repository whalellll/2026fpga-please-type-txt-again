"""Keep both r13 integer candidates and the closed det512 route explicit."""
import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[1];B=R/'build/picture-merge-20261023'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
c=load(H/'working_combination.json');source=next((B/'r13').rglob('candidate_r13_e_v3c'));graph=load(source/'integer_graph.json');p=c['profiles']['working-r12']
assert graph['model_SHA256']=={k:v['sha256'] for k,v in p['models'].items()}
p.update(backends=['fp32','quantized-mac'],quantized_candidate=source.relative_to(R).as_posix(),quantized_graph_sha256=hashlib.sha256((source/'integer_graph.json').read_bytes()).hexdigest(),quantization_origin='r13',quantized_gate=False,integer_acceptance='r13 v3c negative; historical rollback only')
write(H/'candidates/candidate_r13_e_v3c/registration.json',dict(selected_for_work=False,quantized_payload_available=True,model_sha256=graph['model_SHA256'],local_quantized_candidate=p['quantized_candidate'],reported_game2_INT_correct=64,frames=84,dev37_loss_pp=5.41,quantized_gate=False,production_ready=False))
write(H/'candidates/det512-r13-negative/registration.json',dict(selected_for_work=False,negative_result=True,reported_G_v3c=52,reported_H_v2band=62,frames=84,threshold=72,new_camera_domain_suitable=False,route='closed; retain training delivery and code for provenance only',source='r13 training-side aggregate; engineering game2 inference zero',production_ready=False))
write(H/'working_combination.json',c)
write(R/'docs/validation/picture-merge-20261023/r13-supplement.json',dict(status='REGISTERED',v3c_INT_aggregate=64,v3d_INT_aggregate=69,denominator=84,det512_G_H=[52,62],game2_images_opened=0,game2_inference_runs=0,default_unchanged='r14 standard QAT FP32'))
print('R13_BOTH_INTEGER_CANDIDATES_AND_DET512_NEGATIVE_REGISTERED')
