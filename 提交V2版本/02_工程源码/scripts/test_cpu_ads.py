#!/usr/bin/env python3
"""Exercise the CPU ADS audit against a real netlist and four deliberate faults.

This does not run PDS or simulate hardware. Temporary mutant netlists are removed
on exit; the supplied netlist is read only. Each audit child has a finite timeout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from audit_cpu_ads import Cone, pma_output_names


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_generic_lut():
    # Z uses only the high half-table because I5 is fixed high. The unused
    # Z5 half has a self-dependency and must not be followed while checking Z.
    source = """module T ();
GTP_LUT6D #(.INIT(64'hAAAAAAAACCCCCCCC)) shared (.Z(out), .Z5(loop),
 .I0(a), .I1(loop), .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1));
GTP_DFF_R state_ff (.Q(state), .D(a), .CLK(clock), .R(1'b0));
endmodule
"""
    cone = Cone(source, 'T')
    for value in (0, 1):
        if cone.evaluate('out', {'a': value}) != value:
            raise RuntimeError('Fixed LUT6D cofactor evaluation is wrong')
    checks = ['fixed_lut6d_cofactor_values_0_and_1']
    for target, diagnostic in [('loop', 'Combinational cycle'), ('state', 'Unsupported evaluated driver')]:
        try:
            cone.evaluate(target, {'a': 0})
        except ValueError as error:
            if diagnostic not in str(error):
                raise
        else:
            raise RuntimeError('Unknown active driver/cycle was incorrectly accepted')
        checks.append('reject_active_' + target)
    return checks


def change_init(source, module, target, value):
    cell = Cone(source, module).primitive(target)
    body = re.search(r"(?ms)^module " + re.escape(module) + r"\s.*?^endmodule", source)
    pattern = (r"\b" + re.escape(cell['type']) +
               r"\s*(?:/\*.*?\*/\s*)?#\s*\((?P<params>[^;]*?)\)\s+" +
               re.escape(cell['instance']) + r"\s*\(")
    # Instance identifiers may be escaped in the Verilog text.
    pattern = pattern.replace(re.escape(cell['instance']), r"\\?" + re.escape(cell['instance']))
    matches = list(re.finditer(pattern, body.group(), flags=re.S))
    if len(matches) != 1:
        raise ValueError('Cannot uniquely identify mutant LUT: ' + target)
    params = matches[0].group('params')
    replacement, count = re.subn(r"(\.INIT\s*\(\s*)(\d+)'[bh][0-9a-fA-F_]+(\s*\))",
                                lambda m: m[1] + m[2] + "'h" + format(value, 'x') + m[3], params)
    if count != 1:
        raise ValueError('Cannot uniquely change mutant INIT: ' + target)
    begin, end = matches[0].span('params')
    begin += body.start()
    end += body.start()
    return source[:begin] + replacement + source[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 600:
        parser.error('--timeout-seconds must be in 1..600')
    runner = Path(__file__).resolve()
    audit_script = runner.with_name('audit_cpu_ads.py')
    generic_checks = check_generic_lut()
    original = args.netlist.read_bytes()
    source = original.decode('utf-8')
    hint = Cone(source, 'RsMem').primitive('scanKnownCached_0')
    pma_outputs = pma_output_names(source)
    fused_pma = pma_outputs == ('N7',)
    supervisor_pma = fused_pma and 'N23' in Cone(source, 'Lsu').drivers
    if fused_pma:
        uncached_output = 'N7'
        if supervisor_pma:
            store_lut = Cone(source, 'Lsu').primitive('N23')
            load_lut = Cone(source, 'Lsu').primitive('N972')
            if store_lut['type'] != 'GTP_LUT6' or load_lut['type'] not in ('GTP_LUT4', 'GTP_LUT6D'):
                raise ValueError('Unknown supervisor PMA consumer LUT shape; review the fixture')
        else:
            shared_lut = Cone(source, 'Lsu').primitive('N13')
            if shared_lut['type'] != 'GTP_LUT6D' or shared_lut['ports'].get('Z5') != 'N965':
                raise ValueError('Unknown fused PMA consumer LUT shape; review the fixture')
    else:
        n965_inputs = set(Cone(source, 'Lsu').primitive('N965')['ports'].values())
        uncached_outputs = set(pma_outputs) & n965_inputs
        if len(uncached_outputs) != 1:
            raise ValueError('Unknown PMA uncached-output LUT shape; review the fixture')
        uncached_output = uncached_outputs.pop()
    # Current actual LUT3: I0=uncacheable, I1=refresh, I2=valid. Turn
    # valid && !uncacheable && !refresh (0x10) into valid && !uncacheable
    # (0x50). Refuse to mutate an unknown shape rather than weaken the test.
    if supervisor_pma:
        if (hint['type'] == 'GTP_LUT6D' and hint['output'] in ('Z5', 'Z') and
                hint['ports'].get('I1') == 's0KeyRefreshA_0' and
                hint['ports'].get('I2') == 's0ValValidA_0' and
                hint['ports'].get('I4') == 'io_dataTranslationActive'):
            refresh_bit, lut_entries = 1, 32 if hint['output'] == 'Z5' else 64
        elif (hint['type'] == 'GTP_LUT6' and hint['output'] == 'Z' and
              hint['ports'].get('I0') == 's0KeyRefreshA_0' and
              hint['ports'].get('I1') == 's0ValValidA_0' and
              hint['ports'].get('I5') == 'io_dataTranslationActive'):
            refresh_bit, lut_entries = 0, 64
        elif (hint['type'] == 'GTP_LUT4' and hint['output'] == 'Z' and hint['init'] == 0x10 and
              hint['ports'].get('I1') == 's0KeyRefreshA_0' and
              hint['ports'].get('I2') == 's0ValValidA_0' and
              hint['ports'].get('I3') == 'io_dataTranslationActive'):
            refresh_bit, lut_entries = 1, 16
        elif (hint['type'] == 'GTP_LUT4' and hint['output'] == 'Z' and hint['init'] == 0x100 and
              hint['ports'].get('I0') == 'io_dataTranslationActive' and
              hint['ports'].get('I2') == 's0KeyRefreshA_0' and
              hint['ports'].get('I3') == 's0ValValidA_0'):
            refresh_bit, lut_entries = 2, 16
        elif (hint['type'] == 'GTP_LUT4' and hint['output'] == 'Z' and hint['init'] == 0x4 and
              hint['ports'].get('I0') == 's0KeyRefreshA_0' and
              hint['ports'].get('I1') == 's0ValValidA_0' and
              hint['ports'].get('I2') == 'io_dataTranslationActive' and
              hint['ports'].get('I3') == 'N11'):
            # Same validated valid && !refresh && !translation && !PMA term,
            # with the current PDS pin permutation. Mutate only refresh.
            refresh_bit, lut_entries = 0, 16
        else:
            raise ValueError('Unknown supervisor refresh LUT shape; review the fixture')
        refresh_bypass = hint['init']
        for index in range(lut_entries):
            if index & (1 << refresh_bit):
                source_bit = (hint['init'] >> (index ^ (1 << refresh_bit))) & 1
                refresh_bypass = (refresh_bypass & ~(1 << index)) | (source_bit << index)
    else:
        if (hint['type'] != 'GTP_LUT3' or hint['init'] != 0x10 or
                hint['ports'].get('I1') != 's0KeyRefreshA_0' or
                hint['ports'].get('I2') != 's0ValValidA_0'):
            raise ValueError('Unknown refresh LUT shape; review the fixture')
        refresh_bypass = 0x50
    cases = [('original', None, None),
             ('branch0_constant_zero', ('CoreFrontend', 'branch0', 0), 'Frontend mismatch'),
             ('refresh_guard_bypassed', ('RsMem', 'scanKnownCached_0', refresh_bypass), 'RsMem hint mismatch'),
             ('pma_lut_stuck_zero', ('PhysicalMemoryAttributes', uncached_output, 0),
              'PMA output LUT is constant')]
    frontend = Cone(source, 'CoreFrontend')
    if 'pdReturns_0' in frontend.drivers:
        from audit_cpu_ads import bind_registered_frontend_controls
        control=bind_registered_frontend_controls(frontend,source)
        meta_d = frontend.drivers['pdReturns_0'][0]['ports']['D']
        access_d = frontend.drivers['fcFaults[6]'][0]['ports']['D']
        page_d = frontend.drivers['fcFaults[7]'][0]['ports']['D']
        cases.extend([
            ('metadata_return_d_zero', ('CoreFrontend', meta_d, 0), 'Native D function differs'),
            ('metadata_return_selector_zero', ('CoreFrontend', control['return_selector'], 0),
             'selected metadata must be uniquely bound' if control['mode']=='folded_ras_push' else 'Return selector must be uniquely bound'),
            ('instruction_access_fault_zero', ('CoreFrontend', access_d, 0), 'PMA instruction-access mismatch'),
            ('instruction_page_fault_zero', ('CoreFrontend', page_d, 0), 'page-fault consumer disconnected'),
        ])
    if supervisor_pma:
        cases.extend([
            ('pma_atomic_decision_zero', ('Lsu', 'N23', 0),
             'Supervisor PMA atomic consumer mismatch'),
            ('pma_load_decision_zero', ('Lsu', 'N972', 0),
             'Supervisor PMA load consumer mismatch'),
        ])
        if load_lut['type'] == 'GTP_LUT6D' and 'aGo_cpy' in load_lut['ports'].values():
            cases.append(('pma_load_ago_copy_zero', ('Lsu', 'aGo_cpy', 0),
                          'Supervisor PMA load aGo copy differs'))
    elif fused_pma:
        cases.extend([
            ('pma_store_decision_zero', ('Lsu', 'N13', shared_lut['init'] & 0xffffffff),
             'PMA LSU N13 mismatch'),
            ('pma_load_decision_zero', ('Lsu', 'N965', shared_lut['init'] & ~0xffffffff),
             'PMA LSU N965 mismatch'),
        ])
    else:
        cases.append(('pma_store_decision_zero', ('Lsu', 'N13', 0),
                      'PMA LSU N13 mismatch'))
    # Validate every mutation before spending time on the positive audit.
    for _, mutation, _ in cases:
        if mutation is not None:
            change_init(source, *mutation)
    results = []
    with tempfile.TemporaryDirectory(prefix='cpu-ads-fixtures-') as temporary:
        folder = Path(temporary)
        for name, mutation, expected_error in cases:
            netlist = folder / (name + '.vm')
            netlist.write_bytes(original if mutation is None else change_init(source, *mutation).encode('utf-8'))
            evidence = folder / (name + '.json')
            run = subprocess.run([sys.executable, str(audit_script), str(netlist), '--output', str(evidence)],
                                 capture_output=True, text=True, timeout=args.timeout_seconds)
            detail = json.loads(evidence.read_text(encoding='utf-8')) if evidence.exists() else {}
            if mutation is None:
                passed = run.returncode == 0 and detail.get('status') == 'PASS'
            else:
                passed = (run.returncode != 0 and detail.get('status') == 'FAIL' and
                          expected_error in detail.get('error', ''))
            results.append(dict(case=name, expected='PASS' if mutation is None else 'REJECT',
                                status='PASS' if passed else 'FAIL', exit_code=run.returncode,
                                mutated_netlist_sha256=digest(netlist.read_bytes()),
                                diagnostic=detail.get('error', run.stdout.strip())))
            if not passed:
                raise RuntimeError('Unexpected audit result: ' + json.dumps(results[-1]))
    if args.netlist.read_bytes() != original:
        raise RuntimeError('Input netlist changed during fixture checks')
    result = dict(schema=1, status='PASS', scope='Synthetic audit faults; not additional hardware evidence',
                  netlist_sha256=digest(original), runner_sha256=digest(runner.read_bytes()),
                  audit_script_sha256=digest(audit_script.read_bytes()), cases=results,
                  generic_lut_cases=generic_checks,
                  reproduce='python scripts/test_cpu_ads.py <actual-integrated-ADS.vm> --output <result.json>')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('CPU_ADS_FIXTURES_PASS cases=' + str(len(results)))


if __name__ == '__main__':
    main()
