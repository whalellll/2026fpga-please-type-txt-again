"""Compile existing INT8 detector into an integer-only HWC graph and native input.

No new training/calibration. User explicitly chose existing INT8 weights.
Conservative dyadic bounds retain exact Add/Concat values; narrow only when safe.
"""
import argparse,array,hashlib,json,struct,tarfile,zlib
from pathlib import Path
from workspace_paths import workspace_path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
source=Path('G:/fpga/performance_soc_transfer_reuse_20261025/build/detector-stage-build-03/source/assets.tar.gz')
with tarfile.open(source,'r:gz') as tar:
 def item(name):
  items=[m for m in tar.getmembers() if m.name==name or m.name.endswith('/'+name)];assert len(items)==1
  return tar.extractfile(items[0]).read()
 model=item('detector.xqm');inp=item('detector.f32')
expected=json.loads((R/'docs/validation/transfer-reuse-20261025/board-models.json').read_text(encoding='utf-8'))['fixed_input_hashes']
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(model)==expected['opt/integrated60/assets/detector.xqm'] and sha(inp)==expected['opt/integrated60/assets/detector.f32']
h=struct.unpack_from('<10I',model,8);assert model[:8]==b'XQGRPH1\0' and h[:2]==(1,1) and zlib.crc32(model[48:])==h[9]
nodes=[list(struct.unpack_from('<32i',model,48+i*128)) for i in range(h[2])];blob=model[48+h[2]*128:]
outputs=list(h[4:4+h[3]]);children=[[] for _ in nodes]
for i,n in enumerate(nodes):
 for parent in n[5:5+n[4]]:
  assert parent<i
  if parent>=0:children[parent].append(i)
def q8(v,delta):
 mag=abs(v)
 if delta>=0:q=mag<<delta if delta<8 else (128 if mag else 0)
 else:
  k=-delta
  if k>31:q=0
  else:
   q=mag>>k;r=mag- (q<<k);half=1<<(k-1)
   if r>half or (r==half and q&1):q+=1
 q=min(q,128 if v<0 else 127)
 return -q if v<0 else q
newblob=bytearray();bounds=[];original_exp=[n[19] for n in nodes];fusions=[]
def data(b):
 newblob.extend(b'\0'*((-len(newblob))%8));offset=len(newblob);newblob.extend(b);return offset
