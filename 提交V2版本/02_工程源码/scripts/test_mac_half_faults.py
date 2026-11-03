"""Reject half-row selection, output-address and bias mapping mutations."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,subprocess
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--icarus-bin',type=Path,required=True);a=ap.parse_args()
root=Path(__file__).resolve().parents[1];a.output.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
original=root/'rtl/mac_accel/MacAccelCore.v';digest=sha(original);source=original.read_text()
oracle=root/'sim/reference/mac_half_output_p8.v.gz';meta=json.loads(oracle.with_suffix('.json').read_text());raw=gzip.decompress(oracle.read_bytes());assert hashlib.sha256(raw).hexdigest()==meta['raw_sha256'] and sha(oracle)==meta['gzip_sha256']
s=raw.decode();names=re.findall(r'^module\s+(\w+)',s,re.M);s=re.sub(r'\b(?:'+'|'.join(map(re.escape,names))+r')\b',lambda m:'Baseline'+m[0],s);ref=a.output/'reference.v';ref.write_text(s)
# A real failing output comparison is required. Compilation errors, unknown
# data, timeout or inability to run do not count as detection.
bench=(root/'sim/tb_mac_half_output.sv').read_text();bench=bench.replace('for(id=0;id<65;id=id+1)','for(id=64;id<65;id=id+1)')
cut=bench.index('        // Reset at every active phase');bench=bench[:cut]+'        $display("HALF_FAULT_BASELINE_PASS");$finish;\n    end\nendmodule\n'
tb=a.output/'bench.sv';tb.write_text(bench)
faults={
 'weight_upper_half_stale':("coTileIndex[0] ? io_wtRdata[1023:512] : io_wtRdata[511:0]","1'b0 ? io_wtRdata[1023:512] : io_wtRdata[511:0]"),
 'bias_upper_half_stale':("coTileIndex[0] ? io_biasRdata[1535:768] : io_biasRdata[767:0]","1'b0 ? io_biasRdata[1535:768] : io_biasRdata[767:0]"),
 'second_half_wrong_output_offset':("computeModeR == 0 ? 8 : 16","computeModeR == 0 ? 8 : 15"),
}
env=dict(os.environ);env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH'];result={}
for name,change in [('baseline',None),*faults.items()]:
 code=source
 if change:
  old,new=change;assert code.count(old)==1;code=code.replace(old,new)
 p=a.output/(name+'.v');p.write_text(code);image=a.output/(name+'.vvp')
 for phase,cmd in [('compile',[a.icarus_bin/'iverilog.exe','-g2012','-s','tb_mac_half_output','-o',image,p,ref,root/'sim/gtp_apm_e2_perf_sim.v',tb]),('run',[a.icarus_bin/'vvp.exe',image])]:
  x=subprocess.run(list(map(str,cmd)),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120);log=a.output/(name+'-'+phase+'.log');log.write_bytes(x.stdout)
  if phase=='compile':assert x.returncode==0,x.stdout[-1500:]
  elif name=='baseline':assert x.returncode==0 and b'HALF_FAULT_BASELINE_PASS' in x.stdout,x.stdout[-1500:]
  else:assert x.returncode!=0 and (b'output mismatch id=64' in x.stdout or name=='second_half_wrong_output_offset' and b'duplicate/out-of-range write' in x.stdout),x.stdout[-1500:]
 result[name]=dict(exit_code=x.returncode,log_sha256=sha(log))
assert sha(original)==digest
(a.output/'result.json').write_text(json.dumps(dict(status='HALF_OUTPUT_THREE_FUNCTIONAL_FAULT_REJECTIONS_PASS_NOT_STA',source_sha256=digest,cases=result),indent=2)+'\n')
print('HALF_OUTPUT_THREE_FUNCTIONAL_FAULT_REJECTIONS_PASS_NOT_STA')
