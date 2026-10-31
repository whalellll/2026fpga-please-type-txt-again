"""Check the integrated UART TX FIFO write-address identity pads after ADS.

This is a structural mapping contract, not routed hold or board acceptance.
Unknown mappings fail closed. Native RAM instance names are deliberately not
assumed: all four dual-bit RAMs and all sixteen low WADDR pins are checked.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from audit_icache_pad_ads import cells, clean, module, ports, sha


def require(condition, message):
    if not condition:
        raise ValueError('UART TX pad ADS: ' + message)


def audit(source):
    for parent, kind, inst, clock in (
            ('soc_top', 'axi_boot_periph', 'u_local', 'sys_clk'),
            ('axi_boot_periph', 'uart_tx_fifo', 'u_tx', 'clk')):
        matches = cells(module(source, parent), kind)
        require(len(matches) == 1 and matches[0]['name'] == inst,
                'missing or duplicate integrated hierarchy ' + parent + '/' + inst)
        require(ports(matches[0]['ports']).get('clk') == clock, 'wrong SYS clock binding')
    body = module(source, 'uart_tx_fifo')
    module_inputs = set(re.findall(r'\b(?:input|inout)\s+(?:\[\d+:\d+\]\s+)?([A-Za-z_][\w$]*)', clean(body)))
    # ADS emits direct primitive wiring here. Accepting an unreviewed alias
    # would weaken the no-bypass and unique-driver checks.
    require(not re.search(r'\bassign\b', clean(body)), 'unexpected alias/assignment')
    kinds = set(re.findall(r'\b(GTP_\w+)\s', clean(body)))
    primitive_cells = [(kind, cell, ports(cell['ports']))
                       for kind in sorted(kinds) for cell in cells(body, kind)]
    names = [cell['name'] for _, cell, _ in primitive_cells]
    require(len(names) == len(set(names)), 'duplicate primitive instance')
    # ADS may merge the wr_ptr wire into its pad_address_in alias (run8ad).
    # Recover the four nets from the exact retained register instances, never
    # from a bus name alone. Only these two observed bus spellings are accepted.
    pointer_cells = [(kind, cell, pins) for kind, cell, pins in primitive_cells
                     if re.fullmatch(r'\\wr_ptr\[\d+\]', cell['name'])]
    require(len(pointer_cells) == 4, 'missing or extra write pointer FF')
    pointer_wires = []
    pointer_drivers = []
    pointer_bus = None
    for bit in range(4):
        matches = [(kind, cell, pins) for kind, cell, pins in pointer_cells
                   if cell['name'] == f'\\wr_ptr[{bit}]']
        require(len(matches) == 1 and matches[0][0] == 'GTP_DFF_RE' and
                matches[0][2].get('CLK') == 'clk' and matches[0][2].get('CE') == 'push',
                'write pointer is not one preserved SYS/push-enabled FF per bit')
        kind, cell, pins = matches[0]
        net = re.fullmatch(r'(wr_ptr|pad_address_in)\[' + str(bit) + r'\]', pins.get('Q', ''))
        require(net is not None and net[1] not in module_inputs and
                (pointer_bus is None or pointer_bus == net[1]), 'write pointer Q mapping changed')
        pointer_bus = net[1]
        pointer_wires.append(pins['Q'])
        pointer_drivers.append((kind, cell['name'], 'Q'))
    declarations = re.findall(r'\bwire\s+\[(\d+):(\d+)\]\s+' + re.escape(pointer_bus) + r'\s*;', clean(body))
    require(declarations == [('3', '0')], 'unknown or duplicate write pointer width')
    pads = [(kind, cell, pins) for kind, cell, pins in primitive_cells
            if 'write_address_pad' in cell['name'] or 'u_hold_dual_lut' in cell['name']]
    require(len(pads) == 2, 'expected exactly two write-address pads')
    outputs = [None] * 4
    expected_driver = {}
    pairs = []
    seen = set()
    for kind, cell, pins in pads:
        match = re.fullmatch(r'\\write_address_pad\[([01])\]\.u_hold_dual_lut', cell['name'])
        require(kind == 'GTP_LUT6D' and match is not None, 'unknown pad primitive/name')
        pair = int(match[1])
        require(pair not in seen, 'duplicate pad pair'); seen.add(pair)
        require((cell['attr'] or '').strip() == '(* PAP_DONT_TOUCH *)', 'pad preservation attribute missing')
        init = ports(cell['params'] or '').get('INIT', '')
        value = re.fullmatch(r"64'([bh])([0-9a-fA-F_]+)", init)
        require(value and int(value[2].replace('_', ''), 2 if value[1] == 'b' else 16) == 0xCCCCCCCCAAAAAAAA,
                'pad identity INIT changed')
        require(set(pins) == {'Z', 'Z5', 'I0', 'I1', 'I2', 'I3', 'I4', 'I5'}, 'pad pins incomplete')
        require(pins['I0'] == pointer_wires[pair*2] and pins['I1'] == pointer_wires[pair*2+1],
                'pad is tied, swapped or not fed by the write pointer')
        require([pins[x] for x in ('I2', 'I3', 'I4', 'I5')] == ["1'b0", "1'b0", "1'b0", "1'b1"],
                'pad select/fixed pins changed')
        for bit, port in ((pair*2, 'Z5'), (pair*2+1, 'Z')):
            wire = pins[port]
            require(re.fullmatch(r'[A-Za-z_][\w$]*(?:\[\d+\])?', wire) is not None and
                    wire.split('[')[0] not in {'wr_ptr', 'pad_address_in'} | module_inputs,
                    'pad output tied, aliased to an input or bypassed')
            outputs[bit] = wire
            expected_driver[wire] = (kind, cell['name'], port)
        pairs.append(dict(pair=pair, instance=cell['name'], inputs=[pins['I0'], pins['I1']],
                          outputs=[pins['Z5'], pins['Z']]))
    require(seen == {0, 1} and len(set(outputs)) == 4, 'pad outputs overlap or are missing')
    drivers = {}
    for kind, cell, pins in primitive_cells:
        for port in ('Q', 'Z', 'Z5', 'COUT', 'DO'):
            for wire in re.findall(r'[A-Za-z_][\w$]*(?:\[\d+\])?', pins.get(port, '')):
                drivers.setdefault(wire, []).append((kind, cell['name'], port))
    for wire, driver in expected_driver.items():
        require(drivers.get(wire) == [driver], 'pad output lacks one unique driver: ' + wire)
    for wire, driver in zip(pointer_wires, pointer_drivers):
        require(drivers.get(wire) == [driver], 'write pointer Q lacks one unique driver: ' + wire)
    memories = [(kind, cell, pins) for kind, cell, pins in primitive_cells
                if kind.startswith(('GTP_RAM', 'GTP_DRM'))]
    require(len(memories) == 4 and all(kind == 'GTP_RAM32X2DP' for kind, _, _ in memories),
            'unknown FIFO storage mapping or missing data bits')
    data = []
    ram_records = []
    shared_waddr = None
    for kind, cell, pins in memories:
        address = re.fullmatch(r'\{([^{}]+)\}', pins.get('WADDR', ''))
        bits_high_first = address[1].split(',') if address else []
        require(len(bits_high_first) == 5 and bits_high_first[0] == "1'b0" and
                Counter(bits_high_first[1:]) == Counter(outputs), 'FIFO WADDR bypassed, tied or missing')
        require(shared_waddr is None or shared_waddr == pins['WADDR'], 'inconsistent FIFO address permutation')
        shared_waddr = pins['WADDR']
        require(pins.get('WCLK') == 'clk' and pins.get('WE') == 'push', 'FIFO clock/write enable changed')
        bits = re.fullmatch(r'\{push_data\[([0-7])\],push_data\[([0-7])\]\}', pins.get('DI', ''))
        require(bits is not None, 'FIFO DI mapping changed')
        data.extend(int(x) for x in bits.groups())
        ram_records.append(dict(instance=cell['name'], primitive=kind, waddr=pins['WADDR'],
                                data_bits=[int(x) for x in bits.groups()],
                                waddr_low_to_high_pointer_bits=[outputs.index(w) for w in reversed(bits_high_first[1:])]))
    require(Counter(data) == Counter(range(8)), 'FIFO write data is not exactly eight bits')
    return dict(schema=1, status='PASS', scope='MAPPED_UART_TX_WADDR_PADS',
                hierarchy='soc_top/u_local/u_tx', pairs=sorted(pairs, key=lambda p:p['pair']),
                primitive='GTP_LUT6D', init='CCCCCCCC_AAAAAAAA', preservation_attribute='PAP_DONT_TOUCH',
                address_bits=4, upstream_ff_bits=4, memory_cells=4, data_bits=8, waddr_pins_checked=16,
                memories=ram_records, unique_drivers=True, bypass=False,
                module_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest(),
                post_pnr_physical_retention_proven=False, routed_hold_margin_proven=False)


def bind_result(result, netlist, snapshot_path):
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes.decode('utf-8-sig'))
    checker = sha(Path(__file__))
    parser = sha(Path(__file__).with_name('audit_icache_pad_ads.py'))
    require(snapshot['inputs'].get('scripts/audit_uart_tx_pad_ads.py') == checker, 'checker differs from frozen input')
    require(snapshot['inputs'].get('scripts/audit_icache_pad_ads.py') == parser, 'parser differs from frozen input')
    result.update(checker_sha256=checker, parser_sha256=parser, vm_sha256=sha(netlist),
                  input_snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest(), run_id=snapshot['run_id'],
                  uart_rtl_sha256=snapshot['inputs']['rtl/soc/uart_tx_fifo.v'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input-snapshot', type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'refuse to overwrite evidence')
    before = args.netlist.read_bytes()
    try:
        result = audit(before.decode('utf-8'))
        if args.input_snapshot:
            result = bind_result(result, args.netlist, args.input_snapshot)
        require(args.netlist.read_bytes() == before, 'netlist changed during audit')
    except (ValueError, AssertionError, KeyError) as error:
        result = dict(schema=1, status='FAIL', error=str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('UART_TX_PAD_ADS_' + result['status'])
    if 'error' in result:
        print(result['error'])
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
