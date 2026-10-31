#!/usr/bin/env python3
"""Check dynamic FDC/CCR identity using preserved native data and explicit mutations.

No synthesis is run. Mutated reports are in-memory negative/positive checker
fixtures, never archived as new ADS evidence.
"""
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('cdc_audit', root / 'pds/audit_cpu_sys_cdc_ads.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    native = root / 'docs/validation/frequency-search/div15-PASS-6e934e9f84094159bff9a8870e260e8e/raw'
    fdc = (native / 'pds/soc.fdc').read_text()
    ccr = (native / 'pds/constraint_check/constraint_check.ccr').read_text()
    vm = (native / 'pds/synthesize/soc_top_syn.vm').read_text()
    records = audit.mapped_fifo_audit(vm)
    payloads, _ = audit.mapped_payload_ram_audit(vm, fdc)
    syncs, _, _ = audit.mapped_sync_first_stage_audit(vm, fdc)
    assert audit.mapped_constraint_propagation_audit(vm, fdc) == 300
    audit.constraint_audit(ccr, fdc, records, payloads, syncs)
    checks = ['native_div15_ads_and_ccr_unchanged_pass']
    for period, limit in [('15.712682','14.912'),('14.590348','13.79'),('13.468013','12.668'),('14.109347','13.309')]:
        candidate = fdc.replace('16.835017', period).replace(' 16.0\n', ' ' + limit + '\n')
        assert audit.reviewed_cdc_limit(candidate) == limit
        candidate_ccr = ccr.replace('16.835017', period).replace(' 16.0\n', ' ' + limit + '\n')
        audit.constraint_audit(candidate_ccr, candidate, records, payloads, syncs)
        checks.append('tightened_' + limit + 'ns_fixture_pass')
        try:
            audit.constraint_audit(ccr, candidate, records, payloads, syncs)
        except audit.AuditError as error:
            assert 'report did not register' in str(error), str(error)
            checks.append('old_ccr_rejected_at_' + limit + 'ns')
        else:
            raise AssertionError('old CCR accepted')
    unsafe = fdc.replace('16.835017','15.712682')
    try:
        audit.constraint_audit(ccr, unsafe, records, payloads, syncs)
    except audit.AuditError as error:
        assert 'directive missing' in str(error), str(error)
        checks.append('unsafe_16ns_div14_fdc_rejected')
    else:
        raise AssertionError('unsafe CDC budget accepted')
    result = {'schema':1,'status':'PASS','kind':'native-ads-ccr-mutation-tests-not-new-hardware-evidence','checks':checks}
    if args.report:
        args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('CLOCK_CDC_POLICY_TEST_PASS checks=%d' % len(checks))


if __name__ == '__main__':
    main()
