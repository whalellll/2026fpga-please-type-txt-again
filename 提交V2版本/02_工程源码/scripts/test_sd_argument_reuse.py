"""Cycle miter against frozen SD controller: command/read/write/stream benches."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,subprocess,traceback,shutil
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--baseline',action='store_true');ap.add_argument('--faults',action='store_true');a=ap.parse_args()
root=Path(__file__).resolve().parents[1];out=a.output;out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
archive=root/'sim/reference/sd_native_mmio_p5.v.gz';manifest=json.loads(archive.with_name('sd_native_mmio_p5.json').read_text())
assert sha(archive)==manifest['gzip_sha256'];raw=gzip.decompress(archive.read_bytes());assert hashlib.sha256(raw).hexdigest()==manifest['source_sha256']
old=raw.decode().replace('\r\n','\n');source=a.source.read_text();ref=out/'reference.v'
ref.write_text(old.replace('module sd_native_mmio #(','module sd_native_mmio_argument_reference #(',1).replace('sd_native_sector_bank','sd_native_sector_bank_argument_reference'))
assert source.count('module sd_native_mmio #(')==1
result=dict(status='RUNNING',source_sha256=sha(a.source),reference_sha256=manifest['source_sha256'],checker_sha256=sha(Path(__file__)),cases=[],negative_cases=[])
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
ports={'rdata':'[31:0]','hit':'','sd_clk':'','sd_cmd_out':'','sd_cmd_oe':'','sd_dat_out':'[3:0]','sd_dat_oe':''}
parameters=['BASE','RESET_DIV','DEBOUNCE_CYCLES','CMD_TIMEOUT_CLOCKS','DATA_TIMEOUT_CLOCKS','BUSY_TIMEOUT_CLOCKS','WRITE_TIMEOUT_CLOCKS','TX_WAIT_TIMEOUT_CYCLES']
inputs=['clk','resetn','addr','wr','wdata','wstrb','sd_cmd_in','sd_dat_in','sd_detect_n']
miter='\n'+''.join('wire '+width+' __ref_'+n+';\n' for n,width in ports.items())
miter+='sd_native_mmio_argument_reference #('+','.join('.'+n+'('+n+')' for n in parameters)+') __ref ('+','.join('.'+n+'('+n+')' for n in inputs)+','+','.join('.'+n+'(__ref_'+n+')' for n in ports)+');\n'
miter+='integer __checks=0;always @(negedge clk)begin\n__checks=__checks+1;\n'
miter+='if ({'+','.join(ports)+'} !== {'+','.join('__ref_'+n for n in ports)+'}) $fatal(1,"SD_ARGUMENT_INTERFACE_MISMATCH check=%0d state=%0d",__checks,state);\n'
state=['state','data_state','busy','done','error_sticky','cmd_crc','cmd_crc_count','data_timeout_count','tx_wait_count','response_shift','blocks_done','tx0_full','tx1_full','data_word_build']
miter+='if ({'+','.join(state)+'} !== {'+','.join('__ref.'+n for n in state)+'}) $fatal(1,"SD_ARGUMENT_PROTOCOL_MISMATCH check=%0d",__checks);\n'
miter+='if ((state==ST_CMD_TX) && (cmd_tx_shift !== __ref.cmd_tx_shift)) $fatal(1,"SD_ARGUMENT_TX_WORD_MISMATCH");\n'
if not a.baseline:
 miter+='if ((state==ST_CMD_CRC) && (cmd_tx_shift[47:8] !== {2\'b01,__ref.cmd_index_latched,__ref.cmd_arg_latched})) $fatal(1,"SD_ARGUMENT_HEADER_RELATION_MISMATCH");\n'
miter+='end\nfinal $display("SD_ARGUMENT_CYCLE_MITER_PASS checks=%0d",__checks);\n'
iv=shutil.which('iverilog') or 'G:/fpga/workspace/tools/msys64/ucrt64/bin/iverilog.exe';vvp=str(Path(iv).with_name('vvp.exe' if os.name=='nt' else 'vvp'))
env=dict(os.environ);env['PATH']=str(Path(iv).parent)+os.pathsep+env['PATH']
benches=['tb_sd_native_mmio','tb_sd_native_write','tb_sd_native_multiblock']
def run(label,rtl,bench):
 folder=out/label;folder.mkdir();p=folder/'candidate.v';p.write_text(rtl.replace('\nendmodule','\n'+miter+'endmodule',1))
 tb=(root/'sim'/(bench+'.sv')).read_text()
 # Mirror the six explicit reachable-state injections in the original MMIO
 # collision test. All other original stimulus and pin/card checks are intact.
 tb=re.sub(r'(dut\.(\w+)\s*=\s*(?!=)[^;]+;)',lambda m:m[1]+m[1].replace('dut.','dut.__ref.'),tb)
 test=folder/(bench+'.sv');test.write_text(tb);image=folder/'test.vvp'
 command=[iv,'-g2012','-s',bench,'-o',str(image),str(p),str(ref),str(test)]
 proc=subprocess.run(command,capture_output=True,timeout=120,env=env);(folder/'compile.log').write_bytes(proc.stdout+proc.stderr);assert proc.returncode==0,(label,proc.stderr[-1800:])
 proc=subprocess.run([vvp,str(image)],capture_output=True,timeout=180,env=env);log=folder/'run.log';log.write_bytes(proc.stdout+proc.stderr)
 return proc,log
try:
 for bench in benches:
  proc,log=run(bench,source,bench);assert proc.returncode==0,(bench,proc.stdout[-2000:],proc.stderr[-1000:])
  count=re.search(rb'SD_ARGUMENT_CYCLE_MITER_PASS checks=(\d+)',proc.stdout);assert count and int(count[1])>1000
  assert re.search(rb'SD_NATIVE_.*PASS',proc.stdout)
  result['cases'].append(dict(bench=bench,cycles=int(count[1]),log_sha256=sha(log)));save()
 if a.faults:
  mutants=[('wrong-header-argument',source.replace("wdata[5:0], argument};","wdata[5:0], (argument ^ 32'b1)};",1)),('wrong-crc',source.replace("{command_crc_next, 1'b1}","{(command_crc_next ^ 7'b1), 1'b1}",1)),('wrong-auto-cmd12',source.replace("cmd_tx_shift[47:8] <= {2'b01, 6'd12, 32'd0}","cmd_tx_shift[47:8] <= {2'b01, 6'd12, 32'd1}"))]
  for label,rtl in mutants:
   assert rtl!=source;proc,log=run(label,rtl,benches[0])
   assert proc.returncode!=0 and re.search(rb'SD_ARGUMENT_\w+MISMATCH',proc.stdout+proc.stderr),(label,proc.returncode,proc.stdout[-2000:])
   result['negative_cases'].append(dict(label=label,rejected=True,log_sha256=sha(log)));save()
 result['status']='SD_ARGUMENT_THREE_FULL_PROTOCOL_CYCLE_MITERS_PASS_NOT_NATIVE_OR_BOARD'
except Exception:result.update(status='FAILED_SD_ARGUMENT_CYCLE_MITER_PRESERVED',error=traceback.format_exc());raise
finally:save();print(result['status'],flush=True)
