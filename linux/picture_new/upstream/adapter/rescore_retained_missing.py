"""Supplemental score of fresh predictions, retaining the non-withdrawn missing piece."""
import argparse
import collections
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
software=HERE.parent/'vision-model-20261020/golden/software'
sys.path[:0]=[str(HERE),str(software),str(software/'runtime'),str(software/'vendor')]
from evaluate_combined import load_module,sha,write
import numpy as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
a=p.parse_args();out=a.source/'retained-missing'
if out.exists():p.error('supplemental score exists')
base=json.loads((a.source/'metrics_summary.json').read_text())
assert base['n_frames']==135 and base['label_policy']=='user-original-game3-20261020'
inputs=json.loads((a.source/'inputs.json').read_text())
for entry in inputs['files'].values():assert sha(Path(entry['path']))==entry['sha256']
dataset=Path(inputs['files']['IMG00908/image']['path']).parent.parent
board=Path(inputs['files']['IMG00908/board']['path']).parent
protocol=load_module('supplemental_r1_protocol',HERE/'evaluation/r1_test_eval_t1.py')
corrections=protocol.load_corrections(a.source/'truth-policy/retained_corrections.json')
truth=json.loads((a.source/'truth-policy/fen_gt_retained_missing.json').read_text())
strict=[];prediction_hashes={};statuses=collections.Counter()
class Saved:
    index=908
    def predict(self,image,reference_roi):
        del reference_roi
        stem=f'IMG{self.index:05d}';self.index+=1
        path=a.source/'predictions'/(stem+'.json');prediction_hashes[stem]=sha(path)
        r=json.loads(path.read_text());expected=truth[stem]['fen_board']
        assert r['frame']['width']==image.shape[1] and r['frame']['height']==image.shape[0]
        statuses[r['status']]+=1
        strict.append(dict(frame=stem,status=r['status'],gt_fen=expected,
            candidate_exact=r['candidate_placement_fen']==expected,
            usable_exact=r['board_placement_fen']==expected))
        return np.asarray([p['bbox_original']+[p['score'],p['class_id']] for p in r['pieces']],dtype=float).reshape(-1,6)
rows,dets=protocol.evaluate(Saved(),dataset/'in',dataset/'out',board,corrections,limit=135)
classes={}
for cid,name in enumerate(protocol.CLASS_NAMES):
    d=dets[cid];tp=np.asarray(d['tp'],np.float32);conf=np.asarray(d['conf'],np.float64)
    classes[name]=dict(ap50=protocol.compute_ap_yolov5(tp,conf,d['n_gt']) if d['n_gt'] else None,
                      n_gt=d['n_gt'],n_pred=len(tp),n_tp=int(tp.sum()))
correct=sum(r['board_exact'] for r in rows);weak={name:classes[name]['ap50'] for name in protocol.WEAK_CLASSES}
summary=dict(backend=base['backend'],label_policy='withdraw-77-class-corrections-retain-IMG00920-missing-piece',
    inference='Rescoring the same freshly regenerated 135 prediction files; no additional model execution',
    n_frames=135,whole_board_exact=dict(correct=correct,total=135,rate=correct/135),
    per_class_ap50=classes,weak_classes=weak,
    requested_numeric_gate_pass=correct/135>=.85 and all(v is not None and v>=.5 for v in weak.values()),
    end_to_end=dict(candidate_exact=sum(r['candidate_exact'] for r in strict),
        strict_usable_exact=sum(r['usable_exact'] for r in strict),total=135,status_counts=dict(statuses)),
    test_game_corrections=1,withdrawn_game3_corrections=77,independent_test=False,
    production_ready=False,m0_accepted=False,full_integer_pipeline=False)
write(out/'metrics_summary.json',summary);write(out/'per_frame.json',rows)
write(out/'end_to_end_per_frame.json',strict)
write(out/'source_identity.json',dict(predictions_sha256=prediction_hashes,
    source_inputs_sha256=sha(a.source/'inputs.json'),truth_sha256=sha(a.source/'truth-policy/fen_gt_retained_missing.json')))
print('RETAINED_MISSING_SCORE',json.dumps(summary['whole_board_exact']),json.dumps(summary['end_to_end']))
