"""Read-only mapped Boolean graph with exact LUT constants/alias cofactors."""
from functools import lru_cache
import re
from ads_bdd import lut_inputs
from audit_cpu_ads import signal
from native_hier_cone_vector_v2 import VectorHierCone

class MemoryBoundaryCone(VectorHierCone):
 @lru_cache(None)
 def cone(self,kind):
  c=super().cone(kind)
  body=re.sub(r'/\*.*?\*/|//[^\n]*','',self.modules[kind],flags=re.S)
  for cell in re.finditer(r'\b(GTP_RAM32X2DP)\s*#\s*\((.*?)\)\s+(\w+)\s*\((.*?)\);',body,re.S):
   primitive,params,name,connections=cell.groups()
   ports={p:signal(v) for p,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',connections)}
   output=ports['DO'];assert output.startswith('{') and output.endswith('}'),('Unsupported RAM DO',kind,name,output)
   bits=output[1:-1].split(',');assert len(bits)==2 and all(re.fullmatch(r'[A-Za-z_$][\w$]*\[\d+\]',bit) for bit in bits),('Unsupported RAM DO bits',kind,name,output)
   assert all(p in ports for p in ['DI','RADDR','WADDR','WCLK','WE'])
   assert all(re.search(r'\.INIT_'+str(i)+r'\s*\(\s*32.b[01]{32}\s*\)',params) for i in range(2)),('Unknown RAM init',kind,name)
   for index,net in enumerate(reversed(bits)):
    assert net not in c.drivers,('Duplicate RAM output',kind,net)
    c.drivers[net]=({'kind':primitive,'name':name,'ports':ports,'init':None,'ram_bit':index},'DO')
  return c

class BooleanGraph:
 def __init__(self,source):
  self.h=MemoryBoundaryCone(source);self.stops=set();self.nodes={};self.active=set();self.ffs={}
 def key(self,ctx,net):
  n=signal(net)
  if n in ("1'bx","1'bz"):return (('UNKNOWN',),n)
  try:return self.h.canonical(ctx,n)
  except AssertionError as ex:
   detail=ex.args[0] if ex.args else None
   if isinstance(detail,tuple) and detail and detail[0]=='Unknown value in requested proof':
    return (('UNKNOWN',),detail[1][1])
   raise
 def anchor(self,ctx,net):
  key=self.key(ctx,net)
  if key[0]!=('UNKNOWN',) and key[1] not in ("1'b0","1'b1"):self.stops.add(key)
  return key
 def build(self,ctx,net):return self.visit(self.key(ctx,net))
 def visit(self,key):
  if key in self.nodes:return key
  assert key not in self.active,('Mapped Boolean cycle',key)
  if key[0]==('UNKNOWN',):raise AssertionError(('Requested unknown value',key))
  ctx,net=key
  if net in ("1'b0","1'b1"):self.nodes[key]=('const',int(net[-1]));return key
  if key in self.stops:self.nodes[key]=('input',);return key
  self.active.add(key)
  try:
   kind=self.h.contexts[ctx][0];c=self.h.cone(kind)
   if net not in c.drivers:
    base=net.split('[')[0]
    assert ctx==() and self.h.directions(kind).get(base)=='input',('Unknown graph leaf',key)
    self.nodes[key]=('external',);return key
   node,port=c.drivers[net]
   if port=='DO' and node['kind']=='GTP_RAM32X2DP':self.nodes[key]=('ram',);return key
   if port=='Q' and node['kind'].startswith('GTP_DFF'):
    assert node['init'] in [0,1],('Unknown FF INIT',key,node['init'])
    self.nodes[key]=('ff',node['init']);self.ffs[key]=node['kind'];return key
   if node['kind'].startswith('GTP_MUX2'):table,pins=0xca,[node['ports']['I0'],node['ports']['I1'],node['ports']['S']]
   else:table,pins=lut_inputs(node,port)
   keys=[self.key(ctx,pin) for pin in pins];unique=[]
   for value in keys:
    if value[1] not in ("1'b0","1'b1") and value not in unique:unique.append(value)
   normalized=0
   for assignment in range(1<<len(unique)):
    index=0
    for i,value in enumerate(keys):
     bit=int(value[1][-1]) if value[1] in ("1'b0","1'b1") else (assignment>>unique.index(value))&1
     index|=bit<<i
    normalized|=((table>>index)&1)<<assignment
   relevant=[i for i in range(len(unique)) if any(((normalized>>a)^(normalized>>(a^(1<<i))))&1 for a in range(1<<len(unique)))]
   children=[unique[i] for i in relevant];reduced=0
   for assignment in range(1<<len(children)):
    original=sum(((assignment>>i)&1)<<old for i,old in enumerate(relevant));reduced|=((normalized>>original)&1)<<assignment
   for child in children:self.visit(child)
   self.nodes[key]=('truth',reduced,tuple(children));return key
  finally:self.active.remove(key)
 def depth(self,target,source):
  @lru_cache(None)
  def step(key):
   if key==source:return 0
   node=self.nodes[key]
   if node[0]!='truth':return None
   depths=[step(child) for child in node[2]];depths=[v for v in depths if v is not None]
   return 1+max(depths) if depths else None
  return step(target)
 def evaluate(self,target,values):
  cache={}
  def go(key):
   if key in cache:return cache[key]
   node=self.nodes[key]
   if node[0]=='const':value=node[1]
   elif node[0] in ('input','ram'):assert key in values,('Missing graph input',key);value=values[key]
   elif node[0]=='ff':value=values.get(key,node[1])
   elif node[0]=='external':value=values.get(key,0)
   else:value=(node[1]>>sum(go(child)<<i for i,child in enumerate(node[2])))&1
   assert value in [0,1],('Nonboolean input',key,value);cache[key]=value;return value
  return go(target)

def csr_graph(source):
 g=BooleanGraph(source);backend=g.h.find('CoreBackend');decoder=backend+('u_decoder0',);rename=g.h.find('Rename');g.h.children(backend)
 anchors={}
 for label,ctx,port in [('i0',backend,'io_ib_pop0_inst'),('i1',backend,'io_ib_pop1_inst'),('priv',decoder,'io_privilege'),('status',decoder,'io_status'),('access',decoder,'io_counterAccess')]:
  anchors[label]={int(net.rsplit('[',1)[1][:-1]):g.anchor(ctx,net) for net in g.h.vector_bits(ctx,port)}
 # Anchor only explicitly verified instruction RAM outputs, not arbitrary missing drivers.
 frontend=g.h.find('CoreFrontend');g.h.children(frontend);buffer=frontend+('buffer',);banks=[]
 for child in g.h.children(buffer):
  if re.fullmatch(r'bank_[0-3]_ext',child[-1]):
   kind=g.h.contexts[child][0];c=g.h.cone(kind)
   bits={int(net.split('[')[1][:-1]):g.anchor(child,net) for net,(node,port) in c.drivers.items() if port=='DO' and net.startswith('R0_data[')}
   assert all(bit in bits for bit in range(32,64)),('Missing instruction RAM bits',child)
   banks.append(bits)
 assert len(banks)==4,('Expected four instruction banks',banks)
 anchors['banks']=banks
 target=g.build(rename,'io_ibRfWe_0')
 return g,target,anchors

def values_for(g,anchors,word,priv,status,access):
 values={}
 for name,value in [('i0',word),('i1',word),('priv',priv),('status',status),('access',access)]:
  for bit,key in anchors[name].items():
   if key not in g.nodes:continue
   v=(value>>bit)&1
   if key[1] in ("1'b0","1'b1"):assert int(key[1][-1])==v,('Constant boundary inconsistent',name,bit,v);continue
   assert key not in values or values[key]==v,('Aliased boundary values inconsistent',name,bit)
   values[key]=v
 for bank in anchors['banks']:
  for bit,key in bank.items():
   if key not in g.nodes:continue
   assert 32<=bit<64,('Unexpected noninstruction memory dependency',key)
   value=(word>>(bit-32))&1
   assert key not in values or values[key]==value
   values[key]=value
 return values
