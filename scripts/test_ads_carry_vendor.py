"""Check exact carry-cone semantics against unmodified PDS vendor simulation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess

from ads_bdd import BDD, cone_evaluator, cone_leaves
from audit_cpu_ads import Cone


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vendor-models', type=Path, required=True)
    ap.add_argument('--icarus-bin', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(0x6ca770)
    inits = [0, (1 << 64)-1, 0xAAAAAAAA55555555, 0xCCCCCCCC33333333]
    inits += [1 << bit for bit in range(64)]
    inits += [rng.getrandbits(64) for _ in range(32)]
    models = [a.vendor_models / (n+'.v') for n in
              ['GTP_LUT6CARRY', 'GTP_LUT5', 'INT_LUTMUX2_UDP', 'INT_LUTMUX4_UDP']]
    lines = ['module tb;', 'reg [6:0] x;', 'integer k;', 'wire [399:0] z,c;']
    expected = []
    cases = 0
    for init in inits:
        for to_lut, to_carry in [('FALSE','FALSE'), ('FALSE','TRUE'), ('TRUE','FALSE'), ('TRUE','TRUE')]:
            n = len(expected)
            params = f'.INIT(64\'h{init:016x}),.I5_TO_LUT("{to_lut}"),.I5_TO_CARRY("{to_carry}")'
            pins = ','.join(f'.I{i}(x{i})' for i in range(6))+',.CIN(x6)'
            text = f'module m (); GTP_LUT6CARRY #({params}) g (.Z(z),.COUT(c),{pins});\nendmodule'
            cone = Cone(text, 'm')
            variables = [f'x{i}' for i in range(7)]
            bdd = BDD(variables); walk = cone_evaluator(cone, bdd)
            roots = [walk(port) for port in ['z', 'c']]
            assert cone_leaves(cone, ['z','c']) <= set(variables)
            tables = [0,0]
            for k in range(128):
                values = {f'x{i}':(k >> i)&1 for i in range(7)}
                for j, port in enumerate(['z','c']):
                    scalar = cone.evaluate(port, values)
                    node = roots[j]
                    while node > 1:
                        var, low, high = bdd.nodes[node]
                        node = high if values[variables[var]] else low
                    assert node == scalar
                    tables[j] |= scalar << k
                    cases += 1
            expected.append(tables)
            pins = ','.join(f'.I{i}(x[{i}])' for i in range(6))+',.CIN(x[6])'
            lines.append(f'GTP_LUT6CARRY #({params}) g{n} (.Z(z[{n}]),.COUT(c[{n}]),{pins});')
    lines += ['initial begin', 'for(k=0;k<128;k=k+1) begin x=k; #1;']
    for n, tables in enumerate(expected):
        for port, table in zip(['z','c'], tables):
            lines.append(f'if ({port}[{n}] !== ((128\'h{table:032x} >> k) & 1)) $fatal(1,"carry mismatch {n} {port} k=%d",k);')
    lines += ['end', '$display("ADS_CARRY_VENDOR_PASS"); $finish;', 'end', 'endmodule']
    tb = a.output/'tb.sv'; tb.write_text('\n'.join(lines)+'\n')
    exe = a.output/'tb.vvp'
    env=dict(os.environ); env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
    compiled=subprocess.run([str(a.icarus_bin/'iverilog.exe'), '-g2012', '-s', 'tb', '-o', str(exe),
                    str(tb), *map(str,models)], capture_output=True, timeout=60,env=env)
    (a.output/'compile.log').write_bytes(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0, 'Vendor compile failed; inspect compile.log'
    run = subprocess.run([str(a.icarus_bin/'vvp.exe'),str(exe)], check=True,
                         capture_output=True, text=True, timeout=60,env=env)
    assert 'ADS_CARRY_VENDOR_PASS' in run.stdout
    (a.output/'vendor.log').write_text(run.stdout+run.stderr)
    # Defaults are legal; invalid parameters and unsupported variants fail closed.
    default = Cone('module m (); GTP_LUT6CARRY #(.INIT(64\'h0123456789abcdef)) g '
                   '(.Z(z),.COUT(c),'+','.join(f'.I{i}(x{i})' for i in range(6))+',.CIN(x6));\nendmodule','m')
    explicit = Cone('module m (); GTP_LUT6CARRY #(.INIT(64\'h0123456789abcdef),'
                    '.I5_TO_LUT("FALSE"),.I5_TO_CARRY("TRUE")) g '
                    '(.Z(z),.COUT(c),'+','.join(f'.I{i}(x{i})' for i in range(6))+',.CIN(x6));\nendmodule','m')
    for k in range(128):
        values={f'x{i}':(k>>i)&1 for i in range(7)}
        for port in ['z','c']: assert default.evaluate(port,values)==explicit.evaluate(port,values)
    for kind, params in [('GTP_LUT6CARRY','.I5_TO_LUT("BAD")'),('GTP_LUT6CARRY_E1','')]:
        source=f'module m (); {kind} #(.INIT(64\'h0){","+params if params else ""}) g (.Z(z));\nendmodule'
        try: cone_evaluator(Cone(source,'m'),BDD([]))('z')
        except (ValueError,KeyError): pass
        else: raise AssertionError('Unknown carry form accepted')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    record=dict(status='PASS',vendor_output_cases=cases,scalar_bdd_cases=cases,
                primitive_configurations=len(expected),default_cases=256,negative_cases=2,
                vendor_sha256={str(p):sha(p) for p in models},
                checker_sha256={n:sha(Path(__file__).with_name(n)) for n in
                                ['test_ads_carry_vendor.py','ads_bdd.py','audit_cpu_ads.py']},
                scope='Binary combinational behavior only; not STA or board acceptance')
    (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print('ADS_CARRY_VENDOR_PASS cases='+str(cases))


if __name__ == '__main__': main()
