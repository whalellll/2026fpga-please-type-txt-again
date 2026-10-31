#!/usr/bin/env python3
"""Check CPU coremark_test_soc control cones in a PDS 2022.2 ADS Verilog netlist.

This evaluates selected combinational LUT cones, not the complete sequential
design or routed timing. Unknown cells/signals in an evaluated cone fail closed.
GTP LUT bit order follows the vendor simulation library (I0 is the low bit).
Bindings below were inspected in the standalone coremark_soc_top ADS netlist
for CPU 01747a11 and the current GCC 16 firmware. A changed/unknown netlist shape fails instead of guessing names.
"""
import argparse
from functools import lru_cache
import hashlib
import itertools
import json
import random
import re
from pathlib import Path


@lru_cache(maxsize=32768)
def signal(value):
    return re.sub(r"\s+", "", value.replace("\\", ""))


class Cone:
    def __init__(self, source, module):
        match = re.search(r"(?ms)^module " + re.escape(module) + r"\s.*?^endmodule", source)
        if not match:
            raise ValueError("Missing module " + module)
        body = re.sub(r"/\*.*?\*/|//[^\n]*", "", match.group(), flags=re.S)
        self.drivers = {}
        self.aliases = {signal(a): signal(b) for a, b in re.findall(r"\bassign\s+([^=;]+)=([^;]+);", body)}
        pattern = r"\b(GTP_\w+)\s*(?:#\s*\((.*?)\))?\s+(\\[^\s]+|\w+)\s*\((.*?)\);"
        for cell in re.finditer(pattern, body, re.S):
            kind, params, name, connections = cell.groups()
            ports = {p: signal(v) for p, v in re.findall(r"\.(\w+)\s*\(([^()]*)\)", connections)}
            init = re.search(r"\.INIT\s*\(\s*\d+'([bh])([0-9a-fA-F_]+)\s*\)", params or "")
            node = {"kind": kind, "name": signal(name), "ports": ports, "support": {},
                    "init": int(init[2].replace("_", ""), 2 if init[1] == "b" else 16) if init else None}
            for port in ("Z", "Z5", "COUT", "Q"):
                if port in ports:
                    self.drivers[ports[port]] = (node, port)

    def evaluate(self, target, values, cache=None, active=None):
        cache = {} if cache is None else cache
        active = set() if active is None else active
        target = signal(target)
        if target in values:
            return values[target]
        if target in cache:
            return cache[target]
        if target in ("1'b0", "1'b1"):
            return int(target[-1])
        if target in active:
            raise ValueError('Combinational cycle in evaluated cone: ' + target)
        active.add(target)
        if target in self.aliases:
            result = self.evaluate(self.aliases[target], values, cache, active)
        else:
            if target not in self.drivers:
                raise ValueError("No combinational driver/value for " + target)
            node, port = self.drivers[target]
            kind, ports = node['kind'], node['ports']
            lut = re.fullmatch(r"GTP_LUT([1-6])(D)?", kind)
            if lut:
                width = 5 if port == 'Z5' else int(lut[1])
                init = node['init'] & ((1 << (1 << width)) - 1)
                # A LUT6D's Z/Z5 outputs can share terms. Resolve constants and
                # already-known pins before finding support: e.g. fixed I5=1
                # makes the low half-table irrelevant to Z. Following its
                # unused inputs can create a false dependency cycle.
                fixed_mask = fixed_value = 0
                for bit in range(width):
                    wire = ports['I' + str(bit)]
                    seen = set()
                    while wire in self.aliases and wire not in values and wire not in cache and wire not in seen:
                        seen.add(wire)
                        wire = self.aliases[wire]
                    known = values.get(wire, cache.get(wire))
                    if wire in ("1'b0", "1'b1"):
                        known = int(wire[-1])
                    if known is not None:
                        fixed_mask |= 1 << bit
                        fixed_value |= known << bit
                key = (port, fixed_mask, fixed_value)
                if key not in node['support']:
                    compatible = [i for i in range(1 << width) if i & fixed_mask == fixed_value]
                    node['support'][key] = [bit for bit in range(width) if not fixed_mask & (1 << bit) and
                        any(((init >> i) ^ (init >> (i ^ (1 << bit)))) & 1 for i in compatible)]
                index = fixed_value
                for bit in node['support'][key]:
                    # Only ignore a pin when its entire remaining cofactor
                    # proves it cannot affect this evaluated output.
                    index |= self.evaluate(ports['I' + str(bit)], values, cache, active) << bit
                result = (init >> index) & 1
            elif kind.startswith('GTP_MUX2'):
                select = self.evaluate(ports['S'], values, cache, active)
                result = self.evaluate(ports['I' + str(select)], values, cache, active)
            else:
                raise ValueError("Unsupported evaluated driver: " + kind + " " + node['name'])
        cache[target] = result
        active.remove(target)
        return result

    def primitive(self, target):
        node, port = self.drivers[target]
        return dict(type=node['kind'], instance=node['name'], output=port,
                    init=node['init'], ports=node['ports'])

    def fanin(self, target):
        """Structural combinational fan-in, stopping at register outputs."""
        seen = set()
        def visit(name):
            if name in seen:
                return
            seen.add(name)
            if name in self.aliases:
                visit(self.aliases[name])
            if name not in self.drivers:
                return
            node, port = self.drivers[name]
            if port == 'Q':
                return
            for pin, wire in node['ports'].items():
                if pin.startswith('I') or pin in ('S', 'CIN'):
                    visit(wire)
        visit(target)
        return seen