for i,n in enumerate(nodes):
 assert n[0] in (1,4,5,7,8,10,11),'Unsupported integer operator; do not use float fallback'
 if n[0]==1:
  ci=3 if n[5]<0 else nodes[n[5]][1];co=n[1];kh,kw=n[10:12];k=ci*kh*kw
  assert n[25]==0 and k<=1152 and kh==kw and kh in (1,3,6)
  weight=blob[n[20]:n[20]+co*k];assert len(weight)==co*k
  packed=bytearray(((co+7)//8)*k*8)
  for oc in range(co):
   for y in range(kh):
    for x in range(kw):
     for c in range(ci):packed[(((oc//8*kh+y)*kw+x)*ci+c)*8+oc%8]=weight[((oc*ci+c)*kh+y)*kw+x]
  params=bytearray(((co+7)//8)*8*12)
  for oc in range(((co+7)//8)*8):
   bias=struct.unpack_from('<i',blob,n[21]+oc*4)[0] if oc<co else 0;shift=struct.unpack_from('<q',blob,n[22]+oc*8)[0] if oc<co else 0
   assert 0<=shift<=62;struct.pack_into('<iII',params,oc*12,bias,1,shift)
  lut=blob[n[23]:n[23]+n[24]];assert len(lut)==n[24] and n[24] in (0,65536)
  old_exp=original_exp[i]
  # Only quantization consumers: replacing this LUT with each consumer's exact
  # INT8 input is lossless even though the intermediate representation changes.
  desired={nodes[j][18] for j in children[i] if nodes[j][0]==1}
  can_fuse=bool(lut and children[i] and i not in outputs and len(desired)==1 and all(nodes[j][0]==1 for j in children[i]))
  n[31]=int(i in outputs)
  if can_fuse:
   target=next(iter(desired));lut=bytes(q8(v if v<128 else v-256,old_exp-target)&255 for v in lut)
   n[19]=target;n[31]|=2;fusions.append(i)
  if lut:
   values=[v if v<128 else v-256 for v in lut];lo,hi=min(values),max(values)
  else:lo,hi=-32768,32767
  n[20]=data(packed);n[21]=data(params);n[22]=0;n[23]=data(lut);n[29]=len(packed);n[30]=len(params)
 else:
  ps=n[5:5+n[4]];assert all(j>=0 for j in ps)
  exponent=min(nodes[j][19] for j in ps)
  ranges=[]
  for j in ps:
   shift=nodes[j][19]-exponent;assert 0<=shift<=30
   ranges.append((bounds[j][0]*(1<<shift),bounds[j][1]*(1<<shift)))
  if n[0]==8:lo,hi=sum(v[0] for v in ranges),sum(v[1] for v in ranges)
  else:lo,hi=min(v[0] for v in ranges),max(v[1] for v in ranges)
  if n[0]==11:lo,hi=max(0,lo),max(0,hi)
  n[19]=exponent;n[20]=n[21]=n[22]=n[23]=n[24]=n[29]=n[30]=0;n[31]=int(i in outputs)
 assert -100<=n[19]<=100 and max(abs(lo),abs(hi))<(1<<24),'Require exact binary32 dyadic representation'
 n[27]=8 if -128<=lo and hi<=127 else 16 if -32768<=lo and hi<=32767 else 32
 n[28]=max(abs(lo),abs(hi));bounds.append((lo,hi))
body=b''.join(struct.pack('<32i',*n) for n in nodes)+newblob
header=struct.pack('<8s10I',b'XQINT81\0',1,1,len(nodes),len(outputs),*(outputs+[0xffffffff]*(3-len(outputs))),len(newblob),len(body),zlib.crc32(body))
binary=header+body;(out/'detector.xqi').write_bytes(binary)
side=640;pixels=side*side;bits=array.array('I');bits.frombytes(inp);assert len(bits)==pixels*3
exponent=nodes[0][18];native=bytearray(pixels*4)
def from_float_bits(b):
 field=(b>>23)&255;negative=b>>31;assert field!=255
 if not field:return 0
 mantissa=(b&0x7fffff)|0x800000;shift=150+exponent-field
 if shift<=16:q=128
 elif shift>24:q=0
 else:
  q=mantissa>>shift;r=mantissa&((1<<shift)-1);half=1<<(shift-1)
  if r>half or (r==half and q&1):q+=1
 return -min(q,128) if negative else min(q,127)
cache={b:from_float_bits(b) for b in set(bits)}
for c in range(3):
 for p in range(pixels):native[p*4+c]=cache[bits[c*pixels+p]]&255
input_header=struct.pack('<8s6IiI',b'XQHWC81\0',1,side,side,3,4,len(native),exponent,zlib.crc32(native))
(out/'detector.hwc8').write_bytes(input_header+native)
(out/'reference.xqm').write_bytes(model);(out/'reference.f32').write_bytes(inp)
report=dict(status='INTEGER_HWC_DETECTOR_COMPILED_REFERENCE_CHECK_PENDING',temporary=True,weights='Existing genuine INT8 weights reused per explicit user reply; no FP32 checkpoint conversion claimed',
 source_model_sha256=sha(model),source_input_sha256=sha(inp),model_sha256=sha(binary),input_sha256=sha(input_header+native),
 float_operators=0,node_count=len(nodes),conv_layers=sum(n[0]==1 for n in nodes),input_exponent=exponent,input_layout='HWC4',
 tensor_bits={str(b):sum(n[27]==b for n in nodes) for b in (8,16,32)},lut_input_quant_fused_nodes=fusions,
 all_integer_graph=True,accumulator_bits=32,precision_contract='Dyadic bounds under24 bits preserve float Add/Concat; LUT changes only on equal-scale Conv-only edges. Actual outputs still require independent oracle comparison.',
 nodes=[dict(index=i,opcode=n[0],shape=n[1:4],exponent=n[19],bits=n[27],lo=bounds[i][0],hi=bounds[i][1]) for i,n in enumerate(nodes)])
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='nodes'},indent=2))
