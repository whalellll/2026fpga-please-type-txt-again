"""Game-3-only workload estimates. Never substitutes PC timing for RV32 latency."""
import argparse
import json
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def host_budget_context():
    r09=json.loads((REPO/'docs/validation/picture-r09-offline-20261021/budget-scope.json').read_text())
    r08=json.loads((REPO/'docs/validation/picture-r08-offline-20261021/latency-offline.json').read_text())
    return dict(refinement_B=dict(trials=80,iterations=5,bbox_integrals=True,
                  pc_45_vector_median_ms=r09['refinement_45_pc_median_ms'],
                  RV32_latest_s=None),
                r07_historical_device_stage_ms=r08['r07_device_reference_ms'],
                r07_scope='historical frozen640/v1 device replay; not current r11 timing',
                implemented_host_changes=['A before crop/resize and classifier tensors',
                    'B80 bbox integral maps, unchanged thresholds/five iterations',
                    'single held-bank copy fills snapshot and ordinary RAM together'],
                graph_driver_numeric_kernels_changed=False,
                current_RV32_host_overheads_measured=False,
                PC_to_RV32_speedup_extrapolation_used=False,
                reason='r11 delivers no INT8 payload; current RV32 prep/graph/driver components are unmeasured; adding PC milliseconds would fabricate an end-to-end estimate')

def main():
    import numpy as np
    from r11_reference import load_reference
    base=REPO/'build/picture-r11-20261022'
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();assert out.is_relative_to(REPO/'build');out.mkdir(exist_ok=False)
    inputs=json.loads((base/'adapter-inputs/game3-inputs.json').read_text())['frames']
    frames=inputs[::10];assert len(frames)==9 and all(152<=f['index']<=234 for f in frames)
    reports={};identities={}
    for detector in ('frozen640','det416mix-r11','det416-r09'):
        model=load_reference('fp32','v3c',detector)
        assert model.pipeline.detector.input_size==(640 if detector=='frozen640' else 416)
        import pipeline as PL
        # Budget workload only. Do not turn predictions into acceptance
        # scores, use truth labels, or run on the held-out second game.
        def budget_only(rgb,coarse,*,rank_axis,occluder_boxes=None):
            return dict(accepted=False,corners=np.asarray(coarse).tolist(),reason='budget_only_not_accuracy')
        PL.refine_board=budget_only
        rows=[]
        for item in frames:
            result=model.predict(REPO/item['path'])
            assert not result['automatic_action_allowed'] and not result['production_ready']
            rows.append(dict(batch=model.pipeline.detector._r09_counts,timings=result['timings_ms']))
        mean_batch=statistics.mean(r['batch']['classifier_batch'] for r in rows)
        side=model.pipeline.detector.input_size
        cycles=int(327732335*(side/640)**2)+13133090+201600000*mean_batch/211
        reports[detector]=dict(training_frames=9,game2_frames=0,input_side=side,
             classifier_before_mean=statistics.mean(r['batch']['before'] for r in rows),classifier_after_A_mean=mean_batch,
             conditional_W8A8_model_busy_s=cycles/49500000,conditional_jobs=round(34950*(side/640)**2)+1508+round(28499*mean_batch/211),
             fixed_r09_budget_busy_s=7.733 if side==640 else 3.91,
             host_RV32_prep_s=None,host_non_MAC_graph_s=None,driver_scheduling_s=None,camera_capture_s=None,
             end_to_end_s=None,end_to_end_5s_passed=False,
             remaining_host_budget_for_5s_s=5-cycles/49500000,
             pc_FP32_frame_ms_median=statistics.median(r['timings']['total_frame'] for r in rows),
             scope='FP32 workload sample; conditional int8 cost assuming delivered baseline plan; not board latency')
        identities[detector]={k:v['sha256'] for k,v in result['models'].items()}
        (out/(detector+'.json')).write_text(json.dumps(rows,indent=2)+'\n')
        print('R11_BUDGET_PROFILE_DONE',detector,flush=True)
    # Verify selector contracts without evaluating game 2.
    try:load_reference('quantized-mac','v3c')
    except ValueError as e:assert 'INT8' in str(e)
    else:raise AssertionError('r11 silently substituted a quantized candidate')
    report=dict(status='CONDITIONAL_BUDGET_NOT_BOARD_TIMING',profiles=reports,model_identities=identities,
          game2_frames_read=0,game2_annotations_read=0,game2_inference_runs=0,
          r11_INT8_payload_available=False,default_classifier='v2-band',quantized_v3c_fails_closed=True,
          model_cost_frequency_hz=49500000,host_CPU_contract_hz=59400000,
          equations='end_to_end = trigger_to_verified_frame + model_busy + host_prep + non_MAC_graph + refinement + driver + IPC/GUI',
          capture_retries='user-requested unlimited until fresh success or cancellation; no finite worst-case trigger-to-result bound',
          quality_decision='pending user game2 review and formal training reissue; no model promotion',
          host_budget_context=host_budget_context(),hardware_used=False,production_ready=False)
    (REPO/'docs/validation/picture-r11-offline-20261022/budget-and-switch.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R11_BUDGET_AND_SELECTOR_PASS',flush=True)

if __name__=='__main__':main()
