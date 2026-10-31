"""Reject stale/mismatched SD and timing identities before any board access."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import argparse,json
import board_integrated60_trial as board

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    kit=board.R/'build/integrated-stream-sd-kit-01'
    writes=board.R/'build/integrated-stream-sd-write-01'
    check=lambda:board.preflight(kit,writes,True,True,True)
    _,baseline=check();assert baseline['functional_trial_sta_failed'] and baseline['software_sd_compatibility']['unchanged_hardware_inputs']==406
    actual_read=board.read;passed=['actual_candidate_and_readback_compatible_406_inputs']
    cases=[
        ('false_STA_pass_rejected','manifest.json','candidate',lambda d:d.update(sta_pass=True)),
        ('wrong_CPU_frequency_rejected','manifest.json','sd',lambda d:d.update(cpu_hz=75000000)),
        ('wrong_system_frequency_rejected','manifest.json','sd',lambda d:d.update(sys_hz=50000000)),
        ('wrong_clock_binding_rejected','manifest.json','sd',lambda d:d.update(clock_sha256='0'*64)),
        ('stale_original_bit_binding_rejected','manifest.json','sd',lambda d:d.update(candidate_manifest_sha256='0'*64)),
        ('changed_rootfs_bytes_rejected','manifest.json','sd',lambda d:d['sd_root_files']['rootfs.cpio'].update(sha256='0'*64)),
        ('failed_readback_rejected','write-result.json','write',lambda d:d.update(Status='FAILED')),
    ]
    for name,filename,kind,mutate in cases:
        def read(path):
            d=actual_read(path)
            selected=(kind=='sd' and path==kit/'manifest.json') or (kind=='candidate' and 'integrated60_linefix_trial_20261024' in str(path)) or (kind=='write' and path.name==filename)
            if selected:d=deepcopy(d);mutate(d)
            return d
        try:
            with patch.object(board,'read',side_effect=read):check()
        except (AssertionError,KeyError):passed.append(name)
        else:raise AssertionError('Unsafe trial fixture accepted: '+name)
    result=dict(status='JOINT60_ACTUAL_PREFLIGHT_AND_SEVEN_IDENTITY_FAULTS_REJECTED_NO_BOARD_ACCESS',checks=passed,
        source_sha256={p.name:board.sha(p) for p in [Path(__file__),board.R/'scripts/board_integrated60_trial.py']},board=False,flash=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
