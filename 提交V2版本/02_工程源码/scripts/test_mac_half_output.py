#!/usr/bin/env python3
"""Compare PE-result reuse with the frozen pre-change core on every cycle."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
ap.add_argument('--output', type=Path, required=True)
ap.add_argument('--icarus-bin', type=Path)
ap.add_argument('--profile', type=int, choices=[1,2], default=1)
a = ap.parse_args()
a.root = a.root.resolve()
a.output = a.output.resolve()
assert not a.output.exists()
a.output.mkdir(parents=True)
suffix = '.exe' if os.name == 'nt' else ''
iv = str(a.icarus_bin/('iverilog'+suffix)) if a.icarus_bin else shutil.which('iverilog')
vvp = str(a.icarus_bin/('vvp'+suffix)) if a.icarus_bin else shutil.which('vvp')
assert iv and vvp, 'Icarus is required'
env = dict(os.environ)
if a.icarus_bin:
    env['PATH'] = str(a.icarus_bin)+os.pathsep+env['PATH']
oracle = a.root/'sim/reference/mac_half_output_p8.v.gz'
meta = json.loads(oracle.with_suffix('.json').read_text())
raw = gzip.decompress(oracle.read_bytes())
assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
assert hashlib.sha256(oracle.read_bytes()).hexdigest() == meta['gzip_sha256']
text = raw.decode()
names = re.findall(r'^module\s+(\w+)', text, re.M)
text = re.sub(r'\b(?:'+'|'.join(map(re.escape,names))+r')\b', lambda m:'Baseline'+m[0], text)
reference = a.output/'reference.v'
reference.write_text(text)
core = a.root/'rtl/mac_accel/MacAccelCore.v'
bench = a.root/'sim/tb_mac_half_output.sv'
model = a.root/'sim/gtp_apm_e2_perf_sim.v'
record = {'status':'RUNNING', 'scope':'Transaction/output equivalence with measured increased cycles, unchanged host packing; not STA or board.',
          'output_profile':a.profile,
          'core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),
          'oracle':meta, 'sources':{str(q.relative_to(a.root)):hashlib.sha256(q.read_bytes()).hexdigest()
                                  for q in [bench,model]}, 'profiles':{}}
receipt = a.output/'result.json'
def save(): receipt.write_text(json.dumps(record, indent=2)+'\n')
save()
for bank in ['full','word']:
    image = a.output/(bank+'.vvp')
    defines = ['-DWORD_BIAS'] if bank == 'word' else []
    commands = [[iv,'-g2012',*defines,'-s','tb_mac_half_output',f'-Ptb_mac_half_output.OUTPUT_PROFILE={a.profile}','-o',str(image),
                 str(core),str(reference),str(model),str(bench)], [vvp,str(image)]]
    for phase,command in zip(['compile','run'],commands):
        result = subprocess.run(command,cwd=a.root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        (a.output/(bank+'-'+phase+'.log')).write_bytes(result.stdout)
        output = result.stdout.decode(errors='replace')
        assert result.returncode == 0 and not re.search(r'warning:|FATAL:|ERROR:', output), output[-2500:]
    cases = re.findall(r'MAC_HALF_OUTPUT_CASE_PASS id=(\d+).*candidate=(\d+) reference=(\d+) saved=0', output)
    assert len(cases) == 65 and [int(x[0]) for x in cases] == list(range(65))
    assert all(int(x[1]) >= int(x[2]) for x in cases)
    summary = re.search(r'MAC_HALF_OUTPUT_PASS cases=65 reset_phases=11 words=(\d+) candidate=(\d+) reference=(\d+)', output)
    assert summary and int(summary[2]) > int(summary[3])
    record['profiles'][bank] = {'cases':65,'reset_phases':11,'words':int(summary[1]),
                                'candidate_cycles':int(summary[2]),'reference_cycles':int(summary[3])}
    save()
record['status'] = 'MAC_QUARTER_OUTPUT_DIFFERENTIAL_PASS' if a.profile==2 else 'MAC_HALF_OUTPUT_DIFFERENTIAL_PASS'
save()
print(record['status']+' bank_profiles=2 cases=130 reset_phases=22')
