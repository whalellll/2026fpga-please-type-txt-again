"""Verify pinned board/classifier snapshots through the real runtime + mocked ioctl."""
import ctypes as C,hashlib,json,subprocess
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;R=HERE.parents[1];B=R/'build/picture-merge-20261023';E=R/'docs/validation/picture-merge-20261023'
class Stats(C.Structure):_fields_=[('jobs',C.c_uint64),('cycles',C.c_uint64)]
def main():
 libpath=B/'pinned-graph.so'
 sources=[HERE/'runtime'/n for n in ('xq_native_graph.c','xq_int8_layer.c','xq_resident_matrix.c','mock_resident_transport.c')]+[R/'sw/bootloader/crc32_fast.c']
 subprocess.run(['gcc','-shared','-fPIC','-O3','-std=c11','-ffp-contract=off','-DXQ_NATIVE_DIRECT_PACK','-Dxqm_matrix=xqn_resident_matrix','-Wl,--wrap=ioctl','-I'+str(R/'linux/vision'),'-I'+str(R/'linux/mac_accel'),'-I'+str(R/'sw/bootloader'),*map(str,sources),'-lm','-o',str(libpath)],check=True)
 lib=C.CDLL(str(libpath));P=C.c_void_p
 lib.xqn_load.argtypes=[C.c_char_p];lib.xqn_load.restype=P;lib.xqn_free.argtypes=[P]
 lib.xqn_mock_open.restype=P;lib.xqn_mock_close.argtypes=[P];lib.xqn_mock_counters.argtypes=[P,C.POINTER(C.c_uint)]
 lib.xqn_pin_resident.argtypes=[P,P];lib.xqn_pin_resident.restype=C.c_int
 lib.xqn_run.argtypes=[P,P,C.c_uint,P,C.c_int,C.POINTER(Stats)];lib.xqn_run.restype=C.c_int
 lib.xqn_output.argtypes=[P,C.c_uint,C.POINTER(C.c_uint)];lib.xqn_output.restype=C.POINTER(C.c_float)
 rng=np.random.default_rng(20261023);models={};reports={}
 def outputs(model,count):
  values=[]
  for i in range(count):
   dims=(C.c_uint*4)();p=lib.xqn_output(model,i,dims);assert p;values.append(np.ctypeslib.as_array(p,shape=(int(np.prod(list(dims))),)).copy())
  return values
 for name,side,batch,heads in [('board',192,1,2),('classifier',32,3,1)]:
  model=lib.xqn_load(str(B/'native-models'/(name+'.xqm')).encode());transport=lib.xqn_mock_open();assert model and transport
  assert lib.xqn_pin_resident(model,transport)
  image=rng.random((batch,3,side,side),dtype=np.float32);stats=Stats();assert lib.xqn_run(model,None,batch,image.ctypes.data,1,C.byref(stats))
  models[name]=(model,transport,image,batch,heads,outputs(model,heads))
 for frame in range(2):
  for name,(model,transport,image,batch,heads,expected) in models.items():
   stats=Stats();assert lib.xqn_run(model,transport,batch,image.ctypes.data,0,C.byref(stats));assert stats.jobs>0
   got=outputs(model,heads);assert all(np.array_equal(a,b) for a,b in zip(expected,got)),name
 for name,(model,transport,*_) in models.items():
  counters=(C.c_uint*3)();lib.xqn_mock_counters(transport,counters)
  assert counters[0]==1 and counters[2]>=2
  reports[name]=dict(registrations=counters[0],simulated_jobs=counters[1],physical_owner_restores_simulated=counters[2],two_frames_heads_bit_exact=True)
  lib.xqn_free(model);lib.xqn_mock_close(transport)
 (E/'pinned-models.json').write_text(json.dumps(dict(status='PASS',models=reports,scope='PC actual C graph/runtime; fd snapshots and driver owner restoration emulated; no hardware',hardware_used=False,production_ready=False,source_sha256={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}),indent=2)+'\n')
 print('PINNED_MODELS_CROSS_FD_BIT_EXACT_PASS',reports,flush=True)
if __name__=='__main__':main()
