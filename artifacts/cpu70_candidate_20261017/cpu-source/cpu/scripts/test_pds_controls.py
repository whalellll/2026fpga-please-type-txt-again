#!/usr/bin/env python3
"""Exercise the CPU ADS audit against a real netlist and three deliberate faults.

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

from audit_pds_controls import Cone


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
    audit_script = runner.with_name('audit_pds_controls.py')
    generic_checks = check_generic_lut()
    original = args.netlist.read_bytes()
    source = original.decode('utf-8')
    hint = Cone(source, 'RsMem').primitive('scanKnownCached_0')
    # Current actual LUT3: I0=uncacheable, I1=refresh, I2=valid. Turn
    # valid && !uncacheable && !refresh (0x10) into valid && !uncacheable
    # (0x50). Refuse to mutate an unknown shape rather than weaken the test.
    if (hint['type'] != 'GTP_LUT3' or hint['init'] != 0x10 or
            hint['ports'].get('I1') != 's0KeyRefreshA_0' or
            hint['ports'].get('I2') != 's0ValValidA_0'):
        raise ValueError('Unknown refresh LUT shape; review the fixture')
    cases = [('original', None, None),
             ('branch0_constant_zero', ('CoreFrontend', 'branch0', 0), 'Frontend mismatch'),
             ('refresh_guard_bypassed', ('RsMem', 'scanKnownCached_0', 0x50), 'RsMem hint mismatch'),
             ('pma_all_cached', ('PhysicalMemoryAttributes', 'N7', 0), 'PMA MAT mismatch')]
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
                  reproduce='python scripts/test_pds_controls.py <actual-integrated-ADS.vm> --output <result.json>')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('BARE_ADS_FIXTURES_PASS cases=' + str(len(results)))


if __name__ == '__main__':
    main()
