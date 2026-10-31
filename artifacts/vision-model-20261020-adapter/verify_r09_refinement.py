"""45 training-frame vectors: Python full/B and native full/B, unchanged guards."""
import argparse
import copy
import ctypes as C
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'software/runtime'),str(G/'software/vendor'),str(G/'quantization')]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--models',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True);p.add_argument('--reuse-build',type=Path);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    from verify_r08_host import build,sha
    if a.reuse_build:
        before=json.loads((a.reuse_build/'sources-before.json').read_text())
        audit=[REPO/name for name in before]
        assert before=={p.relative_to(REPO).as_posix():sha(p) for p in audit}
        for name in ('geometry.so','before','after','sources-before.json'):shutil.copyfile(a.reuse_build/name,out/name)
    else:
        audit,before=build(out,a.models.resolve())
    import numpy as np
    import pipeline as PL
    import line_refinement as LR
    from recognizer import Recognizer
    from r09_reference import refinement_b
    model=Recognizer(G/'software',device='cpu',precision='fp32')
    original=PL.refine_board;b_refine=refinement_b();parameters=copy.deepcopy(LR.PARAMETERS)
    class Box(C.Structure):
        _fields_=[(n,C.c_float) for n in ('x0','y0','x1','y1','score')]+[('class_id',C.c_uint)]
    class Stats(C.Structure):
        _fields_=[('crossings',C.c_uint),('inliers',C.c_uint),('median',C.c_double),('p95',C.c_double)]
    lib=C.CDLL(str(out/'geometry.so'));ptr=C.c_void_p
    lib.xnp_load_rng.argtypes=[C.c_char_p,ptr]
    for name in ('xnp_refine','xnp_refine_full'):
        getattr(lib,name).argtypes=[ptr,ptr,ptr,C.c_uint,ptr,ptr,C.POINTER(Stats)]
        getattr(lib,name).restype=C.c_int
    rng=np.empty((91,240,4),np.uint8)
    assert lib.xnp_load_rng(str(a.models.resolve()/'refinement_rng.bin').encode(),rng.ctypes.data)==1
    identities=json.loads((REPO/'docs/validation/picture-p20-combined-20261020/fp32/inputs.json').read_text())['files']
    rows=[]
    for frame in range(908,953):
        stem=f'IMG{frame:05d}';image=Path(identities[stem+'/image']['path'])
        assert sha(image)==identities[stem+'/image']['sha256']
        captured={}
        def observe(rgb,coarse,*,rank_axis,occluder_boxes=None):
            rgb=np.ascontiguousarray(rgb,dtype=np.uint8);coarse=np.ascontiguousarray(coarse,dtype=np.float64)
            boxes=np.asarray(occluder_boxes,dtype=np.float64).reshape(-1,4)
            cboxes=(Box*len(boxes))(*[Box(*q,1.,0) for q in boxes])
            start=time.perf_counter();full=original(rgb,coarse,rank_axis=rank_axis,occluder_boxes=boxes)
            full_ms=(time.perf_counter()-start)*1000
            start=time.perf_counter();b=b_refine(rgb,coarse,rank_axis=rank_axis,occluder_boxes=boxes)
            b_ms=(time.perf_counter()-start)*1000
            values={}
            for name,fn in (('full',lib.xnp_refine_full),('B',lib.xnp_refine)):
                q=np.zeros((4,2),np.float64);stats=Stats();start=time.perf_counter()
                okay=fn(rgb.ctypes.data,coarse.ctypes.data,cboxes,len(boxes),rng.ctypes.data,q.ctypes.data,C.byref(stats))
                values[name]=dict(accepted=bool(okay),corners=q,ms=(time.perf_counter()-start)*1000)
            assert values['full']['accepted']==full['accepted'],(stem,'full acceptance')
            assert values['B']['accepted']==b['accepted'],(stem,'B acceptance')
            diffs={}
            for name,py in (('full',full),('B',b)):
                error=float(np.linalg.norm(values[name]['corners']-np.asarray(py['corners']),axis=1).max()) if py['accepted'] else 0.
                assert error<1e-4,(stem,name,error)
                diffs[name]=error
            captured.update(coarse=coarse.copy(),boxes=boxes.copy(),b=b,native=values,diffs=diffs,
                            py_full_ms=full_ms,py_B_ms=b_ms)
            return full
        PL.refine_board=observe
        baseline=model.predict(image)
        def replay_refine(rgb,coarse,*,rank_axis,occluder_boxes=None,native=False):
            assert np.array_equal(coarse,captured['coarse'])
            assert np.array_equal(np.asarray(occluder_boxes),captured['boxes'])
            result=copy.deepcopy(captured['b'])
            if native and result['accepted']:result['corners']=captured['native']['B']['corners'].tolist()
            return result
        PL.refine_board=replay_refine
        python_b=model.predict(image)
        def native_refine(*args,**kwargs):return replay_refine(*args,**kwargs,native=True)
        PL.refine_board=native_refine
        native_b=model.predict(image)
        for key in ('status','candidate_placement_fen','board_placement_fen','can_use_as_candidate'):
            assert baseline[key]==python_b[key]==native_b[key],(stem,key)
        bg=baseline.get('geometry');vg=python_b.get('geometry')
        drift=float(np.linalg.norm(np.asarray(bg['corners_image_TL_TR_BR_BL'])-np.asarray(vg['corners_image_TL_TR_BR_BL']),axis=1).max()) if bg and vg else 0.
        assert drift<=2.,(stem,drift)
        row=dict(frame=stem,status_and_both_fens_equal=True,python_full_vs_B_corner_drift_px=drift,
                 native_vs_python_corner_error_px=captured['diffs'],
                 native_full_ms=captured['native']['full']['ms'],native_B_ms=captured['native']['B']['ms'],
                 python_full_ms=captured['py_full_ms'],python_B_ms=captured['py_B_ms'])
        rows.append(row)
        (out/'progress.json').write_text(json.dumps(rows,indent=2)+'\n')
        if len(rows)%15==0:print('R09_REFINEMENT_VECTOR_PASS',len(rows),'/45',flush=True)
    PL.refine_board=original
    assert parameters==LR.PARAMETERS
    assert before=={p.relative_to(REPO).as_posix():sha(p) for p in audit}
    report=dict(status='PASS',vectors=45,scope='Training frames 908..952; native/Python B vs full; no board acceptance',
                variant='B_trials80_bbox',ransac_trials=80,refine_iterations=5,threshold_contract_unchanged=True,
                C_variant_enabled=False,source_stable_during_run=True,
                max_corner_drift_px=max(r['python_full_vs_B_corner_drift_px'] for r in rows),
                max_native_vs_python_error_px=max(max(r['native_vs_python_corner_error_px'].values()) for r in rows),
                vectors_detail=rows,sources=before,hardware_used=False)
    a.receipt.write_text(json.dumps(report,indent=2)+'\n')
    print('R09_REFINEMENT_B_45_VECTOR_PASS',report['max_corner_drift_px'],flush=True)


if __name__=='__main__':main()
