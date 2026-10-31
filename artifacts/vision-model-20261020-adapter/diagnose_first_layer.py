import sys,struct,json
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;G=HERE.parent/'vision-model-20261020/golden'
sys.path[:0]=[str(G/'software'),str(G/'quantization')]
import numpy as np,torch
from integer_ops import round_shift_even
from pc_exact import load_integer_runtime
from exact_mm_int64_reference import exact_mm_int64_torch as exact_mm
model=load_integer_runtime(G/'software',G/'quantization/candidate_v1');op=model.pipeline.locator.model.features[0]
inp=np.random.default_rng(20261020).integers(0,256,(1,3,192,192),dtype=np.uint8).astype(np.float32)/255
q=torch.round(torch.from_numpy(inp)/2.**op.input_exp).clamp(-128,127).to(torch.int8)
a=torch.nn.functional.unfold(q.float(),(3,3),padding=1,stride=2).transpose(1,2).reshape(-1,27).to(torch.int8)
b=op.qw.reshape(16,-1).T.contiguous()
mm=exact_mm(a,b);independent=a[:10].numpy().astype(np.int64)@b.numpy().astype(np.int64)
print('FIRST_MM_DIFFERENCE',np.count_nonzero(mm[:10].numpy()!=independent),'torch',mm[:10,0].tolist(),'numpy',independent[:,0].tolist(),flush=True)
data=(HERE.parents[1]/'build/picture-p21-native/model-r02/board.xqm').read_bytes();header=struct.unpack('<10I',data[8:48])
nodes=np.frombuffer(data,offset=48,count=header[2]*32,dtype='<i4').reshape(-1,32);n=nodes[0];blob=data[48+header[2]*128:]
for key,z,offset,dtype in [('weight',op.qw.numpy(),n[20],np.int8),('bias',op.qb.numpy(),n[21],np.int32),('shifts',op.shifts.numpy(),n[22],np.int64),('lut',op.lut.numpy(),n[23],np.int8)]:
    p=np.frombuffer(blob,offset=int(offset),count=z.size,dtype=dtype).reshape(z.shape)
    print('PACKED',key,np.array_equal(z,p),flush=True)
print('METADATA',op.metadata,'NODE',n.tolist(),flush=True)
