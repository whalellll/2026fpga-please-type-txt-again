"""Check folded-store MAC register boundaries and retained CPU cache DRM."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
def inspect(root,width):
 vm=root/'pds/synthesize/soc_top_syn.vm';text=vm.read_text();module=re.search(r'(?m)^module mac_weight_double_buffer\b.*?^endmodule',text,re.S|re.M).group()
 ports={};pattern=r'\b(GTP_DFF\w*)\s*/\*.*?\*/\s*#\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);'
 for cell,params,name,body in re.findall(pattern,module,re.S):
  pins=dict((k,v.strip()) for k,v in re.findall(r'\.(\w+)\s*\((.*?)\)',body,re.S));q=pins.get('Q','')
  if re.fullmatch(r'read_data\[\d+\]|read_valid',q):
   assert q not in ports and pins['CLK']=='clk' and 'GRS_EN("TRUE")' in params and ".INIT(1'b0)" in params,(q,pins,params)
   ports[q]=dict(cell=cell,pins=pins)
 assert set(ports)=={f'read_data[{i}]' for i in range(width)}|{'read_valid'},'Read register coverage changed'
 banks=[ports[f'read_data[{i}]'] for i in range(width)]
 assert all(x['cell']=='GTP_DFF_RE' for x in banks) and ports['read_valid']['cell']=='GTP_DFF_R'
 assert len({x['pins']['CE'] for x in banks})==len({x['pins']['R'] for x in banks})==1
 assert all(x['pins']['CE'] not in ("1'b0","1'b1",'0','1') and x['pins']['R'] not in ("1'b0","1'b1",'0','1') for x in banks)
 for i,x in enumerate(banks):assert re.fullmatch(r'\w+\['+str(i)+r'\]',x['pins']['D']),('Read bit identity',i,x)
 output=a.output.parent/(root.name+'-resources.json')
 subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('profile_native_resources.py')),'--root',str(root),'--output',str(output)],check=True,capture_output=True)
 profile=json.loads(output.read_text());cpu={row['path']:row['inclusive']['drm36k_equivalent'] for row in profile['rows'] if row['path'].startswith('soc_top/u_cpu')}
 assert cpu and sum(cpu.values())>0,'CPU DRM hierarchy missing'
 return dict(read_registers=ports,cpu_drm=cpu,netlist_sha256=hashlib.sha256(vm.read_bytes()).hexdigest(),resource_profile_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
baseline=inspect(a.baseline,1024);candidate=inspect(a.candidate,544)
assert baseline['cpu_drm']==candidate['cpu_drm'],'CPU cache DRM mapping changed'
subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('prove_conv_fold_ads.py')),'--root',str(a.candidate),'--output',str(a.output.parent/'fold-ads-proof.json')],check=True)
record=dict(status='NATIVE_FOLDED_STORE_MAC512_CHECKSUM32_READ_BOUNDARIES_CPU_DRM_PASS_NOT_STA',baseline=baseline,candidate=candidate,scope='All512MAC data FF and32folded checksum FF plus read_valid retain clock/init/reset/enable read boundary. Upper-half representation equivalence and controls require separate RTL tests; final STA required.')
a.output.write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
