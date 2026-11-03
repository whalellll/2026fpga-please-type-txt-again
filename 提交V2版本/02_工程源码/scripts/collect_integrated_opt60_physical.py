"""Preserve full accepted native reports and the candidate bit; not a release."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import gzip
import json
import shutil
import subprocess
import sys

from board_integrated_opt60 import ROOT, preflight, sha
from report_pikafish_resources import read as resource_counts
from vision32_resource_contract import vision32_resource_contract
from pikafish_dedicated_resource_contract import pikafish_dedicated_resource_contract


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-root', type=Path, required=True)
    ap.add_argument('--expected-commit', required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--evidence', type=Path, required=True)
    a = ap.parse_args()
    native = a.native_root.resolve()
    bit, checked = preflight(native, a.expected_commit)
    assert not a.candidate.exists() and not a.evidence.exists()
    a.candidate.mkdir(parents=True)
    a.evidence.mkdir(parents=True)
    subprocess.run([sys.executable, str(ROOT/'scripts/report_pikafish_physical.py'),
                    '--native-root', str(native), '--output', str(a.evidence/'physical-summary.json')],
                   check=True, timeout=120)
    summary = json.loads((a.evidence/'physical-summary.json').read_text())
    assert summary['summary_row_count'] == 116 and not summary['violations']
    vm = (native/'pds/synthesize/soc_top_syn.vm').read_text()
    snr = (native/'pds/synthesize/soc_top.snr').read_text()
    resources = dict(whole_chip=resource_counts(native/'pds/synthesize/soc_top.snr')['total'],
                     vision=vision32_resource_contract(vm, snr),
                     retained=pikafish_dedicated_resource_contract(
                         vm, snr, (native/'rtl/soc/soc_top.v').read_text()))
    shutil.copyfile(bit, a.candidate/'soc_top.sbit')
    assert sha(bit) == sha(a.candidate/'soc_top.sbit')
    for name, source in {
        'physical-launch.json': native/'physical-launch.json',
        'build_snapshot.json': native/'pds/build_snapshot.json',
        'build_evidence.json': native/'artifacts/build_evidence.json',
        'pnr-history.json': native/'pnr-history.json',
    }.items():
        shutil.copyfile(source, a.evidence/name)
        assert sha(source) == sha(a.evidence/name)
    for rel in ['report_timing/soc_top.rtr', 'report_timing/rtr.db', 'synthesize/soc_top.snr']:
        source = native/'pds'/rel
        target = a.evidence/(source.name+'.gz')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
        assert gzip.decompress(target.read_bytes()) == source.read_bytes()
    result = dict(checked, status='INTEGRATED_OPT60_FULL_NATIVE_STA_PASS_NOT_BOARD',
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  bitstream=dict(path='soc_top.sbit', bytes=bit.stat().st_size, sha256=sha(bit)),
                  resources=resources, sta_focus=summary['focus'],
                  evidence_root=a.evidence.resolve().relative_to(ROOT).as_posix(),
                  evidence_sha256={p.name:sha(p) for p in a.evidence.iterdir()},
                  board=False, sd=False, flash=False, pushed=False, formal_delivery=False)
    text = json.dumps(result, indent=2)+'\n'
    (a.candidate/'manifest.json').write_text(text)
    (a.evidence/'summary.json').write_text(text)
    print(result['status'], result['bitstream']['sha256'])


if __name__ == '__main__':
    main()
