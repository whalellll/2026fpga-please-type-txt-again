"""Fault tests for the exact functional-trial gate; no hardware access."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
from check_cpu60_functional_trial import verify

def run(root, trial, output):
    if output.exists(): raise ValueError('Preserve prior test output')
    output.mkdir(parents=True)
    copy=output/'fault-fixture'
    shutil.copytree(trial,copy)
    image=copy/'soc_top.sbit'
    tests=[]
    result=verify(root,trial,trial/'soc_top.sbit')
    tests.append('exact_original_source_and_report_pass')
    def reject(name, path, change):
        old=path.read_bytes()
        path.write_bytes(change(old))
        try:
            try: verify(root,copy,image)
            except (ValueError,FileNotFoundError): tests.append(name)
            else: raise AssertionError('Unsafe fixture accepted: '+name)
        finally: path.write_bytes(old)
    reject('changed_bitstream_rejected',image,lambda b:b[:100]+bytes([b[100]^1])+b[101:])
    reject('changed_manifest_rejected',copy/'manifest.json',lambda b:b+b' ')
    reject('changed_original_report_rejected',copy/'archive/rtr.db',lambda b:b+b' ')
    reject('changed_snapshot_input_rejected',copy/'source/config/clocks.json',lambda b:b+b' ')
    try: verify(root,trial,root/'artifacts/soc_top.sbit')
    except ValueError: tests.append('old_cpu80_image_rejected')
    else: raise AssertionError('CPU80 image accepted')
    record=dict(status='PASS',hardware_access=False,checks=tests,identity=result,
        source_sha256={str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          str(root/'scripts/check_cpu60_functional_trial.py'):hashlib.sha256((root/'scripts/check_cpu60_functional_trial.py').read_bytes()).hexdigest()})
    (output/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('CPU60_FUNCTIONAL_TRIAL_IDENTITY_AND_FIVE_NEGATIVES_PASS',len(tests))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--trial-directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root.resolve(),a.trial_directory.resolve(),a.output.resolve())
