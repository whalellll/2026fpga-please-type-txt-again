"""R1 T1 scoring, R2 image-only golden models. Writes only explicit evidence.

R1's reference quad is used for scoring only. Its ROI argument is discarded
by the R2 predictor: localization/refinement/orientation all run on the image.
Model construction follows golden/recognize.py; one immutable instance is
reused across frames, as the public Recognizer API permits.
"""
import argparse,collections,csv,hashlib,importlib.util,json,os,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
R2=HERE.parent/'vision-model-20261020'
GOLDEN=R2/'golden'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',choices=['fp32','quantized-mac'],required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--board-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--limit',type=int,default=135)
    p.add_argument('--label-policy',choices=['legacy-r1-81','user-original-game3-20261020'],default='legacy-r1-81')
    a=p.parse_args()
    if a.out.exists():p.error('choose a fresh output directory')
    if not 1<=a.limit<=135:p.error('limit must be 1..135')
    os.environ.update(PYTHONDONTWRITEBYTECODE='1',WANDB_MODE='disabled',YOLO_AUTOINSTALL='false',YOLOv5_AUTOINSTALL='false')
    sys.path[:0]=[str(HERE),str(GOLDEN/'software'),str(GOLDEN/'quantization')]
    import numpy as np
    protocol=load_module('r1_t1_protocol',HERE/'evaluation/r1_test_eval_t1.py')
    corrections=protocol.load_corrections(HERE/'dataset_corrections.json')
    truth=json.loads((HERE/'fen_gt.json').read_text(encoding='utf-8'))
    assert sum(len(v) for v in corrections.values())==81
    frames=list(range(908,908+a.limit));inputs={}
    for idx in frames:
        stem=f'IMG{idx:05d}'
        for tag,path in [('image',a.dataset/'in'/(stem+'.PNG')),('pieces',a.dataset/'out'/(stem+'.json')),('board',a.board_dir/(stem+'.json'))]:
            if not path.is_file():raise FileNotFoundError(path)
            inputs[stem+'/'+tag]={'path':str(path.resolve()),'sha256':sha(path)}
    a.out.mkdir(parents=True)
    policy_manifest=None
    if a.label_policy!='legacy-r1-81':
        from user_game3_truth import prepare
        corrections,truth,policy_manifest=prepare(protocol,a.dataset,a.board_dir,a.out/'truth-policy')
        baseline=json.loads((REPO/'docs/validation/picture-p20-combined-20261020'/a.backend/'inputs.json').read_text(encoding='utf-8'))['files']
        assert set(inputs)==set(baseline) if a.limit==135 else set(inputs)<=set(baseline)
        assert all(entry['sha256']==baseline[key]['sha256'] for key,entry in inputs.items()),'input changed since historical evaluation'
    write(a.out/'inputs.json',{'files':inputs,'corrections_sha256':sha(HERE/'dataset_corrections.json'),
                              'fen_truth_sha256':sha(HERE/'fen_gt.json'),'golden_entrypoint_sha256':sha(GOLDEN/'recognize.py'),
                              'protocol_sha256':sha(HERE/'evaluation/r1_test_eval_t1.py'),'backend':a.backend,
                              'reference_geometry_used_for_inference':False,'model_reuse':True,
                              'label_policy':a.label_policy,'truth_policy_manifest':policy_manifest,
                              'evaluator_sha256':sha(Path(__file__))})
    if a.backend=='fp32':
        from recognizer import Recognizer
        model=Recognizer(GOLDEN/'software',device='cpu',precision='fp32')
    else:
        from integer_ops import load_integer_runtime
        model=load_integer_runtime(GOLDEN/'software',GOLDEN/'quantization/candidate_v1')
    strict=[];status_counts=collections.Counter()

    class Predictor:
        def __init__(self):self.index=908
        def predict(self,image,reference_roi):
            # This is the R1 evaluator's detector seam. Never pass reference
            # corners, ROI, labels, corrections or tracking to the R2 model.
            del reference_roi
            stem=f'IMG{self.index:05d}';self.index+=1
            path=a.dataset/'in'/(stem+'.PNG')
            start=time.perf_counter();result=model.predict(path)
            elapsed=time.perf_counter()-start
            assert result['frame']['width']==image.shape[1] and result['frame']['height']==image.shape[0]
            result['delivery_backend']=a.backend;result['full_integer_pipeline']=False
            if a.backend=='quantized-mac':
                result['numeric_backend']=dict(CNN_MAC='S8xS8_INT32',preactivation='S16',activation='S8_LUT',host_non_MAC='FP32')
                for identity in result['models'].values():identity['precision']='W8A8_MAC_with_host_FP32_graph'
            write(a.out/'predictions'/(stem+'.json'),result)
            expected=truth[stem]['fen_board']
            candidate=result['candidate_placement_fen'];usable=result['board_placement_fen']
            strict.append(dict(frame=stem,status=result['status'],candidate_exact=candidate==expected,
                               usable_exact=usable==expected,can_use_as_candidate=result['can_use_as_candidate'],
                               candidate_fen=candidate,usable_fen=usable,gt_fen=expected,inference_ms=elapsed*1000))
            status_counts[result['status']]+=1
            if len(strict)==1 or len(strict)%10==0 or len(strict)==a.limit:
                print('P20_FRAME',a.backend,len(strict),'/',a.limit,stem,result['status'],round(elapsed,3),flush=True)
            return np.asarray([piece['bbox_original']+[piece['score'],piece['class_id']] for piece in result['pieces']],dtype=float).reshape(-1,6)

    rows,dets=protocol.evaluate(Predictor(),a.dataset/'in',a.dataset/'out',a.board_dir,corrections,limit=a.limit)
    per_class={}
    for cid,name in enumerate(protocol.CLASS_NAMES):
        d=dets[cid];tp=np.asarray(d['tp'],np.float32);conf=np.asarray(d['conf'],np.float64)
        ap=protocol.compute_ap_yolov5(tp,conf,d['n_gt']) if d['n_gt'] else None
        per_class[name]=dict(ap50=ap,n_gt=d['n_gt'],n_pred=len(tp),n_tp=int(tp.sum()))
    exact=sum(row['board_exact'] for row in rows);n=len(rows)
    weak={name:per_class[name]['ap50'] for name in protocol.WEAK_CLASSES}
    gate=n==135 and exact/n>=.85 and all(v is not None and v>=.5 for v in weak.values())
    strict_exact=sum(r['usable_exact'] for r in strict);candidate_exact=sum(r['candidate_exact'] for r in strict)
    report=dict(backend=a.backend,n_frames=n,requested_protocol=dict(conf=.05,iou=.5,nms_iou=.6,class_aware=True,
                geometry='R1 reference geometry for scoring; R2 automatic geometry for inference'),
                whole_board_exact=dict(correct=exact,total=n,rate=exact/n),per_class_ap50=per_class,weak_classes=weak,
                requested_numeric_gate_pass=bool(gate),
                end_to_end=dict(candidate_exact=candidate_exact,strict_usable_exact=strict_exact,total=n,
                    candidate_rate=candidate_exact/n,strict_usable_rate=strict_exact/n,status_counts=dict(status_counts)),
                independent_test=False,independence_reason='R2 training_manifest: reused game 3 failure-analysis set',
                corrections=sum(len(v) for v in corrections.values()),label_policy=a.label_policy,
                test_game_corrections=sum(len(corrections.get(f'IMG{i:05d}',[])) for i in frames),
                withdrawn_game3_corrections=77 if policy_manifest else 0,
                production_ready=False,full_integer_pipeline=False,m0_accepted=False,
                piece_fit_enabled=False,reference_geometry_used_for_inference=False)
    write(a.out/'metrics_summary.json',report);write(a.out/'per_frame.json',rows);write(a.out/'end_to_end_per_frame.json',strict)
    with (a.out/'per_image_metrics.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!='errors']);writer.writeheader()
        writer.writerows({k:v for k,v in row.items() if k!='errors'} for row in rows)
    print('P20_EVALUATION_COMPLETE',json.dumps(report,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':main()
