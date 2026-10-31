"""Finite off-board integration regressions; no programming or device access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from picture_workspace import ROOT, workspace_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--only', help='Comma-separated case names; keep earlier passing evidence')
    a = p.parse_args()
    out = workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    cases = [
        ('gui', 'test_gui_fine.py', [], 240),
        ('main-loop', 'check_xinyi_main_loop.py', [], 180),
        ('clock', 'test_main75_boot_sync.py', ['--source-root', str(ROOT)], 240),
        ('feature-host', 'test_pikafish_feature_updates.py', [], 180),
        ('feature-rv32', 'test_pikafish_feature_updates.py', ['--rv32'], 180),
        ('feature-fallback', 'test_pikafish_feature_fallback.py', [], 180),
        ('v321-interface', 'check_xinyi_v321_interface.py', [], 300),
    ]
    if a.only:
        selected = set(a.only.split(','))
        assert selected <= {c[0] for c in cases}
        cases = [c for c in cases if c[0] in selected]
    result = dict(status='RUNNING_OR_FAILED_PRESERVED', hardware_used=False, checks=[],
                  selected_cases=[c[0] for c in cases], complete_suite=not bool(a.only))
    for name, script, extra, seconds in cases:
        # Pass lexical junction paths to tools which validate their build boundary.
        target = a.output.absolute()/name
        command = [sys.executable, '-X', 'utf8', '-B', str(ROOT/'scripts'/script),
                   '--output', str(target), *extra]
        with (out/(name+'.log')).open('xb') as log:
            r = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=seconds+30)
        result['checks'].append(dict(name=name, command=command, exit=r.returncode,
            log_sha256=hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest()))
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        assert r.returncode == 0, (name,(out/(name+'.log')).read_text(errors='replace')[-2200:])
        print(name+' PASS',flush=True)
    result['status'] = 'MERGED_SELECTED_OFFLINE_CHECKS_PASS_NOT_BOARD'
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    main()
