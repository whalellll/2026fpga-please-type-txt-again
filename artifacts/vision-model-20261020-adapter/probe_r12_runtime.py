"""E FP32 A/B runtime controls on nine game-3 training frames, never game 2."""
import argparse
import collections
import copy
import hashlib
import json
import statistics
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--expected-classifier',default='v3d-QAT')
    args=parser.parse_args();out=args.out.resolve()
    assert out.is_relative_to(REPO/'build') and not out.exists() and not args.receipt.exists()
    out.mkdir(parents=True)
    inputs=json.loads((REPO/'build/picture-r11-20261022/adapter-inputs/game3-inputs.json').read_text())
    frames=inputs['frames'][::10];assert inputs['game']==3 and len(frames)==9
    assert all(152<=item['index']<=234 for item in frames)
    from r12_reference import resolve_selection,load_model
    from r09_reference import refinement_b
    selected=resolve_selection();assert selected['classifier']==args.expected_classifier and selected['detector_input']==640
    variants={}
    for name,use_filter,refinement in [('A_B',True,'B'),('no_A_B',False,'B'),('A_full',True,'full')]:
        settings=dict(selected,candidate_filter=use_filter,refinement=refinement)
        entry=dict(model=load_model(settings),batches=[])
        def hook(module,arguments,entry=entry):entry['batches'].append(int(arguments[0].shape[0]))
        entry['handle']=entry['model'].pipeline.detector.classifier.register_forward_pre_hook(hook)
        variants[name]=entry
    import pipeline as PL
    import line_refinement as LR
    parameters=copy.deepcopy(LR.PARAMETERS)
    functions=dict(B=refinement_b(),full=LR.refine_board)
    rows={name:[] for name in variants};names=list(variants)
    for index,item in enumerate(frames):
        source=REPO/item['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256']
        for name in names[index%3:]+names[:index%3]:
            entry=variants[name];entry['batches'].clear();refinements=[]
            function=functions['full' if name=='A_full' else 'B']
            def observe(rgb,coarse,*,rank_axis,occluder_boxes=None):
                start=time.perf_counter();result=function(rgb,coarse,rank_axis=rank_axis,occluder_boxes=occluder_boxes)
                refinements.append(dict(accepted=result['accepted'],reason=result.get('reason'),
                    crossings=result.get('detected_crossings'),ms=1000*(time.perf_counter()-start)))
                return result
            PL.refine_board=observe
            result=entry['model'].predict(source)
            assert parameters==LR.PARAMETERS and not result['production_ready'] and not result['automatic_action_allowed']
            strict=dict(status=result['status'],can_use=result['can_use_as_candidate'],fen=result.get('board_placement_fen'),issues=result.get('issues'))
            counts=getattr(entry['model'].pipeline.detector,'_r09_counts',None)
            rows[name].append(dict(private_input=item['path'],strict=strict,classifier_batch=sum(entry['batches']),
                counts=counts,timings_ms=result['timings_ms'],refinements=refinements))
        print('R12_E_RUNTIME_CONTROL',index+1,'/',len(frames),flush=True)
    equivalent=all(a['strict']==b['strict'] for a,b in zip(rows['A_B'],rows['no_A_B']))
    assert equivalent,'A changes the strict decision/FEN on the training controls'
    summary={}
    for name,values in rows.items():
        (out/(name+'-private.json')).write_text(json.dumps(values,indent=2)+'\n')
        refinements=[r for value in values for r in value['refinements']]
        summary[name]=dict(frames=len(values),classifier_batch_mean=statistics.mean(v['classifier_batch'] for v in values),
            status_counts=dict(collections.Counter(v['strict']['status'] for v in values)),
            refinement_accepts=sum(r['accepted'] for r in refinements),
            refinement_reasons=dict(collections.Counter(r['reason'] for r in refinements)),
            detected_crossings_min=min((r['crossings'] for r in refinements if r['crossings'] is not None),default=None),
            detected_crossings_max=max((r['crossings'] for r in refinements if r['crossings'] is not None),default=None),
            PC_total_ms_median=statistics.median(v['timings_ms']['total_frame'] for v in values),
            PC_grid_refinement_ms_median=statistics.median(r['ms'] for r in refinements))
        for entry in variants.values():entry['handle'].remove()
    result=dict(status='PASS',scope='E FP32 game-3-only runtime controls; descriptive PC timing, not RV32 or accuracy acceptance',
        variants=summary,strict_A_on_off_decisions_and_FEN_equal=equivalent,comparison_frames=len(frames),
        variant_order='rotated by frame',threshold_contract_unchanged=True,refinement_iterations=5,
        B_trials=80,shared_driver_and_numeric_graph_kernels_changed=False,
        game2_images_read=0,game2_inference_runs=0,hardware_used=False,production_ready=False,
        native_E_latency='r14 exact package available; CPU80 end-to-end measurement pending, no estimate from PC wall-time ratios')
    args.receipt.write_text(json.dumps(result,indent=2)+'\n')
    print('R12_E_RUNTIME_CONTROLS_PASS',json.dumps(summary),flush=True)


if __name__=='__main__':main()
