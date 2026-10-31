"""Fault-test the actual native PMA page export without weakening the CPU oracle."""
from pathlib import Path
import argparse,hashlib,json,re
import audit_pikafish_batch60_ads as batch
import audit_cpu_ads as original
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--netlist',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 raw=a.netlist.read_bytes();source=raw.decode();proof=batch.prove_boundary(source);faults={}
 def changed_cell(module,instance,transform):
  pattern=r'(?ms)^module '+re.escape(module)+r'\b.*?^endmodule'
  m=re.search(pattern,source);assert m
  body=m[0]
  cell=r"(\.INIT\(64'b)([01]{64})(\)\)\s*\n\s*\\?"+re.escape(instance)+r'\s*\()'
  found=list(re.finditer(cell,body));assert len(found)==1,(module,instance)
  n=found[0];bits=transform(n[2]);assert bits!=n[2]
  new=body[:n.start(2)]+bits+body[n.end(2):]
  return source[:m.start()]+new+source[m.end():],dict(module=module,instance=instance,old_init=n[2],new_init=bits)
 for name,module,instance,transform in [
  ('producer_stuck_zero','PmaMmu',proof['producer']['instance'],lambda b:'0'*64),
  ('producer_spurious_fault','PmaMmu',proof['producer']['instance'],lambda b:b[:-1]+('0' if b[-1]=='1' else '1')),
  ('consumer_stuck_zero','CoreFrontend',proof['consumer']['instance'],lambda b:'0'*64),
  # I5 is tied high: mutate reachable INIT bit32, not unreachable bit0.
  ('consumer_spurious_page_fault','CoreFrontend',proof['consumer']['instance'],lambda b:b[:31]+('0' if b[31]=='1' else '1')+b[32:]),
 ]:
  mutant,patch=changed_cell(module,instance,transform)
  try:batch.prove_boundary(mutant)
  except (AssertionError,ValueError,KeyError) as e:faults[name]=dict(rejected=True,error=type(e).__name__,patch=patch)
  else:raise AssertionError('Native fault accepted: '+name)
 # Require the actual hierarchy bridge, not just an isolated truth table.
 marker='.'+'\\'+batch.PAGE
 core=re.search(r'(?ms)^module Core\b.*?^endmodule',source);assert core
 body=core[0];assert body.count(marker)==1
 mutant=source[:core.start()]+body.replace(marker,'.\\broken_page_export',1)+source[core.end():]
 try:batch.prove_boundary(mutant)
 except (AssertionError,ValueError,KeyError) as e:faults['disconnected_hierarchy']=dict(rejected=True,error=type(e).__name__)
 else:raise AssertionError('Disconnected hierarchy accepted')
 assert hashlib.sha256(a.netlist.read_bytes()).digest()==hashlib.sha256(raw).digest()
 report=dict(status='BATCH60_NATIVE_PMA_EXPORT_FAULTS_PASS_NOT_STA_OR_BOARD',cases=proof['cases'],faults=faults,
  netlist=str(a.netlist.resolve()),netlist_sha256=hashlib.sha256(raw).hexdigest(),adapter_sha256=hashlib.sha256(Path(batch.__file__).read_bytes()).hexdigest(),test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
if __name__=='__main__':main()
