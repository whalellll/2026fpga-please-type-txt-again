"""Compare adapter C kernels with all 80 immutable four-tensor golden dumps.

CPU_REFERENCE here is explicit numerical port validation, never board evidence.
The same C entry point accepts the existing strict xqm driver transport.
"""
import argparse,ctypes as C,hashlib,json,os,subprocess,time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
CANDIDATE=HERE.parent/'vision-model-20261020/golden/quantization/candidate_v1'
FIELDS='batch cin height width cout kh kw stride_h stride_w pad_h pad_w dilation_h dilation_w linear cpu_reference'.split()
class Shape(C.Structure):
    _fields_=[(name,C.c_uint) for name in FIELDS]
class Stats(C.Structure):
    _fields_=[('jobs',C.c_uint64),('cycles',C.c_uint64)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    sources=[HERE/'runtime/xq_int8_layer.c',REPO/'linux/vision/xq_mac.c']
    libpath=a.out/'libxq_integer.so'
    command=['cc','-O3','-shared','-fPIC','-std=c11','-Wall','-Wextra','-Werror',
             '-I'+str(REPO/'linux/vision'),'-I'+str(REPO/'linux/mac_accel'),
             *map(str,sources),'-lm','-o',str(libpath)]
    subprocess.run(command,check=True)
    lib=C.CDLL(str(libpath.resolve()))
    ptr=C.c_void_p
    lib.xqi_layer.argtypes=[ptr,C.POINTER(Shape),ptr,ptr,ptr,ptr,ptr,C.c_size_t,ptr,ptr,ptr,C.POINTER(Stats)]
    lib.xqi_layer.restype=C.c_int
    lib.xqi_quantize.argtypes=[ptr,C.c_size_t,C.c_int,ptr];lib.xqi_quantize.restype=C.c_int
    lib.xqi_dequantize.argtypes=[ptr,C.c_size_t,C.c_int,ptr];lib.xqi_dequantize.restype=C.c_int
    # Independent NumPy float32 ties-even checks, including saturation/extremes.
    rng=np.random.default_rng(20261020)
    f=np.r_[np.arange(-130,131,dtype=np.float32)+.5,rng.uniform(-1000,1000,10000).astype(np.float32)]
    for exponent in (-12,-4,0,7):
        got=np.zeros(len(f),np.int8)
        assert lib.xqi_quantize(f.ctypes.data,len(f),exponent,got.ctypes.data)==1
        expected=np.clip(np.rint(f/np.float32(2.**exponent)),-128,127).astype(np.int8)
        assert np.array_equal(got,expected)
    nonfinite=np.array([np.nan],np.float32);q=np.zeros(1,np.int8)
    assert lib.xqi_quantize(nonfinite.ctypes.data,1,0,q.ctypes.data)==0
    arbitrary=rng.integers(0,2**32,size=50000,dtype=np.uint32).view(np.float32)
    arbitrary=arbitrary[np.isfinite(arbitrary)].copy()
    integer=np.arange(-32768,32768,dtype=np.int32).astype(np.int16)
    for exponent in (-120,-80,-12,-4,0,7,60,120):
        got=np.zeros(len(arbitrary),np.int8);decoded=np.zeros(len(integer),np.float32)
        assert lib.xqi_quantize(arbitrary.ctypes.data,len(arbitrary),exponent,got.ctypes.data)==1
        assert lib.xqi_dequantize(integer.ctypes.data,len(integer),exponent,decoded.ctypes.data)==1
        with np.errstate(over='ignore',under='ignore',invalid='ignore'):
            expected=np.clip(np.rint(np.ldexp(arbitrary,-exponent)),-128,127).astype(np.int8)
            reference=np.ldexp(integer.astype(np.float32),exponent)
        assert np.array_equal(got,expected),exponent
        assert np.array_equal(decoded.view(np.uint32),reference.view(np.uint32)),exponent
    graph=json.loads((CANDIDATE/'integer_graph.json').read_text())
    dumps=json.loads((CANDIDATE/'golden_dump_manifest.json').read_text())
    paths={r['path'].split('/')[-1].removesuffix('_call0.npz'):CANDIDATE/r['path'] for r in dumps}
    rows=[]
    for meta in graph['layers']:
        ident=meta['layer_id'];start=time.monotonic()
        with np.load(CANDIDATE/'int8'/(ident+'.npz'),allow_pickle=False) as z:
            weight=z['weight'].copy();bias=z['bias'].copy();shifts=z['right_shifts'].copy();lut=z['activation_lut'].copy()
        with np.load(paths[ident],allow_pickle=False) as z:
            inp=z['input_q'].copy();expected={k:z[k].copy() for k in ('accumulator_with_bias','preactivation_s16','output_q')}
        dims=inp.shape;w=weight.shape
        if meta['kind']=='linear':
            shape=Shape(int(np.prod(dims[:-1])),dims[-1],1,1,w[0],1,1,1,1,0,0,1,1,1,1)
        else:
            shape=Shape(*dims,w[0],w[2],w[3],*meta['stride'],*meta['padding'],*meta['dilation'],0,1)
        shape_out=expected['output_q'].shape
        acc=np.zeros(shape_out,np.int32);pre=np.zeros(shape_out,np.int16);out=np.zeros(shape_out,np.int16);stats=Stats()
        args=[inp,weight,bias,shifts,lut,acc,pre,out]
        assert lib.xqi_layer(None,C.byref(shape),*[x.ctypes.data for x in args[:4]],lut.ctypes.data,lut.nbytes,
                             acc.ctypes.data,pre.ctypes.data,out.ctypes.data,C.byref(stats))==1,ident
        assert stats.jobs==0 and stats.cycles==0
        checks={k:bool(np.array_equal(got,expected[k])) for k,got in
                [('accumulator_with_bias',acc),('preactivation_s16',pre),('output_q',out)]}
        if not all(checks.values()):raise AssertionError((ident,checks))
        shape.cpu_reference=0
        assert lib.xqi_layer(None,C.byref(shape),*[x.ctypes.data for x in args[:4]],lut.ctypes.data,lut.nbytes,
                             acc.ctypes.data,pre.ctypes.data,out.ctypes.data,C.byref(stats))==0
        rows.append(dict(layer=ident,input_shape=list(dims),output_shape=list(shape_out),checks=checks,
                         elapsed_s=time.monotonic()-start,weight_sha256=sha(CANDIDATE/'int8'/(ident+'.npz')),
                         dump_sha256=sha(paths[ident])))
        if len(rows)%10==0:print('NATIVE_LAYER_CHECK',len(rows),'/80',flush=True)
    result=dict(status='PASS',scope='PC C CPU_REFERENCE vs immutable golden layer dumps; NOT board/full-graph acceptance',
                layers=len(rows),checks=rows,compile_command=command,graph_sha256=sha(CANDIDATE/'integer_graph.json'),
                sources={str(s.relative_to(REPO)):sha(s) for s in sources+[HERE/'runtime/xq_int8_layer.h']},
                quantization_checks=4*len(f)+8*len(arbitrary),dequantization_checks=8*len(integer),device_fallback_allowed=False)
    (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('NATIVE_80_LAYER_PASS',flush=True)
if __name__=='__main__':main()
