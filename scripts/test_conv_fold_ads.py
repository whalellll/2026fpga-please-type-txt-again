"""Fault-inject the mapped folding proof; these are synthetic rejection tests."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ap=argparse.ArgumentParser();ap.add_argument('--native',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
vm=a.native/'pds/synthesize/soc_top_syn.vm';text=vm.read_text();module=re.search(r'(?ms)^module mac_conv_weight_dma\b.*?^endmodule',text).group()
if re.search(r'\\upper_fold\[0\]\s*\(',module):
 helper=Path(__file__).with_name('test_conv_stream_native.py');target=a.output/'stream-faults'
 subprocess.run([sys.executable,'-X','utf8',str(helper),'--native',str(a.native),'--output',str(target)],check=True,timeout=800)
 record=json.loads((target/'result.json').read_text())
 (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status']);raise SystemExit(0)
cell_pattern=r'\b(GTP_\w+)\s*/\*.*?\*/\s*#\((.*?)\)\s*(\\\S+|\w+)\s*\((.*?)\);'
cells=list(re.finditer(cell_pattern,module,re.S));fold=next(c for c in cells if re.search(r'\.Z\s*\(store_load\[512\]\)',c[4]));ff=next(c for c in cells if re.search(r'\.Q\s*\(line_shift\[512\]\)',c[4]))
init=re.search(r"(\d+)'([bh])([0-9a-fA-F_]+)",fold[2]);width=int(init[1]);value=int(init[3].replace('_',''),2 if init[2]=='b' else 16)
bad_init=fold.group().replace(init.group(),str(width)+"'h"+format(value^1,'x'),1)
bad_clock=ff.group().replace('.CLK (clk)','.CLK (wrong_clock)',1)
assert bad_clock!=ff.group()
cases={
 'wrong_fold_wiring':(module.replace('store_load[512]','FOLD_SWAP_TMP').replace('store_load[513]','store_load[512]').replace('FOLD_SWAP_TMP','store_load[513]'),'Mapped upper-fold arithmetic differs'),
 'nonlinear_lut':(module[:fold.start()]+bad_init+module[fold.end():],'Non-affine mapped fold LUT'),
 'wrong_registered_clock':(module[:ff.start()]+bad_clock+module[ff.end():],'Upper load register missing')}
results={};proof=Path(__file__).with_name('prove_conv_fold_ads.py')
for name,(source,reason) in cases.items():
 root=a.output/name;path=root/'pds/synthesize/soc_top_syn.vm';path.parent.mkdir(parents=True);path.write_text(source)
 r=subprocess.run([sys.executable,'-B',str(proof),'--root',str(root),'--output',str(root/'must-not-pass.json')],capture_output=True,timeout=60)
 log=root/'reject.log';log.write_bytes(r.stdout+r.stderr)
 assert r.returncode!=0 and reason.encode() in r.stderr,(name,r.returncode,r.stderr[-1000:])
 results[name]=dict(expected_reason=reason,vm_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
record=dict(status='FOLD_ADS_SYNTHETIC_FAULT_REJECTIONS_PASS_NOT_HARDWARE',native_source_sha256=hashlib.sha256(vm.read_bytes()).hexdigest(),proof_tool_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),cases=results)
(a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
