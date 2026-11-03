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
ap.add_argument('--timeout-seconds', type=int, default=600)
ap.add_argument('--profile', choices=['all','full','word'], default='all')
a = ap.parse_args()
if not 10 <= a.timeout_seconds <= 3600:
    ap.error('timeout-seconds must be between10 and3600')
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
oracle = a.root/'sim/reference/mac_pe_hold_reference.v.gz'
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
bench = a.root/'sim/tb_mac_pe_hold.sv'
model = a.root/'sim/gtp_apm_e2_perf_sim.v'
record = {'status':'RUNNING', 'scope':'RTL equivalence, cycles and consumer lifetimes only; no STA or board claim.',
          'requested_profile':a.profile,'host_timeout_seconds':a.timeout_seconds,'platform':os.name,
          'core_sha256':hashlib.sha256(core.read_bytes()).hexdigest(),
          'oracle':meta, 'sources':{str(q.relative_to(a.root)):hashlib.sha256(q.read_bytes()).hexdigest()
                                  for q in [bench,model]}, 'profiles':{}}
receipt = a.output/'result.json'
def save(): receipt.write_text(json.dumps(record, indent=2)+'\n')
save()
for bank in (['full','word'] if a.profile == 'all' else [a.profile]):
    image = a.output/(bank+'.vvp')
    defines = ['-DWORD_BIAS'] if bank == 'word' else []
    commands = [[iv,'-g2012',*defines,'-s','tb_mac_pe_hold','-o',str(image),
                 str(core),str(reference),str(model),str(bench)], [vvp,str(image)]]
    for phase,command in zip(['compile','run'],commands):
        result = subprocess.run(command,cwd=a.root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=a.timeout_seconds)
        (a.output/(bank+'-'+phase+'.log')).write_bytes(result.stdout)
        output = result.stdout.decode(errors='replace')
        assert result.returncode == 0 and not re.search(r'warning:|FATAL:|ERROR:', output), output[-2500:]
    cases = re.findall(r'MAC_PE_HOLD_CASE_PASS id=(\d+).*candidate=(\d+) reference=(\d+) saved=0', output)
    assert len(cases) == 64 and [int(x[0]) for x in cases] == list(range(64))
    assert all(x[1] == x[2] for x in cases)
    summary = re.search(r'MAC_PE_HOLD_PASS cases=64 reset_phases=11 words=(\d+) candidate=(\d+) reference=(\d+)', output)
    assert summary and summary[2] == summary[3]
    record['profiles'][bank] = {'cases':64,'reset_phases':11,'words':int(summary[1]),
                                'candidate_cycles':int(summary[2]),'reference_cycles':int(summary[3])}
    save()
record['status'] = 'MAC_PE_HOLD_DIFFERENTIAL_PASS' if a.profile == 'all' else 'MAC_PE_HOLD_TARGETED_PROFILE_PASS'
save()
if a.profile == 'all':
    print('MAC_PE_HOLD_DIFFERENTIAL_PASS bank_profiles=2 cases=128 reset_phases=22')
else:
    print('MAC_PE_HOLD_TARGETED_PROFILE_PASS profile='+a.profile+' cases=64 reset_phases=11; not full-suite acceptance')
