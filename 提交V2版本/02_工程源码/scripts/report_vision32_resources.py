"""Bind native whole-chip counts, PE lane retention and unchanged subsystems."""
from pathlib import Path
import argparse
import hashlib
import json
from report_pikafish_resources import read
from vision32_resource_contract import vision32_resource_contract
from pikafish_dedicated_resource_contract import pikafish_dedicated_resource_contract


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-root', required=True, type=Path)
    ap.add_argument('--baseline-root', default=Path('G:/pfdsyn2'), type=Path)
    ap.add_argument('--output', required=True, type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    n, b = a.native_root.resolve(), a.baseline_root.resolve()
    receipt = json.loads((n/'resource-evidence/result.json').read_text(encoding='utf-8-sig'))
    assert receipt['status'] == 'SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
    for rel, h in receipt['inputs'].items():
        assert sha(n/rel) == h and sha(root/rel) == h, ('Frozen source differs', rel)
    old_receipt = json.loads((b/'resource-evidence/result.json').read_text(encoding='utf-8-sig'))
    changed = [p for p, h in old_receipt['inputs'].items() if p in receipt['inputs'] and h != receipt['inputs'][p]]
    allowed = {'pds/soc.tcl', 'pds/soc_gui.pds', 'rtl/soc/soc_top.v', 'rtl/mac_accel/mac_accel_ddr_kernel_top.v',
               'scripts/audit_cpu_ads.py', 'scripts/build_snapshot.ps1', 'scripts/audit_cpu_dedicated_pll_ads.py',
               'scripts/build_cpu_ads_gate.ps1'}
    assert set(changed) <= allowed, ('Unreviewed baseline change', sorted(set(changed)-allowed))
    snr = n/'pds/synthesize/soc_top.snr'
    vm = n/'pds/synthesize/soc_top_syn.vm'
    text, report = vm.read_text(), snr.read_text()
    vision = vision32_resource_contract(text, report)
    protected = pikafish_dedicated_resource_contract(text, report, (n/'rtl/soc/soc_top.v').read_text())
    old, new = read(b/'pds/synthesize/soc_top.snr'), read(snr)
    result = dict(status='VISION32_NATIVE_RESOURCE_AND_RETENTION_PASS_NOT_STA_OR_BOARD',
                  native_root=n.as_posix(), source_root=root.as_posix(), frozen_inputs=len(receipt['inputs']),
                  frozen_source_verified=True, baseline_changed_inputs=changed,
                  vision=vision, dedicated_and_voice=protected,
                  whole_chip=new['total'], baseline=old['total'],
                  delta={k:new['total'][k]-v for k,v in old['total'].items()},
                  native_snr_sha256=sha(snr), native_vm_sha256=sha(vm),
                  native_receipt_sha256=sha(n/'resource-evidence/result.json'))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status', 'vision', 'whole_chip', 'delta')}))


if __name__ == '__main__':
    main()