def bits(name, value, width=32):
    return {name + '[' + str(i) + ']': (value >> i) & 1 for i in range(width)}


def device(address):
    return address >> 16 == 0x0200 or address >> 20 == 0x1FE


def uncacheable(address):
    # Boot BRAM, including 1c018000..1c01bfff, is ordinary cached memory.
    return device(address) or address >> 30 == 2


def check(condition, message):
    if not condition:
        raise ValueError(message)


def audit(path):
    original_bytes = path.read_bytes()
    source = original_bytes.decode('utf-8')
    frontend = Cone(source, 'CoreFrontend')
    rsmem = Cone(source, 'RsMem')
    pma = Cone(source, 'PhysicalMemoryAttributes')
    mmu = Cone(source, 'PmaMmu')
    # Sample all line boundaries, descriptor lengths, branch positions and types,
    # simultaneous candidates, and illegal conditional/JALR opcode encodings.
    opcodes = [0x13, 0x6f, 0x63, 0x1063, 0x2063, 0x67, 0x1067]
    vectors = {tuple([opcode if i == lane else 0x13 for i in range(4)])
               for lane in range(4) for opcode in opcodes}
    vectors.update(itertools.product([0x13, 0x6f, 0x63, 0x67], repeat=4))
    frontend_cases = 0
    for instructions, pc_word, length in itertools.product(sorted(vectors), range(8), range(5)):
        values = bits('pdPc', pc_word * 4)
        values.update(bits('pdLength', length, 3))
        values.update(bits('pdFaults', 0, 10))
        types = []
        branches = []
        for i, instruction in enumerate(instructions):
            values.update(bits('pdInsts_' + str(i), instruction))
            jal = instruction & 127 == 0x6f
            cond = instruction & 127 == 0x63 and bool(instruction & (1 << 14) or not instruction & (1 << 13))
            jalr = instruction & 127 == 0x67 and (instruction >> 12) & 7 == 0
            types.append((jal, cond, jalr))
            branches.append(int(i < min(4, 8 - pc_word) and i < length and any(types[-1])))
        first = branches.index(1) if any(branches) else 0
        expected = {'branch' + str(i): branch for i, branch in enumerate(branches)}
        expected.update(found=int(any(branches)), selectedJal=int(types[first][0]),
                        selectedCond=int(types[first][1]), selectedJalr=int(types[first][2]))
        # Standalone ADS shares LUT terms with these two register outputs.
        # Enumerate every cofactor instead of assuming unbound state is zero:
        # the decoded branch/priority/type results must remain independent.
        for extra in itertools.product(range(2), repeat=2):
            state = dict(values)
            state.update(zip(('trainValid', 'trainLength[2]'), extra))
            cache = {}
            for target, value in expected.items():
                check(frontend.evaluate(target, state, cache) == value,
                      'Frontend mismatch ' + repr((target, instructions, pc_word, length, extra)))
            frontend_cases += 1
    # Preserve real refresh flip-flops and exercise both address-hint cones.
    for lane in range(2):
        check(rsmem.primitive('s0KeyRefreshA_' + str(lane))['type'].startswith('GTP_DFF'), 'Missing key-refresh register')
    edges = [0, 0x02000000, 0x02010000, 0x0c000000, 0x10000000, 0x10001000,
             0x1c000000, 0x1c018000, 0x1c01b0a8, 0x1c01c000, 0x1c020000,
             0x1d010000, 0x1d020000, 0x1d030000,
             0x1fc00000, 0x1fd00000, 0x1fe00000, 0x1ff00000, 0x40000000,
             0x80000000, 0xc0000000]
    addresses = {(edge + offset) & 0xffffffff for edge in edges for offset in (-4, 0, 4, 0xfffc)}
    addresses.update(0x1fe00000 + page * 0x10000 for page in range(16))
    random_source = random.Random(0x5633)
    addresses.update(random_source.getrandbits(32) & ~3 for _ in range(2048))
    pma_cases = hint_cases = 0
    for address in sorted(addresses):
        actual = pma.evaluate('N7', bits('u_cpu/core/memory/_u_pma_io_dPaddr', address))
        check(actual == int(uncacheable(address)), 'PMA MAT mismatch at ' + hex(address))
        n17 = mmu.evaluate('N17', bits('u_cpu/core/_memory_io_pma_i_paddr', address))
        # ADS factors the high-RAM allowance into the frontend consumer.
        values = bits('io_pma_i_paddr', address)
        values.update({'u_cpu/core/memory/u_pma/N17': n17, 'pfAdvance': 1})
        fault = frontend.evaluate('N711[6]', values)
        permitted = bool(address >> 31) or (address >> 30 == 0 and not device(address))
        check(fault == int(not permitted), 'PMA instruction-access mismatch at ' + hex(address))
        pma_cases += 1
        for lane, valid, refresh in itertools.product(range(2), range(2), range(2)):
            suffix = '_' + str(lane)
            values = bits('pairKeyA' + suffix, address >> 5, 27)
            values.update({'s0ValValidA' + suffix: valid, 's0KeyRefreshA' + suffix: refresh})
            actual = rsmem.evaluate('scanKnownCached' + suffix, values)
            check(actual == int(valid and not refresh and not uncacheable(address)),
                  'RsMem hint mismatch ' + repr((lane, hex(address), valid, refresh)))
            hint_cases += 1
    controls = {name: frontend.primitive(name) for name in
                ['branch0', 'branch1', 'branch2', 'branch3', 'found', 'selectedJal', 'selectedCond', 'selectedJalr', 'pdRepair']}
    for name, cell in controls.items():
        check(cell['type'].startswith('GTP_LUT'), 'Unexpected control primitive ' + name)
        width = 5 if cell['output'] == 'Z5' else int(re.fullmatch(r'GTP_LUT([1-6])D?', cell['type'])[1])
        mask = (1 << (1 << width)) - 1
        check((cell['init'] & mask) not in (0, mask), 'Constant control ' + name)
    repair_inputs = ['branch0', 'branch1', 'branch2', 'branch3', 'found', 'selectedJal', 'selectedCond']
    check(set(repair_inputs) <= frontend.fanin('pdRepair'), 'Predecode controls missing from repair fan-in')
    check(path.read_bytes() == original_bytes, 'Netlist changed while its control cones were being checked')
    return dict(schema_version=1, status='PASS', profile='CPU coremark_test_soc RV32IMA without obsolete DMA carve-out',
                scope='selected post-ADS combinational LUT cones; not whole-design gate simulation, STA or board acceptance',
                netlist_sha256=hashlib.sha256(original_bytes).hexdigest(),
                frontend_cases=frontend_cases, pma_address_cases=pma_cases, rsmem_hint_cases=hint_cases,
                frontend_extra_state_cofactors=['trainValid', 'trainLength[2]'],
                pma_device_windows=['02000000..0200ffff', '1fe00000..1fefffff'],
                boot_bram_cached='1c000000..1c01ffff, including 1c018000..1c01bfff', uncached_alias='80000000..bfffffff',
                controls=controls,
                repair_structural_fanin=repair_inputs,
                refresh=[rsmem.primitive('s0KeyRefreshA_' + str(i)) for i in range(2)],
                hint=[rsmem.primitive('scanKnownCached_' + str(i)) for i in range(2)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.netlist)
        result['audit_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except Exception as error:
        result = dict(status='FAIL', error=str(error))
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        raise
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('ADS_CONTROLS_PASS frontend={frontend_cases} pma={pma_address_cases} hints={rsmem_hint_cases}'.format(**result))


if __name__ == '__main__':
    main()
