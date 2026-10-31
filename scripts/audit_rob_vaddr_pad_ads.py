"""Verify mapped ROB write pads and head FF retention, not routed timing."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from audit_icache_pad_ads import cells, clean, module, ports, sha
from audit_cpu_ads import instance_ports


def need(ok, message):
    if not ok:
        raise ValueError('ROB pad ADS: ' + message)


def vector(value, width):
    value = value.replace('\\', '')
    if value.startswith('{') and value.endswith('}'):
        result = value[1:-1].split(',')
    elif re.fullmatch(r'[\w/$]+', value):
        result = [f'{value}[{i}]' for i in range(width-1, -1, -1)]
    else:
        raise ValueError('ROB pad ADS: unsupported vector ' + value)
    need(len(result) == width, 'vector width')
    return result


def audit(source):
    pad = module(source, 'PangoRobVaddrPad')
    need(not re.search(r'\bassign\b', clean(pad)), 'pad alias/bypass')
    lut = cells(pad, 'GTP_LUT6D')
    need(len(lut) == 16, 'sixteen identity pairs')
    seen = set()
    for c in lut:
        m = re.fullmatch(r'\\data_pad\[(\d+)\]\.u_hold_dual_lut', c['name'])
        need(m is not None, 'pad instance identity')
        n = int(m[1]); need(0 <= n < 16 and n not in seen, 'pair coverage'); seen.add(n)
        need((c['attr'] or '').strip() == '(* PAP_DONT_TOUCH *)', 'pad preservation')
        init = ports(c['params'] or '').get('INIT', '')
        m = re.fullmatch(r"64'([bh])([0-9a-fA-F_]+)", init)
        need(m and int(m[2].replace('_', ''), 2 if m[1] == 'b' else 16) == 0xCCCCCCCCAAAAAAAA,
             'identity INIT')
        expect = {'I0': f'dataIn[{2*n}]', 'I1': f'dataIn[{2*n+1}]',
                  'I2': "1'b0", 'I3': "1'b0", 'I4': "1'b0", 'I5': "1'b1",
                  'Z5': f'dataOut[{2*n}]', 'Z': f'dataOut[{2*n+1}]'}
        need(ports(c['ports']) == expect, 'pad bit/fixed-pin wiring')
    p = instance_ports(source, 'Rob', 'PangoRobVaddrPad', 'memVaddrWrite_memVaddrPad')
    need(p.get('dataIn') == 'io_memFwd_vaddr', 'actual virtual-address source')
    out = vector(p['dataOut'], 32)
    need(len(set(out)) == 32, 'unique pad output bits')
    rob = module(source, 'Rob')
    for lhs in re.findall(r'\bassign\s+([^=;]+)=', clean(rob)):
        need(not any(v in lhs.replace('\\', '').replace(' ', '') for v in out), 'parallel output driver')
    mem = instance_ports(source, 'Rob', 'memPayloadFwd_32x72', 'memPayloadFwd_ext')
    data = vector(mem['W0_data'], 72)
    need(data[8:40] == out, 'all virtual-address RAM inputs traverse pads')
    need(mem.get('R0_clk') == 'clock' and mem.get('W0_addr') == 'io_memFwd_robid', 'write clock/address')
    body = module(source, 'memPayloadFwd_32x72')
    ram = cells(body, 'GTP_RAM32X2DP'); need(len(ram) == 72, 'RAM capacity/two-read mapping')
    read_coverage = Counter(); di_coverage = Counter()
    for c in ram:
        pins = ports(c['ports'])
        di = vector(pins['DI'], 2); do = vector(pins['DO'], 2)
        for src, dst in zip(di, do):
            m = re.fullmatch(r'R([01])_data\[(\d+)\]', dst)
            need(m is not None, 'RAM output mapping')
            bank, bit = map(int, m.groups())
            need(src == f'W0_data[{bit}]' and bit < 72, 'RAM DI bit/bypass')
            read_coverage[(bank, bit)] += 1; di_coverage[bit] += 1
        need(pins.get('WCLK') == 'R0_clk' and pins.get('WE') == 'W0_en' and
             pins.get('WADDR') == 'W0_addr', 'RAM write contract')
    need(read_coverage == Counter({(bank, bit): 1 for bank in range(2) for bit in range(72)}),
         'all logical bits and both read copies')
    need(all(di_coverage[i] == 2 for i in range(32, 64)), '64 actual padded DI pins')
    head = module(source, 'RobHead80')
    regs = [c for kind in set(re.findall(r'\bGTP_DFF\w*', clean(head))) for c in cells(head, kind)]
    q = [ports(c['ports']).get('Q') for c in regs]
    need(len(regs) == len(set(q)) == 16 and None not in q, 'sixteen independent head FFs')
    return dict(status='PASS', scope='ROB_PAD_AND_HEAD_ADS_RETENTION_ONLY_NOT_STA_OR_BOARD',
                source_pairs=16, data_bits=32, ram_cells=72, padded_di_pins=64,
                head_register_bits=16, ram_slots=32, read_copies=2,
                bypass=False, pad_module_sha256=__import__('hashlib').sha256(pad.encode()).hexdigest())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--netlist', type=Path, required=True)
    ap.add_argument('--input-snapshot', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); need(not a.output.exists(), 'refuse overwrite')
    try:
        raw = a.netlist.read_bytes(); result = audit(raw.decode())
        snapshot = json.loads(a.input_snapshot.read_text(encoding='utf-8-sig'))
        for name in ['audit_rob_vaddr_pad_ads.py', 'audit_icache_pad_ads.py', 'audit_cpu_ads.py']:
            need(snapshot['inputs']['scripts/' + name] == sha(Path(__file__).with_name(name)), 'checker frozen')
        need(a.netlist.read_bytes() == raw, 'netlist unchanged')
        result.update(run_id=snapshot['run_id'], input_snapshot_sha256=sha(a.input_snapshot),
                      netlist_sha256=sha(a.netlist), checker_sha256=sha(Path(__file__)),
                      cpu_rtl_sha256=snapshot['inputs']['rtl/cpu/CoreTop.sv'])
    except (ValueError, AssertionError, KeyError) as error:
        result = dict(status='FAIL', error=str(error))
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print('ROB_VADDR_PAD_ADS_' + result['status'])
    if result['status'] != 'PASS':
        print(result['error']); raise SystemExit(1)


if __name__ == '__main__': main()
