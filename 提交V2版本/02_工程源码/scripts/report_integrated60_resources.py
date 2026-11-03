"""Verify current combined hardware against frozen native resource evidence."""
from pathlib import Path
import argparse,hashlib,json
from report_pikafish_resources import read
from pikafish_dedicated_resource_contract import pikafish_dedicated_resource_contract
from vision32_resource_contract import vision32_resource_contract
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--native-root',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
n=a.native_root.resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=json.loads((n/'resource-evidence/result.json').read_text(encoding='utf-8-sig'))
assert receipt['status']=='SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
changes=[]
for rel,h in receipt['inputs'].items():
 assert sha(n/rel)==h,('Native frozen input changed',rel)
 if sha(R/rel)!=h:
  if rel=='scripts/vision32_cache_contract.py':
   proof=json.loads((R/'build/integrated-linefix-cache-04.json').read_text())
   assert proof['status']=='VISION32_NATIVE_CACHE_PORTS_CAPACITY_DECODERS_AND_MUTATIONS_PASS_NOT_STA'
   assert proof['native_vm_sha256']==sha(n/'pds/synthesize/soc_top_syn.vm')
   assert proof['checker_sha256']==sha(R/rel) and proof['rejected_mutations']==7
   assert proof['positive']['native_read_boundary']['hierarchy_bound']
   scope='Current native cache checker proves accepted-read producer and actual hierarchy;7 native faults rejected. Frozen synthesis inputs/RTL remain unchanged.'
  else:
   assert rel in ['scripts/build_linux_mac_kernel.ps1','scripts/build_picture_new_interface.py','scripts/build_integrated60_boot.py','scripts/build_integrated60_pnr.ps1'],('Unreviewed source difference',rel)
   scope='Software helper or physical launcher offline-gate refresh only; synthesis logic/constraints/checkers must match'
  changes.append(dict(path=rel,frozen=h,current=sha(R/rel),scope=scope))
vm=n/'pds/synthesize/soc_top_syn.vm';snr=n/'pds/synthesize/soc_top.snr'
text,report=vm.read_text(),snr.read_text();top=(n/'rtl/soc/soc_top.v').read_text()
protected=pikafish_dedicated_resource_contract(text,report,top)
vision=vision32_resource_contract(text,report)
counts=read(snr)['total'];assert counts['drm36k']<=140 and counts['apm']<=195
record=dict(status='INTEGRATED60_NATIVE_RESOURCES_AND_RETAINED_ENGINES_PASS_NOT_STA_OR_BOARD',whole_chip=counts,vision=vision,pikafish_voice=protected,frozen_inputs=len(receipt['inputs']),source_software_helper_differences=changes,native_snr_sha256=sha(snr),native_vm_sha256=sha(vm),native_receipt_sha256=sha(n/'resource-evidence/result.json'))
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(status=record['status'],whole_chip=counts)))
