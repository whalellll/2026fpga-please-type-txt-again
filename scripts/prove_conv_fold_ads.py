"""Prove the mapped upper-fold network as an affine Boolean transformation."""
from pathlib import Path
from functools import lru_cache
import argparse,collections,hashlib,json
from audit_cpu_ads import Cone
from ads_bdd import lut_inputs
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
vm=a.root/'pds/synthesize/soc_top_syn.vm';cone=Cone(vm.read_text(),'mac_conv_weight_dma');constant=1<<512
if any(node['name'].startswith('upper_fold[') for node,port in cone.drivers.values() if port=='Q'):
 from prove_conv_stream_native import prove
 record=prove(a.root,Path('G:/fpga/c80f1080p6'))
 a.output.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));raise SystemExit(0)
anchors={f'line_shift[{512+i}]':i for i in range(512)};seen=set();active=set()
@lru_cache(None)
def walk(net):
 if net in ("1'b0","1'b1"):return (constant if net[-1]=='1' else 0),0
 if net in anchors:
  node,port=cone.drivers[net]
  assert port=='Q' and node['kind'].startswith('GTP_DFF') and node['ports']['CLK']=='clk',('Upper load register missing',net)
  return 1<<anchors[net],0
 assert net not in active,('Combinational cycle',net);active.add(net)
 try:
  if net in cone.aliases:return walk(cone.aliases[net])
  node,port=cone.drivers[net];table,pins=lut_inputs(node,port);c=table&1
  coefficients=[((table>>(1<<i))&1)^c for i in range(len(pins))]
  for x in range(1<<len(pins)):
   value=c
   for i,k in enumerate(coefficients):value^=((x>>i)&1)&k
   assert value==((table>>x)&1),('Non-affine mapped fold LUT',node['name'])
  result=constant if c else 0;depth=0
  for pin,k in zip(pins,coefficients):
   if k:
    mask,d=walk(pin);result^=mask;depth=max(depth,d)
  seen.add(node['name']);return result,depth+1
 finally:active.remove(net)
depths=[]
for output in range(32):
 mask,depth=walk(f'store_load[{512+output}]');expected=0
 for word in range(16):
  bit=(output-5*(15-word))%32;expected|=1<<(32*word+bit)
 assert mask==expected,('Mapped upper-fold arithmetic differs',output)
 depths.append(depth)
loads=collections.Counter();nodes={node['name']:node for node,port in cone.drivers.values()}
for node in nodes.values():
 for pin,wire in node['ports'].items():
  if pin.startswith('I') or pin in ('D','S','CIN'):loads[wire]+=1
fanout=max(loads[n] for n in anchors)
assert max(depths)<=6 and fanout<=4,('Folded preload cone requires resource/timing re-evaluation',depths,fanout)
record=dict(status='NATIVE_UPPER_FOLD_AFFINE_EXACT_PROOF_PASS_NOT_STA',scope='Each mapped LUT exhaustively affine, all32outputs exactly match512independent registered input bits. Depth/fanout are synthesis structural screening, not routed delay or physical fanout.',netlist_sha256=hashlib.sha256(vm.read_bytes()).hexdigest(),independent_input_bits=512,output_bits=32,fold_lut_cells=len(seen),maximum_fold_lut_depth=max(depths),maximum_upper_register_data_pin_loads=fanout,clock_period_ns=20.202,final_sta_required=True)
a.output.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
