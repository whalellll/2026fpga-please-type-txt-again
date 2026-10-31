"""Full native C CNN graphs vs original quantized Torch graphs on explicit inputs."""
import argparse,ctypes as C,hashlib,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
import numpy as np,torch
from pc_exact import ensure_integer_ops,load_integer_runtime
ensure_integer_ops()
from integer_ops import IntegerOp
class Stats(C.Structure):_fields_=[('jobs',C.c_uint64),('cycles',C.c_uint64)]
def main():
    p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True);p.add_argument('--library',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--release',type=Path,default=G/'software');p.add_argument('--candidate',type=Path,default=G/'quantization/candidate_v1')
    p.add_argument('--detector-size',type=int,choices=[416,640],default=640)
    p.add_argument('--integer-oracle',choices=['exact-int64'],default='exact-int64')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    lib=C.CDLL(str(a.library.resolve()));ptr=C.c_void_p
    lib.xqn_load.argtypes=[C.c_char_p];lib.xqn_load.restype=ptr;lib.xqn_free.argtypes=[ptr]
    lib.xqn_run.argtypes=[ptr,ptr,C.c_uint,ptr,C.c_int,C.POINTER(Stats)];lib.xqn_run.restype=C.c_int
    lib.xqn_output.argtypes=[ptr,C.c_uint,C.POINTER(C.c_uint)];lib.xqn_output.restype=C.POINTER(C.c_float)
    lib.xqn_board_corners.argtypes=[ptr,ptr];lib.xqn_board_corners.restype=C.c_int
    m=load_integer_runtime(a.release,a.candidate)
    roots=dict(board=m.pipeline.locator.model,detector=m.pipeline.detector.detector.model,classifier=m.pipeline.detector.classifier)
    metadata=json.loads((a.candidate/'integer_graph.json').read_text())['layers']
    layer_ids={meta['layer_id']:i for i,meta in enumerate(metadata)}
    observer_type=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.POINTER(C.c_int8),C.c_size_t,C.POINTER(C.c_int16),C.c_size_t,C.POINTER(C.c_int32),C.POINTER(C.c_int16))
    lib.xqn_observe.argtypes=[ptr,observer_type,ptr]
    report={};rng=np.random.default_rng(20261020)
    for name,root in roots.items():
        side=192 if name=='board' else a.detector_size if name=='detector' else 32
        batch=3 if name=='classifier' else 1
        inp=(rng.integers(0,256,(batch,3,side,side),dtype=np.uint8).astype(np.float32)/255).copy()
        heads=[];handles=[];layer_expected={};layer_checks=[]
        def reference_hook(module,args,out):
            i=layer_ids[module.layer_id];x=args[0].detach().cpu().numpy();y=out.detach().cpu().numpy()
            layer_expected[i]=(np.clip(np.rint(x/np.float32(2.**module.input_exp)),-128,127).astype(np.int8).reshape(-1),
                               np.rint(y/np.float32(2.**(module.output_exp if module.lut.numel() else module.pre_exp))).astype(np.int16).reshape(-1))
        for node in root.modules():
            if isinstance(node,IntegerOp):handles.append(node.register_forward_hook(reference_hook))
        if name=='board':
            handles += [root.head[-1].register_forward_hook(lambda module,args,out:heads.append(out.detach().cpu().numpy().copy())),
                        root.corner_maps.register_forward_hook(lambda module,args,out:heads.append(out.detach().cpu().numpy().copy()))]
        if name=='detector':
            for layer in root.model[-1].m:handles.append(layer.register_forward_hook(lambda module,args,out:heads.append(out.detach().cpu().numpy().copy())))
        with torch.inference_mode():expected=root(torch.from_numpy(inp))
        for h in handles:h.remove()
        if name=='classifier':heads=[expected.numpy()]
        model=lib.xqn_load(str(a.models/(name+'.xqm')).encode());assert model,name
        def observed(ctx,i,q,qn,out,on,acc,pre):
            qi=np.ctypeslib.as_array(q,shape=(qn,));qo=np.ctypeslib.as_array(out,shape=(on,));eq,eo=layer_expected[i]
            row=dict(layer=metadata[i]['layer_id'],input_exact=bool(np.array_equal(qi,eq)),output_exact=bool(np.array_equal(qo,eo)))
            layer_checks.append(row)
            if not row['input_exact'] or not row['output_exact']:
                print('LAYER_DRIFT',row,'input_diff',np.count_nonzero(qi!=eq),'output_diff',np.count_nonzero(qo!=eo),
                      'first_outputs',qo[:12].tolist(),eo[:12].tolist(),flush=True)
        observer=observer_type(observed);lib.xqn_observe(model,observer,None)
        start=time.monotonic();stats=Stats()
        assert lib.xqn_run(model,None,batch,inp.ctypes.data,1,C.byref(stats))==1,name
        checks=[]
        assert all(row['input_exact'] and row['output_exact'] for row in layer_checks),layer_checks
        (a.out/(name+'-layers.json')).write_text(json.dumps(layer_checks,indent=2)+'\n')
        for i,head in enumerate(heads):
            dims=(C.c_uint*4)();data=lib.xqn_output(model,i,dims);assert data
            got=np.ctypeslib.as_array(data,shape=(int(np.prod(dims)),)).reshape(head.shape)
            diff=float(np.max(np.abs(got-head)))
            # Sigmoid is an explicit host FP32 op, outside integer bit-exact.
            if name=='board' and i==0:assert diff<=1e-7,(name,i,diff)
            else:assert np.array_equal(got,head),(name,i,diff,int(np.count_nonzero(got!=head)))
            checks.append(dict(shape=list(head.shape),exact=bool(np.array_equal(got,head)),max_abs_error=diff))
        if name=='board':
            corners=np.zeros((4,2),np.float32);assert lib.xqn_board_corners(model,corners.ctypes.data)
            diff=float(np.max(np.abs(corners-expected.numpy()[0])));assert diff<2e-6,diff
            checks.append(dict(scope='host FP32 heatmap+prior decode',max_normalized_corner_difference=diff))
        report[name]=dict(batch=batch,heads=checks,elapsed_s=time.monotonic()-start,actual_device_jobs=stats.jobs,
                          model_sha256=hashlib.sha256((a.models/(name+'.xqm')).read_bytes()).hexdigest())
        assert stats.jobs==0
        lib.xqn_free(model);print('NATIVE_GRAPH_PASS',name,report[name],flush=True)
    bad=bytearray((a.models/'board.xqm').read_bytes());bad[-1]^=1
    badpath=a.out/'corrupt.xqm';badpath.write_bytes(bad);assert not lib.xqn_load(str(badpath).encode());badpath.unlink()
    (a.out/'result.json').write_text(json.dumps(dict(status='PASS',scope='PC native CPU_REFERENCE full CNN graphs; not board inference',models=report,
        corrupted_model_rejected=True,three_models=3,integer_oracle=a.integer_oracle,
        delivered_int_mm_equivalence=False,source_library_sha256=hashlib.sha256(a.library.read_bytes()).hexdigest()),indent=2)+'\n')
if __name__=='__main__':main()
