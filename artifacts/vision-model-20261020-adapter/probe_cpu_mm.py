import argparse,json,os,torch,numpy as np
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',type=Path);args=p.parse_args()
torch.set_num_threads(1)
r=np.random.default_rng(20261020)
a=r.integers(0,65,(32,32),dtype=np.int8);b=r.integers(-127,128,(32,16),dtype=np.int16).astype(np.int8)
y=torch._int_mm(torch.from_numpy(a),torch.from_numpy(b)).numpy();z=a.astype(np.int64)@b.astype(np.int64)
print('CPU_INT_MM',torch.backends.cpu.get_cpu_capability(),'ATEN',os.getenv('ATEN_CPU_CAPABILITY'),'DNNL',os.getenv('DNNL_MAX_CPU_ISA'),
      'mismatches',int(np.count_nonzero(y!=z)),'max_error',int(np.max(np.abs(y-z))),flush=True)
if args.out:
    if args.out.exists():raise FileExistsError(args.out)
    examples=[]
    for row,col in np.argwhere(y!=z)[:3]:
        examples.append(dict(row=int(row),column=int(col),input=a[row].tolist(),weight=b[:,col].tolist(),
                             torch_accumulator=int(y[row,col]),independent_int64_accumulator=int(z[row,col])))
    args.out.write_text(json.dumps(dict(torch_version=torch.__version__,capability=torch.backends.cpu.get_cpu_capability(),
        seed=20261020,input_shape=list(a.shape),weight_shape=list(b.shape),mismatches=int(np.count_nonzero(y!=z)),
        max_absolute_error=int(np.max(np.abs(y-z))),examples=examples,scope='Random arithmetic probe, not camera/weights'),indent=2)+'\n')
