"""Read-only expanded DDR failure paths from a completed, unchanged PnR DB."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from microarch_timing_tool import parse_report

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    native, out = a.native_root.resolve(), a.output.resolve()
    launch = json.loads((native/'physical-launch.json').read_text(encoding='utf-8-sig'))
    assert launch['status'] == 'ROUTED_STA_FAILED_NOT_BOARD', launch['status']
    assert not out.exists()
    snapshot = json.loads((native/'pds/build_snapshot.json').read_text(encoding='utf-8-sig'))
    assert snapshot['run_id'] == launch['run_id']
    originals = [native/'pds'/p for p in ['place_route/soc_top_pnr.adf',
                  'report_timing/soc_top.rtr', 'report_timing/rtr.db',
                  'soc.fdc', 'ddr3_test.rcf']]
    before = {p.as_posix():sha(p) for p in originals}
    tables = {t.get('id'):t for t in ET.parse(originals[2]).getroot().findall('table')}
    rows = [[(v.text or '').strip() for v in r.findall('data')]
            for r in tables['report_timing_slow_setup'].findall('row')]
    row = next(r for r in rows if r[:2] == ['ddrphy_sysclk', 'phy_dq_sysclk_1'])
    expected = int(row[4])
    assert expected > 0 and float(row[2]) < 0
    out.mkdir(parents=True)
    for name in ['soc.fdc', 'ddr3_test.rcf']:
        shutil.copyfile(native/'pds'/name, out/name)
    script = out/'expanded.tcl'
    script.write_text('set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676\n'
                      'add_constraint "soc.fdc"\nadd_constraint "ddr3_test.rcf"\n'
                      f'report_timing -force_to_run -input_db_file "{originals[0].as_posix()}" '
                      f'-delay_type max -nworst 1 -max_path {max(100,expected+4)} '
                      '-slack_less_than 0 -clock_group_limit {phy_dq_sysclk_1} '
                      '-report_max_skew -report_exception TRUE\n')
    assert not re.search(r'(?m)^\s*(pnr|dev_map|synthesize|gen_bit_stream)\b', script.read_text())
    command = ['G:/fpga/PDS_2022.2-SP6.4/bin/pds_shell.exe', '-file', str(script)]
    result = dict(status='RUNNING_READ_ONLY_DDR_DIAGNOSTIC', owner_pid=os.getpid(),
                  started_utc=datetime.now(timezone.utc).isoformat(), command=command,
                  formal_run_id=snapshot['run_id'], original_files_sha256=before,
                  expected_failed_endpoints=expected, script_sha256=sha(script),
                  controller_sha256=sha(Path(__file__)), scope='Read-only diagnostic; formal STA remains failed')
    save = lambda: (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    save()
    try:
        with (out/'native.log').open('xb') as log:
            child = subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            result['child_pid'] = child.pid
            save()
            try:
                code = child.wait(timeout=600)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'],
                               capture_output=True, timeout=30)
                raise
        assert code == 0 and not re.search(rb'(?m)^\s*E:', (out/'native.log').read_bytes())
        paths = [p for p in parse_report((out/'report_timing/soc_top.rtr').read_text(), 'phy_dq_sysclk_1')
                 if p['slack_ns'] < 0 and p['delay_type'] == 'max']
        assert len(paths) == expected and min(p['slack_ns'] for p in paths) == float(row[2])
        result.update(status='ALL_FAILED_DDR_ENDPOINTS_EXPANDED_FORMAL_STA_REMAINS_FAILED', paths=paths)
        for name in ['soc_top.rtr', 'rtr.db']:
            p = out/'report_timing'/name
            target = out/(name+'.gz')
            target.write_bytes(gzip.compress(p.read_bytes(), mtime=0))
            assert gzip.decompress(target.read_bytes()) == p.read_bytes()
    except Exception as error:
        result.update(status='READ_ONLY_DDR_DIAGNOSTIC_FAILED_PRESERVED', error=repr(error))
        raise
    finally:
        result['original_files_unchanged'] = all(sha(Path(p)) == h for p,h in before.items())
        result['completed_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        assert result['original_files_unchanged'], 'Formal failed reports or DB changed'
    print(result['status'])


if __name__ == '__main__':
    main()
