"""Check all compact weight-bank DI pads in native ADS; does not prove STA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from audit_icache_pad_ads import cells, clean, module, ports, sha


def need(ok, message):
    if not ok:
        raise ValueError('Weight pad ADS: ' + message)


def audit_decoder_luts(extras, all_cells, ram):
    """Prove the paired even-word decoders against the unchanged odd decoders.

    The shared active-low write inhibit is an abstract input: all 64 index /
    inhibit combinations are checked, without assuming anything about its
    upstream producer. This supplements, rather than replaces, the DI audit.
    """
    if not extras:
        return 0
    need(len(extras) == 8, 'unknown additional dual LUT count')
    selected = lambda word: f'\\g_words.g_word[{word}].selected'
    drivers = {}
    for kind, cell, pins in all_cells:
        for pin in ('Q', 'Z', 'Z5', 'COUT', 'DO'):
            if pin in pins:
                drivers.setdefault(pins[pin], []).append((kind, cell, pins, pin))
    inhibit = set()
    for word in range(1, 32, 2):
        found = drivers.get(selected(word), [])
        need(len(found) == 1 and found[0][0] == 'GTP_LUT6', 'odd decoder mapping')
        pins = found[0][2]
        need([pins.get(f'I{i}') for i in range(5)] ==
             [f'io_wordIndex[{i}]' for i in range(5)], 'odd decoder index')
        inhibit.add(pins.get('I5'))
    need(len(inhibit) == 1 and None not in inhibit, 'shared write inhibit')
    inhibit = inhibit.pop()
    need(inhibit not in {f'io_wordIndex[{i}]' for i in range(5)} and
         inhibit not in ("1'b0", "1'b1"), 'invalid write inhibit')
    even = set()
    for name, (_, pins) in extras.items():
        need(set(pins) == {'Z', 'Z5', 'I0', 'I1', 'I2', 'I3', 'I4', 'I5'}, 'decoder ports')
        for pin in ('Z', 'Z5'):
            match = re.fullmatch(r'\\g_words.g_word\[(\d+)\]\.selected', pins[pin])
            need(match is not None, 'extra dual LUT is not a word decoder')
            word = int(match[1])
            need(0 <= word < 32 and word % 2 == 0 and word not in even, 'even decoder coverage')
            even.add(word)
    need(even == set(range(0, 32, 2)), 'missing even decoder')
    used = set()
    for index in range(32):
        for disabled in (0, 1):
            values = {f'io_wordIndex[{i}]': (index >> i) & 1 for i in range(5)}
            values.update({inhibit: disabled, "1'b0": 0, "1'b1": 1})
            visiting = set()
            def evaluate(net):
                if net in values:
                    return values[net]
                need(net not in visiting, 'decoder cycle')
                visiting.add(net)
                found = drivers.get(net, [])
                need(len(found) == 1, 'nonunique/unknown decoder driver')
                kind, cell, pins, output = found[0]
                need(kind in ('GTP_LUT2', 'GTP_LUT6', 'GTP_LUT6D'), 'unknown decoder primitive')
                width = 2 if kind == 'GTP_LUT2' else 6
                expected = {'Z'} | {f'I{i}' for i in range(width)}
                if kind == 'GTP_LUT6D':
                    expected.add('Z5')
                    need(cell['name'] in extras, 'decoder depends on data pad')
                need(set(pins) == expected and output in ('Z', 'Z5'), 'decoder primitive ports')
                params = ports(cell['params'] or '')
                match = re.fullmatch(str(1 << width) + r"'([bh])([0-9a-fA-F_]+)", params.get('INIT', ''))
                need(set(params) == {'INIT'} and match is not None, 'decoder INIT format')
                init = int(match[2].replace('_', ''), 2 if match[1] == 'b' else 16)
                need(init < (1 << (1 << width)), 'decoder INIT overflow')
                address = sum(evaluate(pins[f'I{i}']) << i for i in range(width if output == 'Z' else 5))
                values[net] = (init >> address) & 1
                used.add(cell['name'])
                visiting.remove(net)
                return values[net]
            for word in range(32):
                need(evaluate(selected(word)) == int(not disabled and index == word), 'word decoder truth table')
    need(set(extras) <= used, 'unproved extra dual LUT')
    for _, cell, pins in ram:
        word = int(re.fullmatch(r'\\g_words.g_word\[(\d+)\]\.memory_\d+', cell['name'])[1])
        need(pins.get('WE') == selected(word), 'RAM word write enable')
    return 32 * 64


def audit(source):
    body = module(source, 'Bank1R1W_1_compact')
    need(not re.search(r'\bassign\b', clean(body)), 'unreviewed alias')
    all_cells = [(k, c, ports(c['ports']))
                 for k in set(re.findall(r'\bGTP_\w+', clean(body)))
                 for c in cells(body, k)]
    names = [c['name'] for _, c, _ in all_cells]
    need(len(names) == len(set(names)), 'duplicate primitive')
    lut = {c['name']: (c, pins) for k, c, pins in all_cells if k == 'GTP_LUT6D'}
    need(len(lut) in (18, 26), 'expected eighteen pads with zero or eight paired word decoders')
    outputs = [None] * 32
    expected_drivers = {}
    pad_names = set()

    def check(name, inputs):
        need(name in lut, 'missing pad ' + name)
        pad_names.add(name)
        c, pins = lut[name]
        need((c['attr'] or '').strip() == '(* PAP_DONT_TOUCH *)', 'preservation attribute')
        init = ports(c['params'] or '').get('INIT', '')
        m = re.fullmatch(r"64'([bh])([0-9a-fA-F_]+)", init)
        need(m and int(m[2].replace('_', ''), 2 if m[1] == 'b' else 16) == 0xCCCCCCCCAAAAAAAA,
             'identity INIT')
        need(set(pins) == {'Z', 'Z5', 'I0', 'I1', 'I2', 'I3', 'I4', 'I5'}, 'pad ports')
        need([pins[x] for x in ('I0', 'I1')] == inputs, 'source swapped, tied or bypassed')
        need([pins[x] for x in ('I2', 'I3', 'I4', 'I5')] == ["1'b0"] * 3 + ["1'b1"], 'fixed pins')
        out = [pins['Z5'], pins['Z']]
        for pin, wire in zip(('Z5', 'Z'), out):
            need(re.fullmatch(r'[A-Za-z_][\w$]*(?:\[\d+\])?', wire) and
                 not wire.startswith('io_') and wire not in expected_drivers, 'output alias')
            expected_drivers[wire] = ('GTP_LUT6D', name, pin)
        return out

    for pair in range(16):
        outputs[pair*2:pair*2+2] = check(
            '\\g_word_input_hold.g_pair[' + str(pair) + '].u_word_input_hold_lut',
            [f'io_wordData[{pair*2}]', f'io_wordData[{pair*2+1}]'])
    special = {}
    for slot in (66, 928):
        out = check('u_weight_hold_lut_' + str(slot), [outputs[slot % 32], outputs[(slot+1) % 32]])
        special.update({slot: out[0], slot+1: out[1]})
    drivers = {}
    for k, c, pins in all_cells:
        for pin in ('Q', 'Z', 'Z5', 'COUT', 'DO'):
            for net in re.findall(r'[A-Za-z_][\w$]*(?:\[\d+\])?', pins.get(pin, '')):
                drivers.setdefault(net, []).append((k, c['name'], pin))
    for net, driver in expected_drivers.items():
        need(drivers.get(net) == [driver], 'nonunique pad driver')
    ram = [(k, c, pins) for k, c, pins in all_cells if k.startswith(('GTP_RAM', 'GTP_DRM'))]
    need(len(ram) == 1024 and all(k == 'GTP_RAM64X1DP' for k, _, _ in ram), 'cache capacity/mapping')
    seen = set()
    for _, c, pins in ram:
        m = re.fullmatch(r'\\g_words.g_word\[(\d+)\]\.memory_(\d+)', c['name'])
        need(m is not None, 'unknown RAM name')
        word, bit = map(int, m.groups()); slot = word * 32 + bit
        need(0 <= word < 32 and 0 <= bit < 32 and slot not in seen, 'RAM coverage')
        seen.add(slot)
        need(pins.get('DI') == special.get(slot, outputs[bit]), 'RAM DI bypass/swapped bit')
        for port, bus in (('RADDR', 'io_raddr'), ('WADDR', 'io_waddr')):
            need(pins.get(port) == '{' + ','.join(f'{bus}[{i}]' for i in range(5, -1, -1)) + '}', '64-line address')
        need(pins.get('WCLK') == 'io_clk', 'RAM clock')
    decoder_cases = audit_decoder_luts({n: v for n, v in lut.items() if n not in pad_names}, all_cells, ram)
    return dict(status='PASS', scope='MAPPED_WEIGHT_PADS_ONLY_NOT_STA_OR_BOARD', source_pairs=16,
                data_bits=32, ram_cells=1024, lines=64, di_pins_checked=1024,
                paired_decoder_luts=len(lut)-18, decoder_truth_cases=decoder_cases,
                unique_drivers=True, bypass=False, module_sha256=hashlib.sha256(body.encode()).hexdigest())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--netlist', type=Path, required=True)
    ap.add_argument('--input-snapshot', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); need(not a.output.exists(), 'refuse overwrite')
    raw = a.netlist.read_bytes()
    try:
        result = audit(raw.decode())
        snapshot = json.loads(a.input_snapshot.read_text(encoding='utf-8-sig'))
        for name in ('audit_mac_weight_pad_ads.py', 'audit_icache_pad_ads.py'):
            need(snapshot['inputs']['scripts/' + name] == sha(Path(__file__).with_name(name)), 'checker not frozen')
        need(a.netlist.read_bytes() == raw, 'netlist changed during audit')
        result.update(run_id=snapshot['run_id'], input_snapshot_sha256=sha(a.input_snapshot),
                      netlist_sha256=sha(a.netlist), checker_sha256=sha(Path(__file__)),
                      rtl_sha256=snapshot['inputs']['rtl/mac_accel/MacAccelCore.v'])
    except (ValueError, AssertionError, KeyError) as e:
        result = dict(status='FAIL', error=str(e))
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print('WEIGHT_PAD_ADS_' + result['status'])
    if 'error' in result:
        print(result['error'])
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
