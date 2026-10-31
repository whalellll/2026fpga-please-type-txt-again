"""Game-3-only geometry replay. Private frame artifacts stay under build/."""
import argparse
import collections
import copy
import json
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--limit',type=int,default=83)
    p.add_argument('--require-accepted',action='store_true');p.add_argument('--controls',action='store_true')
    p.add_argument('--receipt',type=Path);a=p.parse_args()
    assert 1<=a.limit<=83
    out=a.out.resolve();assert out.is_relative_to(REPO/'build');out.mkdir(parents=True,exist_ok=False)
    inputs=json.loads((REPO/'build/picture-r11-20261022/adapter-inputs/game3-inputs.json').read_text())
    assert inputs['game']==3 and all(152<=f['index']<=234 for f in inputs['frames'])
    from r09_reference import load_working_model,refinement_b
    model=load_working_model('fp32')
    import numpy as np
    import pipeline as PL
    import line_refinement as LR
    full=LR.refine_board;b_fn=refinement_b();parameters=copy.deepcopy(LR.PARAMETERS)
    rows=[]
    for index,item in enumerate(inputs['frames'][:a.limit]):
        captured={}; private={}
        def observe(rgb,coarse,*,rank_axis,occluder_boxes=None):
            def measure(fn,axis=rank_axis,boxes=occluder_boxes):
                start=time.perf_counter();v=fn(rgb,coarse,rank_axis=axis,occluder_boxes=boxes)
                return dict(accepted=v['accepted'],reason=v.get('reason'),crossings=v.get('detected_crossings'),
                            inliers=v.get('inliers'),coverage=v.get('coverage'),motion=v.get('corner_motion_cells'),
                            ms=1000*(time.perf_counter()-start)),v
            captured['full'],f=measure(full);captured['B'],b=measure(b_fn)
            if a.controls and index%10==0:
                captured['no_occluders'],_=measure(full,boxes=None)
                captured['vertical_axis'],_=measure(full,axis='image_vertical')
                try:
                    LR.PARAMETERS['min_score']=.15
                    captured['score_015_diagnostic'],_=measure(full)
                finally:
                    LR.PARAMETERS.clear();LR.PARAMETERS.update(parameters)
            private.update(rgb=rgb,coarse=coarse,boxes=np.asarray(occluder_boxes))
            return b
        PL.refine_board=observe
        result=model.predict(REPO/item['path'])
        assert parameters==LR.PARAMETERS
        if index==0 and private:
            np.savez_compressed(out/'first-refinement-input.npz',**private)
        row=dict(private_input=item['path'],input_sha256=item['sha256'],status=result['status'],variants=captured,
                 classifier_batch=model.pipeline.detector._r09_counts,timings_ms=result['timings_ms'])
        rows.append(row)
        (out/'private-progress.json').write_text(json.dumps(rows,indent=2)+'\n')
        if (index+1)%10==0:print('R11_GAME3_REPLAY',index+1,'/',a.limit,flush=True)
    summary=dict(scope='game 3 training-domain geometry diagnosis, not acceptance',frames=len(rows),
                 statuses=dict(collections.Counter(r['status'] for r in rows)),game2_frames_read=0,
                 game2_annotations_read=0,game2_inference_runs=0,production_thresholds_changed=False,
                 production_ready=False,hardware_used=False,variants={})
    for name in sorted({n for r in rows for n in r['variants']}):
        values=[r['variants'][name] for r in rows if name in r['variants']]
        summary['variants'][name]=dict(samples=len(values),accepted=sum(v['accepted'] for v in values),
              reasons=dict(collections.Counter(v['reason'] for v in values)),
              crossings_min=min((v['crossings'] for v in values if v['crossings'] is not None),default=None),
              crossings_max=max((v['crossings'] for v in values if v['crossings'] is not None),default=None))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    if a.receipt:a.receipt.write_text(json.dumps(summary,indent=2)+'\n')
    print('R11_GEOMETRY_SUMMARY',json.dumps(summary),flush=True)
    if a.require_accepted and any(not r['variants'].get('B',{}).get('accepted',False) for r in rows):
        raise SystemExit('R11_REQUIRE_ACCEPTED_FAILED: actual production refinement rejected training frame')

if __name__=='__main__':main()
