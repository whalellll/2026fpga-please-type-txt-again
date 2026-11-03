"""Negative identity checks only; never opens a device or changes pinned files."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import check_main_p3_published as gate

ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists()
    good=gate.check(ROOT,ROOT/'artifacts/soc_top.sbit')
    assert good['frozen_inputs']==495 and not good['formal_release'] and not good['native_database_replay_complete']
    tests=[];digest=gate.digest
    for relative in ['artifacts/soc_top.sbit','artifacts/INTEGRATED_OPT60_MAIN.json',
        'artifacts/build_snapshot.json','artifacts/build_evidence.json','rtl/cpu/CoreTop.sv',
        'pds/soc.fdc','scripts/build_snapshot.ps1','scripts/timing_scope_pixel_grid.ps1',
        'scripts/build_xinyi_cpu60_loader.py']:
        target=ROOT/relative
        def changed(path):return '0'*64 if path==target else digest(path)
        try:
            with patch.object(gate,'digest',side_effect=changed):gate.check(ROOT,ROOT/'artifacts/soc_top.sbit')
        except ValueError:tests.append(relative)
        else:raise AssertionError('Changed identity accepted: '+relative)
    for relative in ['artifacts/pikafish_batch60_candidate.sbit','build/foreign.sbit']:
        try:gate.check(ROOT,ROOT/relative)
        except ValueError:tests.append(relative)
        else:raise AssertionError('Foreign path accepted')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(status='MAIN_P3_PUBLISHED_IDENTITY_NEGATIVES_PASS_NOT_BOARD',
        hardware_used=False,baseline=good,negative_cases=tests),indent=2)+'\n')
    print('MAIN_P3_PUBLISHED_IDENTITY_11_NEGATIVES_PASS_NOT_BOARD')
if __name__=='__main__':main()
