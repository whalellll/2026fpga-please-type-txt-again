"""Verified native DRM/APM output boundaries, used only as explicit data inputs."""
from functools import lru_cache
import re
from audit_cpu_ads import signal
from native_boolean_graph_v3 import BooleanGraph,MemoryBoundaryCone

class NativeDataBoundaryCone(MemoryBoundaryCone):
 @lru_cache(None)
 def cone(self,kind):
  c=super().cone(kind);body=re.sub(r'/\*.*?\*/|//[^\n]*','',self.modules[kind],flags=re.S)
  cells=list(re.finditer(r'\b(GTP_DRM(?:18K|36K)_E1|GTP_APM_E2)\s*#\s*\((.*?)\)\s+(\w+)\s*\((.*?)\);',body,re.S))
  if not cells:return c
  context=next(ctx for ctx,row in self.contexts.items() if row[0]==kind)
  for m in cells:
   primitive,params,name,connections=m.groups();p={k:signal(v) for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',connections)};parameters={k:v.strip() for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',params)}
   if primitive.startswith('GTP_DRM'):
    init=[v for k,v in parameters.items() if re.fullmatch(r'INIT_[0-9A-F]{2}',k)]
    assert init and all(re.fullmatch(r"288'b[01]{288}",v) for v in init),('Unknown native DRM initialization',kind,name)
    assert parameters['RAM_MODE']=='"SIMPLE_DUAL_PORT"'
    if '36K' in primitive:assert parameters['ECC_READ_EN']==parameters['ECC_WRITE_EN']=='"FALSE"'
    else:assert 'ECC_READ_EN' not in parameters and 'ECC_WRITE_EN' not in parameters
    outputs=['DOA','DOB'];width=36 if '36K' in primitive else 18
   else:
    assert parameters['MULT_REG']=='1',('Unreviewed APM data boundary',kind,name)
    assert all(v in ['0','1'] for k,v in parameters.items() if k.endswith('_REG')),('Unknown APM register parameter',kind,name)
    outputs=['P'];width=48
   for port in outputs:
    if not p.get(port):continue
    nets=self.vector_bits(context,p[port]);assert len(nets)==width,('Native output width mismatch',kind,name,port,len(nets),width)
    for bit,net in enumerate(nets):
     assert net not in ["1'b0","1'b1","1'bx","1'bz"],('Invalid native output connection',kind,name,port,net)
     assert net not in c.drivers,('Duplicate native boundary driver',kind,net)
     c.drivers[net]=({'kind':primitive,'name':name,'ports':p,'init':None,'native_data_bit':bit},port)
  return c

class NativeDataGraph(BooleanGraph):
 def __init__(self,source):
  self.h=NativeDataBoundaryCone(source);self.stops=set();self.nodes={};self.active=set();self.ffs={}
 def visit(self,key):
  if key in self.nodes or key in self.stops or key[0]==('UNKNOWN',) or key[1] in ["1'b0","1'b1"]:return super().visit(key)
  ctx,net=key;c=self.h.cone(self.h.contexts[ctx][0])
  if net in c.drivers:
   node,port=c.drivers[net]
   if (node['kind'].startswith('GTP_DRM') and port in ['DOA','DOB']) or (node['kind']=='GTP_APM_E2' and port=='P'):
    self.nodes[key]=('opaque_native_data',);return key
  return super().visit(key)
