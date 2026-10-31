#!/usr/bin/env python3
"""Check integrated CPU control cones in a PDS 2022.2 ADS Verilog netlist.

This evaluates selected combinational LUT cones, not the complete sequential
design or routed timing. Unknown cells/signals in an evaluated cone fail closed.
GTP LUT bit order follows the vendor simulation library (I0 is the low bit).
The frontend, PMA and RsMem bindings originated with CPU V3.1. V3.5 adds
explicitly scoped ROB ownership/valid/read retention checks for V6.5 snapshots.
A changed/unknown netlist shape fails instead of guessing names. Historical
V6.1 snapshots retain their original audit scope; they cannot certify V6.5.
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
                    "string_params": dict(re.findall(r'\.(\w+)\s*\(\s*"([^"\n]*)"\s*\)', params or "")),
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
            elif kind == 'GTP_LUT6CARRY':
                from ads_bdd import lut_inputs
                table, names = lut_inputs(node, port)
                index = sum(self.evaluate(name, values, cache, active) << i for i, name in enumerate(names))
                result = (table >> index) & 1
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


PMA_ADDRESS = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/_u_pma_io_dPaddr'
PMA_LSU_SHARED = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/attributes/N7'


def module_text(source, name):
    matches = list(re.finditer(r'(?ms)^module ' + re.escape(name) + r'\s.*?^endmodule', source))
    check(len(matches) == 1, 'Missing or repeated ADS module ' + name)
    return matches[0].group()


def instance_ports(source, parent, kind, name):
    body = module_text(source, parent)
    matches = list(re.finditer(r'\b' + re.escape(kind) + r'\s+' + re.escape(name) +
                              r'\s*\((.*?)\);', body, re.S))
    check(len(matches) == 1, 'Missing or repeated ADS instance ' + parent + '/' + name)
    pairs = [(signal(port), signal(value)) for port, value in
             re.findall(r'\.(\\[^\s(]+|\w+)\s*\(([^()]*)\)', matches[0].group(1))]
    ports = dict(pairs)
    check(len(ports) == len(pairs), 'Duplicate ADS port in ' + parent + '/' + name)
    return ports


def pma_output_names(source):
    """Read the observed four-output or fused single-output PMA interface."""
    header = module_text(source, 'PhysicalMemoryAttributes').split(');', 1)[0].replace('\r\n', '\n')
    outputs = re.findall(r'(?m)^[ \t]*output[ \t]+([A-Za-z_]\w*)[ \t]*(?:,|$)', header)
    declarations = re.findall(r'(?m)^[ \t]*output\b', header)
    check(len(outputs) == len(declarations) == len(set(outputs)) and
          (len(outputs) == 4 or outputs == ['N7']),
          'Unexpected PhysicalMemoryAttributes output-port topology')
    return tuple(outputs)


def pma_translate_source(attr_ports):
    candidates=[name for name,value in attr_ports.items() if
                re.fullmatch(r'u_cpu/u_cpu_wrapper/u_cpu/core/backend/N\d+',name) and value=='dTranslate']
    check(len(candidates)==1,'Supervisor PMA translation source is not uniquely wired to dTranslate')
    return candidates[0]


def audit_pma_single_output(source, addresses):
    """Prove the PDS-fused PMA N7 and both outputs of its shared LSU LUT."""
    pma = Cone(source, 'PhysicalMemoryAttributes')
    lsu = Cone(source, 'Lsu')
    attr_ports = instance_ports(source, 'PmaMmu', 'PhysicalMemoryAttributes', 'attributes')
    mmu_ports = instance_ports(source, 'CoreMemory', 'PmaMmu', 'u_pma')
    lsu_ports = instance_ports(source, 'CoreMemory', 'Lsu', 'u_lsu')
    if 'io_dPaddr' in attr_ports and any(value=='dTranslate' for value in attr_ports.values()):
        return audit_pma_supervisor_output(pma, lsu, attr_ports, mmu_ports, lsu_ports, addresses)
    check(set(attr_ports) == {PMA_ADDRESS, 'N7'},
          'Fused PMA instance ports do not match its interface')
    check(attr_ports.get('N7') == 'attributes/N7' and
          mmu_ports.get('attributes/N7') == 'u_pma/attributes/N7' and
          lsu_ports.get(PMA_LSU_SHARED) == 'u_pma/attributes/N7',
          'PMA output is disconnected before LSU: N7')
    check(lsu_ports.get('io_pmaDPaddr') == '_u_pma_io_dPaddr',
          'LSU PMA address is not the shared CoreMemory address')
    mmu_address = mmu_ports.get(PMA_ADDRESS, '')
    attr_address = attr_ports.get(PMA_ADDRESS, '')
    for bit in range(16, 32):
        check(mmu_address.count('_u_pma_io_dPaddr[' + str(bit) + ']') == 1,
              'PmaMmu address bit is disconnected: ' + str(bit))
        check(attr_address.count(PMA_ADDRESS + '[' + str(bit) + ']') == 1,
              'PhysicalMemoryAttributes address bit is disconnected: ' + str(bit))
    check({PMA_ADDRESS + '[' + str(bit) + ']' for bit in range(16, 32)} <= pma.fanin('N7'),
          'Fused PMA output lost an address bit')
    mapped_output = pma.primitive('N7')
    check(mapped_output['type'] == 'GTP_LUT6' and mapped_output['output'] == 'Z' and
          mapped_output['init'] not in (None, 0, (1 << 64) - 1),
          'PMA output LUT is constant or not a mapped LUT: N7')
    store = lsu.primitive('N13')
    load = lsu.primitive('N965')
    expected_ports = {'Z': 'N13', 'Z5': 'N965', 'I0': 'io_dcUncached',
                      'I1': 'aGo', 'I2': 'uReload', 'I3': 'aMemOp[8]',
                      'I4': PMA_LSU_SHARED, 'I5': "1'b1"}
    check(store['type'] == load['type'] == 'GTP_LUT6D' and
          store['instance'] == load['instance'] and
          store['output'] == 'Z' and load['output'] == 'Z5' and
          store['ports'] == load['ports'],
          'PMA LSU fused consumer LUT topology is incomplete')
    # The mapper may rotate the six LUT inputs between synthesis contexts
    # (observed v2: identical wiring set on a rotated pin order). The
    # structural contract is the wiring set plus the shared dual-output
    # LUT6D; the randomized functional evaluation below remains the
    # behavior proof and is pin-order independent.
    check(sorted(store['ports'].values()) == sorted(expected_ports.values()) and
          store['ports']['Z'] == 'N13' and store['ports']['Z5'] == 'N965' and
          store['ports']['I5'] == "1'b1",
          'PMA LSU fused consumer wiring differs from the V3.5 contract')
    observed = set()
    count = 0
    for address in sorted(addresses):
        uncached = int(uncacheable(address))
        mapped = pma.evaluate('N7', bits(PMA_ADDRESS, address))
        check(mapped == uncached, 'PMA N7 mismatch at ' + hex(address))
        observed.add(mapped)
        for memop, dc_uncached, ago, reload in itertools.product((0, 1), repeat=4):
            state = {PMA_LSU_SHARED: mapped, 'aMemOp[8]': memop,
                     'io_dcUncached': dc_uncached, 'aGo': ago, 'uReload': reload}
            expected_store = int(bool(memop and uncached))
            expected_load = int(bool(reload or (ago and uncached) or
                                     (dc_uncached and not ago)))
            check(lsu.evaluate('N13', state) == expected_store,
                  'PMA LSU N13 mismatch at ' + hex(address))
            check(lsu.evaluate('N965', state) == expected_load,
                  'PMA LSU N965 mismatch at ' + hex(address))
        count += 1
    check(count > 0 and observed == {0, 1},
          'PMA output corpus lacks both cached and uncached states')
    return dict(address_cases=count, consumer_cases=count * 32,
                consumers=['Lsu.N13', 'Lsu.N965'],
                mapped_outputs={'N7': mapped_output},
                consumer_pma_inputs={'N13': [PMA_LSU_SHARED],
                                     'N965': [PMA_LSU_SHARED]},
                output_values={'N7': sorted(observed)},
                topology='PhysicalMemoryAttributes.N7 -> PmaMmu -> CoreMemory -> Lsu.N13_vname',
                variant='fused_single_output', control_combinations=16)


def audit_pma_supervisor_output(pma, lsu, attr_ports, mmu_ports, lsu_ports, addresses):
    """Check the mapped M/S/U physical MAT cone and its two LSU consumers."""
    virtual = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/_u_lsu_io_pmaDVaddr'
    translated = 'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_physicalAddress'
    translate = pma_translate_source(attr_ports)
    check(set(attr_ports) == {'io_dPaddr', virtual, translated, translate, 'N7'} and
          attr_ports['N7'] == 'attributes/N7' and attr_ports[translate] == 'dTranslate' and
          mmu_ports.get('attributes/N7') == 'u_pma/attributes/N7' and
          lsu_ports.get(PMA_LSU_SHARED) == 'u_pma/attributes/N7',
          'PMA output is disconnected before LSU in supervisor profile')
    check(mmu_ports.get('io_dPaddr') == '_u_pma_io_dPaddr' and
          mmu_ports.get('io_dVaddr') == '_u_lsu_io_pmaDVaddr',
          'Supervisor PMA address inputs differ from the source interface')
    mapped = pma.primitive('N7')
    check(mapped['type'] == 'GTP_LUT6' and mapped['output'] == 'Z' and
          mapped['init'] not in (None, 0, (1 << 64) - 1),
          'PMA output LUT is constant or not a mapped LUT: N7')
    store = lsu.primitive('N23')
    load = lsu.primitive('N972')
    # PDS assigns an unstable _N number to the address-fault LUT output.
    # Bind it by its mapped producer and six source pins instead of one run's
    # generated net name, then check the producer's truth table below.
    # LUT pin assignment is not stable across whole-SoC remapping. Identify
    # the one additional producer beside the five named architectural
    # controls, then prove its wiring and all 64 function values below.
    store_controls = {
        'aMemOp[8]', PMA_LSU_SHARED,
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_io_dAccessFault_T_1',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_accessFault',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_pageFault',
    }
    store_inputs = {store['ports'].get('I' + str(i)) for i in range(6)}
    fault_candidates = store_inputs - store_controls
    check(store_controls <= store_inputs and len(fault_candidates) == 1,
          'Supervisor PMA atomic/fault consumer wiring differs')
    fault_wire = next(iter(fault_candidates))
    check(re.fullmatch(r'_N\d+', fault_wire) and fault_wire in lsu.drivers,
          'Supervisor PMA address-fault producer is missing')
    fault = lsu.primitive(fault_wire)
    fault_sources = (
        'io_pmaDVaddr[30]', 'io_pmaDPaddr[31]',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_physicalAddress[30]',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_physicalAddress[32]',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_physicalAddress[33]',
        translate,
    )
    check(fault['type'] == 'GTP_LUT6' and fault['output'] == 'Z' and
          {fault['ports'].get('I' + str(i)) for i in range(6)} == set(fault_sources),
          'Supervisor PMA address-fault producer wiring differs')
    # Pin ordering varies with whole-chip mapping. The exact six named
    # architectural wires above and all64 native truth values below are
    # required independently of their physical LUT input-pin assignment.
    for pins in itertools.product((0, 1), repeat=6):
        values = dict(zip(fault_sources, pins))
        expected_fault = int(bool(pins[3] and pins[5] or pins[4] and pins[5] or
                                  pins[0] and not pins[1] and not pins[5] or
                                  not pins[1] and pins[2] and pins[5]))
        check(lsu.evaluate(fault_wire, values) == expected_fault,
              'Supervisor PMA address-fault producer truth table differs')
    store_inputs = {store['ports'].get('I' + str(i)) for i in range(6)}
    check(store['type'] == 'GTP_LUT6' and store_inputs == {
        fault_wire, 'aMemOp[8]',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_io_dAccessFault_T_1',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_accessFault',
        'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_pageFault',
        PMA_LSU_SHARED}, 'Supervisor PMA atomic/fault consumer wiring differs')
    load_ports = load['ports']
    simple_load = (load['type'] == 'GTP_LUT4' and load['output'] == 'Z' and
                   {load_ports.get('I' + str(i)) for i in range(4)} ==
                   {'io_dcUncached', 'aGo', 'uReload', PMA_LSU_SHARED})
    packed_load = (load['type'] == 'GTP_LUT6D' and load['output'] == 'Z5' and
                   load_ports.get('I5') == "1'b1" and
                   {load_ports.get('I' + str(i)) for i in range(5)} in (
                   {'io_dcUncached', 'io_sbQueryValid', 'aGo',
                    'uReload', PMA_LSU_SHARED},
                   {'io_dcUncached', 'io_sbQueryValid', 'aGo_cpy',
                    'uReload', PMA_LSU_SHARED}))
    # With the smaller MAC bank, ADS packs the LSU load result alongside an
    # exception OR instead of sbQueryValid. Z5 must be independent of that
    # extra input; the exhaustive functional check below tests both values.
    # Whole-SoC remapping may permute all five inputs of this same Z5
    # packing. Bind the extra input by its actual exception-OR producer;
    # retain the architectural load oracle and both extra-input cofactors.
    exception_controls = {'io_dcUncached', 'aGo', 'uReload', PMA_LSU_SHARED}
    if 'aGo_cpy' in load_ports.values():
        exception_controls = (exception_controls - {'aGo'}) | {'aGo_cpy'}
    exception_extras = ({load_ports.get('I' + str(i)) for i in range(5)} -
                        exception_controls)
    exception_wire = next(iter(exception_extras)) if len(exception_extras) == 1 else ''
    packed_exception_load = (load['type'] == 'GTP_LUT6D' and
        load['output'] == 'Z5' and load_ports.get('I5') == "1'b1" and
        {load_ports.get('I' + str(i)) for i in range(5)} ==
        exception_controls | {exception_wire} and
        exception_wire in lsu.drivers)
    if packed_exception_load:
        exception = lsu.primitive(exception_wire)
        packed_exception_load = (exception['type'] == 'GTP_LUT4' and
            exception['output'] == 'Z' and exception['init'] == 0xfffe and
            {exception['ports'].get('I' + str(i)) for i in range(4)} ==
            {'dExcp[4]', 'dExcp[5]', 'dExcp[8]', 'dExcp[9]'})
    check(simple_load or packed_load or packed_exception_load,
          'Supervisor PMA load consumer wiring differs')
    if (packed_load and 'aGo_cpy' in load_ports.values()) or (
            packed_exception_load and 'aGo_cpy' in load_ports.values()):
        # PDS may duplicate aGo for fanout and pack the load result with an
        # unrelated output. Require the duplicated producer to be identical;
        # then prove Z5 is independent of the extra query input below.
        ago = lsu.primitive('aGo')
        ago_copy = lsu.primitive('aGo_cpy')
        check(ago['type'] == ago_copy['type'] == 'GTP_LUT2' and
              ago['init'] == ago_copy['init'] and
              tuple(ago['ports'].get('I' + str(i)) for i in range(2)) ==
              tuple(ago_copy['ports'].get('I' + str(i)) for i in range(2)),
              'Supervisor PMA load aGo copy differs')
    observed = set()
    for address in sorted(addresses):
        expected = int(uncacheable(address))
        other = 0x10000000 if expected else 0x80000000
        for mode in (0, 1):
            values = bits('io_dPaddr', address)
            values.update(bits(virtual, other if mode else address, 34))
            values.update(bits(translated, address if mode else other, 34))
            values[translate] = mode
            mapped_value = pma.evaluate('N7', values)
            check(mapped_value == expected,
                  'Supervisor PMA mapped MAT mismatch at ' + hex(address))
            observed.add(mapped_value)
        for dc_uncached, ago, reload in itertools.product((0, 1), repeat=3):
            state = {PMA_LSU_SHARED: expected, 'io_dcUncached': dc_uncached,
                     'aGo': ago, 'aGo_cpy': ago, 'uReload': reload}
            expected_load = int(bool(reload or (ago and expected) or
                                     (dc_uncached and not ago)))
            for query in ((0, 1) if packed_load or packed_exception_load else (0,)):
                state['io_sbQueryValid'] = query
                if packed_exception_load:
                    state[exception_wire] = query
                check(lsu.evaluate('N972', state) == expected_load,
                      'Supervisor PMA load consumer mismatch at ' + hex(address))
        fault_free_atomic = {fault_wire: 0, 'aMemOp[8]': 1,
            'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_io_dAccessFault_T_1': 0,
            'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_accessFault': 0,
            'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_pageFault': 0,
            PMA_LSU_SHARED: expected}
        check(lsu.evaluate('N23', fault_free_atomic) == expected,
              'Supervisor PMA atomic consumer mismatch at ' + hex(address))
    check(observed == {0, 1}, 'Supervisor PMA corpus lacks both MAT values')
    return dict(address_cases=len(addresses), consumer_cases=len(addresses) * 32,
                consumers=['Lsu.N23', 'Lsu.N972'], mapped_outputs={'N7': mapped},
                consumer_pma_inputs={'N23': [PMA_LSU_SHARED], 'N972': [PMA_LSU_SHARED]},
                output_values={'N7': sorted(observed)},
                topology='PhysicalMemoryAttributes.N7 -> PmaMmu -> CoreMemory -> Lsu.N23/N972',
                variant='supervisor_fused_single_output', control_combinations=16)


def audit_pma_consumers(source, addresses):
    """Prove actual PMA outputs reach both LSU load and store decisions."""
    if pma_output_names(source) == ('N7',):
        return audit_pma_single_output(source, addresses)
    pma = Cone(source, 'PhysicalMemoryAttributes')
    lsu = Cone(source, 'Lsu')
    attr_ports = instance_ports(source, 'PmaMmu', 'PhysicalMemoryAttributes', 'attributes')
    mmu_ports = instance_ports(source, 'CoreMemory', 'PmaMmu', 'u_pma')
    lsu_ports = instance_ports(source, 'CoreMemory', 'Lsu', 'u_lsu')
    pma_outputs = pma_output_names(source)
    output_set = set(pma_outputs)
    check(set(attr_ports) == output_set | {PMA_ADDRESS},
          'PhysicalMemoryAttributes instance ports do not match its interface')
    for name in pma_outputs:
        check(attr_ports.get(name) == mmu_ports.get(name) == lsu_ports.get(name) == name,
              'PMA output is disconnected before LSU: ' + name)
    check(lsu_ports.get('io_pmaDPaddr') == '_u_pma_io_dPaddr',
          'LSU PMA address is not the shared CoreMemory address')
    mmu_address = mmu_ports.get(PMA_ADDRESS, '')
    attr_address = attr_ports.get(PMA_ADDRESS, '')
    for bit in range(16, 32):
        check(mmu_address.count('_u_pma_io_dPaddr[' + str(bit) + ']') == 1,
              'PmaMmu address bit is disconnected: ' + str(bit))
    for bit in range(16, 30):
        check(attr_address.count(PMA_ADDRESS + '[' + str(bit) + ']') == 1,
              'PhysicalMemoryAttributes address bit is disconnected: ' + str(bit))
    consumer_pma_inputs = {}
    for target, fixed, pma_count in (
        ('N13', {'aMemOp[8]', 'io_pmaDPaddr[30]', 'io_pmaDPaddr[31]'}, 3),
        ('N965', {'io_dcUncached', 'aGo', 'uReload',
                  'io_pmaDPaddr[30]', 'io_pmaDPaddr[31]'}, 1),
    ):
        cell = lsu.primitive(target)
        check(cell['type'].startswith('GTP_LUT'),
              'PMA LSU consumer is not a mapped LUT: ' + target)
        inputs = [cell['ports'].get('I' + str(bit)) for bit in range(6)]
        direct_pma = output_set.intersection(inputs)
        check(None not in inputs and len(set(inputs)) == 6 and
              len(direct_pma) == pma_count and set(inputs) == fixed | direct_pma,
              'PMA LSU consumer direct inputs are incomplete: ' + target)
        check(fixed | direct_pma <= lsu.fanin(target),
              'PMA LSU consumer fan-in is incomplete: ' + target)
        consumer_pma_inputs[target] = sorted(direct_pma)
    check(not (set(consumer_pma_inputs['N13']) & set(consumer_pma_inputs['N965'])) and
          set(consumer_pma_inputs['N13'] + consumer_pma_inputs['N965']) == output_set,
          'PMA outputs are not assigned to both LSU consumers')
    mapped_outputs = {}
    for name in pma_outputs:
        cell = pma.primitive(name)
        lut = re.fullmatch(r'GTP_LUT([1-6])D?', cell['type'])
        check(lut is not None and cell['init'] is not None,
              'PMA output is not a mapped LUT: ' + name)
        width = 5 if cell['output'] == 'Z5' else int(lut[1])
        mask = (1 << (1 << width)) - 1
        check((cell['init'] & mask) not in (0, mask), 'PMA output LUT is constant: ' + name)
        mapped_outputs[name] = cell
    observed = {name: set() for name in pma_outputs}
    count = 0
    for address in sorted(addresses):
        state = bits(PMA_ADDRESS, address)
        outputs = {name: pma.evaluate(name, state) for name in pma_outputs}
        for name, value in outputs.items():
            observed[name].add(value)
        lsu_state = bits('io_pmaDPaddr', address)
        lsu_state.update(outputs)
        lsu_state.update({'aMemOp[8]': 1, 'io_dcUncached': 0, 'aGo': 1, 'uReload': 0})
        expected = int(uncacheable(address))
        for target in ('N13', 'N965'):
            check(lsu.evaluate(target, lsu_state) == expected,
                  'PMA LSU ' + target + ' mismatch at ' + hex(address))
        count += 1
    check(count > 0 and all(values == {0, 1} for values in observed.values()),
          'PMA output corpus lacks both cached and uncached states')
    return dict(address_cases=count, consumer_cases=count * 2,
                consumers=['Lsu.N13', 'Lsu.N965'], mapped_outputs=mapped_outputs,
                consumer_pma_inputs=consumer_pma_inputs,
                output_values={name: sorted(values) for name, values in observed.items()},
                topology='PhysicalMemoryAttributes -> PmaMmu -> CoreMemory -> Lsu')


def bind_registered_frontend_controls(frontend, source):
    """Bind the selected metadata through an actual call consumer.

    ADS may fold isCall into the RAS push LUT. In that shape, prove every
    cofactor of the observed push output, then check both selected metadata
    cones against the original instruction oracle in audit().
    """
    from ads_bdd import cone_leaves
    returns={'pdReturns_'+str(i) for i in range(4)}
    calls={'pdCalls_'+str(i) for i in range(4)}
    if 'isCall' in frontend.drivers:
        cell=frontend.drivers['isCall'][0]
        candidates=[wire for pin,wire in cell['ports'].items() if pin.startswith('I') and
                    returns<=cone_leaves(frontend,[wire])]
        check(len(candidates)==1,'Return selector must be uniquely bound through the call consumer')
        return dict(mode='named_call',return_selector=candidates[0],call_target='isCall',truth_cases=0)
    body=re.search(r'(?ms)^module CoreFrontend\s.*?^endmodule',source)
    ras=re.findall(r'(?s)\bRas\s+ras\s*\((.*?)\);',body.group())
    check(len(ras)==1,'Folded call requires exactly one actual RAS instance')
    pins=re.findall(r'\.io_specPush\s*\(([^()]*)\)',ras[0])
    check(len(pins)==1,'Folded call missing actual RAS push consumer')
    target=signal(pins[0])
    check(target in frontend.drivers,'Folded RAS push has no mapped driver')
    node,port=frontend.drivers[target]
    check(re.fullmatch(r'GTP_LUT[1-6]D?',node['kind']) is not None,'Folded RAS push must be a LUT')
    inputs={wire for pin,wire in node['ports'].items() if pin.startswith('I') and wire not in ("1'b0","1'b1")}
    check({'pdAccept','found'}<=inputs,'Folded RAS push lost acceptance/found consumers')
    selected_returns=[wire for wire in inputs if returns<=cone_leaves(frontend,[wire])]
    selected_calls=[wire for wire in inputs if calls<=cone_leaves(frontend,[wire])]
    check(len(selected_returns)==len(selected_calls)==1,'Folded RAS selected metadata must be uniquely bound')
    ret,call=selected_returns[0],selected_calls[0]
    check(ret!=call,'Folded RAS return/call selectors must remain independent')
    inputs=sorted(inputs);count=0
    for values in itertools.product(range(2),repeat=len(inputs)):
        state=dict(zip(inputs,values))
        expected=(1-state[ret])&state[call]&state['found']&state['pdAccept']
        check(frontend.evaluate(target,state)==expected,'Folded RAS push truth function differs')
        count+=1
    return dict(mode='folded_ras_push',return_selector=ret,call_target=call,push_target=target,
                truth_cases=count,consumer='CoreFrontend.ras.io_specPush',mapped_output=port)


def audit(path):
    original_bytes = path.read_bytes()
    source = original_bytes.decode('utf-8')
    frontend = Cone(source, 'CoreFrontend')
    frontend_ib_binding = None
    ib_rf_proof = None
    # Native sharing may move PD decode terms into the actual IB child and
    # export them back to the parent. Resolve that exact hierarchy instead of
    # assigning an arbitrary value to its new port or ignoring the dependency.
    if re.search(r'(?m)^module\s+PangoFallbackTargetPad\b', source):
        from ads_frontend_ib_cone import bind as bind_frontend_ib
        frontend, _, frontend_ib_binding = bind_frontend_ib(source)
        from audit_ib_rf_metadata_ads import audit as audit_ib_rf
        ib_rf_proof = audit_ib_rf(source)
    rsmem = Cone(source, 'RsMem')
    mmu = Cone(source, 'PmaMmu')
    # Sample all line boundaries, descriptor lengths, branch positions and types,
    # simultaneous candidates, and illegal conditional/JALR opcode encodings.
    opcodes = [0x13, 0x6f, 0x63, 0x1063, 0x2063, 0x67, 0x1067]
    vectors = {tuple([opcode if i == lane else 0x13 for i in range(4)])
               for lane in range(4) for opcode in opcodes}
    vectors.update(itertools.product([0x13, 0x6f, 0x63, 0x67], repeat=4))
    # A return consumes the selected JALR decode even when ADS folds the
    # selectedJalr wire into its users. Include positive and negative return
    # operands for every candidate lane, not just zero-filled instructions.
    return_vectors = set()
    for lane, rd, rs1 in itertools.product(range(4), (0, 1, 5), (0, 1, 5)):
        instruction = (rs1 << 15) | (rd << 7) | 0x67
        return_vectors.add(tuple(instruction if i == lane else 0x13 for i in range(4)))
    return_vectors.difference_update(vectors)
    has_selected_jalr = 'selectedJalr' in frontend.drivers or 'selectedJalr' in frontend.aliases
    registered_metadata = any('pdReturns_' + str(i) in frontend.drivers for i in range(4))
    metadata_proof = None
    return_selector = None
    if registered_metadata:
        from audit_frontend_metadata_ads import audit_metadata
        metadata_proof = audit_metadata(frontend)
        control_binding=bind_registered_frontend_controls(frontend,source)
        return_selector=control_binding['return_selector']
        metadata_proof['control_consumer_binding']=control_binding
    check(registered_metadata or has_selected_jalr or 'isReturn' in frontend.drivers,
          'Frontend lost both selected JALR and its return consumer')
    if not has_selected_jalr and not registered_metadata:
        for lane in range(4):
            check('jalr_' + str(lane) in frontend.drivers,
                  'Frontend JALR lane decode is missing: ' + str(lane))
    frontend_cases = 0
    return_cases = 0
    for instructions, pc_word, length in itertools.product(sorted(vectors | return_vectors), range(8), range(5)):
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
            if registered_metadata:
                rd, rs1 = (instruction >> 7) & 31, (instruction >> 15) & 31
                values['pdReturns_' + str(i)] = int(jalr and rd == 0 and rs1 in (1, 5))
                values['pdCalls_' + str(i)] = int((jal or jalr) and rd in (1, 5))
            branches.append(int(i < min(4, 8 - pc_word) and i < length and any(types[-1])))
        first = branches.index(1) if any(branches) else 0
        expected = {'branch' + str(i): branch for i, branch in enumerate(branches)}
        expected.update(found=int(any(branches)), selectedJal=int(types[first][0]),
                        selectedCond=int(types[first][1]))
        if registered_metadata:
            selected_return = values['pdReturns_' + str(first)]
            expected[return_selector] = selected_return
            expected[control_binding['call_target']] = (values['pdCalls_' + str(first)]
                if control_binding['mode']=='folded_ras_push' else
                int(bool(any(branches) and not selected_return and values['pdCalls_' + str(first)])))
        elif has_selected_jalr:
            expected['selectedJalr'] = int(types[first][2])
        else:
            selected = instructions[first]
            expected['isReturn'] = int(bool(any(branches) and types[first][2] and
                                       (selected >> 7) & 31 == 0 and
                                       (selected >> 15) & 31 in (1, 5)))
            expected.update({'jalr_' + str(i): int(type_[2])
                             for i, type_ in enumerate(types)})
        # Integrated ADS shares LUT terms with these three register outputs.
        # Enumerate every cofactor instead of assuming unbound state is zero:
        # the decoded branch/priority/type results must remain independent.
        for extra in itertools.product(range(2), repeat=3):
            state = dict(values)
            state.update(zip(('trainValid', 'trainLength[1]', 'pdHistTaken'), extra))
            cache = {}
            for target, value in expected.items():
                check(frontend.evaluate(target, state, cache) == value,
                      'Frontend mismatch ' + repr((target, instructions, pc_word, length, extra)))
            if instructions in return_vectors:
                return_cases += 1
            else:
                frontend_cases += 1
    check(frontend_cases == 85760 and return_cases == 10240,
          'Frontend and return-control vector counts changed')
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
    pma_contract = audit_pma_consumers(source, addresses)
    pma_cases = pma_contract['address_cases']
    hint_cases = 0
    supervisor_pma = pma_contract.get('variant') == 'supervisor_fused_single_output'
    instruction_fault_target = 'N712[6]' if supervisor_pma else 'N711[6]'
    instruction_page_target = 'N712[7]'
    if registered_metadata:
        fault_targets = []
        for bit in [6, 7]:
            ff, port = frontend.drivers['fcFaults[' + str(bit) + ']']
            check(port == 'Q' and ff['kind'].startswith('GTP_DFF') and ff['ports']['CLK'] == 'clock',
                  'Instruction fault capture FF/clock is missing')
            fault_targets.append(ff['ports']['D'])
        instruction_fault_target, instruction_page_target = fault_targets
    for address in sorted(addresses):
        permitted = bool(address >> 31) or (address >> 30 == 0 and not device(address))
        if supervisor_pma:
            # The S/Sv32 mapper may either expose the direct access LUT as
            # _N105149 or fold it into the later _N99436 fault decision.
            # Evaluate the actual mapped producer for every address.
            physical = dict(bits('io_iVaddr', address), **bits('io_iPaddr', address))
            physical.update(bits('io_satp', 0))
            physical.update(bits('io_privilege', 3, 2))
            physical.update(bits('_tlb_io_response_bits_physicalAddress', address, 34))
            physical.update({'N92': 0, '_tlb_io_response_bits_accessFault': 0})
            if '_N105149' in mmu.drivers:
                access_fault = mmu.evaluate('_N105149', physical)
                values = {'_N105149': access_fault,
                          'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/N92': 0,
                          'io_instructionAccept': 1, 'io_ifu_pma_vaddr[0]': 0,
                          'io_ifu_pma_vaddr[1]': 0}
                page_values = {'_N411155': access_fault,
                               'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/N92': 1,
                               'io_ifu_pma_req': 1, 'io_ifu_pma_vaddr[0]': 0,
                               'io_ifu_pma_vaddr[1]': 0}
            else:
                # PDS may rotate the frontend LUT pins and regenerate the
                # fault net name. Bind its one mapped PMA producer by wiring.
                fault_candidates = [wire for wire in
                    frontend.primitive(instruction_fault_target)['ports'].values()
                    if wire in mmu.drivers]
                check(len(fault_candidates) == 1 and
                      re.fullmatch(r'_N\d+', fault_candidates[0]),
                      'Supervisor instruction fault producer is missing')
                fault_wire = fault_candidates[0]
                physical.update({'iTranslate': 0, 'iResponse': 0,
                                 '_tlb_io_response_bits_pageFault': 0})
                access_fault = mmu.evaluate(fault_wire, physical)
                values = {fault_wire: access_fault,
                          'io_instructionAccept': 1, 'io_ifu_pma_vaddr[0]': 0,
                          'io_ifu_pma_vaddr[1]': 0}
                page_values = {
                    'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_pageFault': 1,
                    'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/iResponse': 1,
                    'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/iTranslate': 1,
                    'io_ifu_pma_req': 1, 'io_ifu_pma_vaddr[0]': 0,
                    'io_ifu_pma_vaddr[1]': 0}
            fault = frontend.evaluate(instruction_fault_target, values)
            check(frontend.evaluate(instruction_page_target, page_values) == 1,
                  'Supervisor instruction page-fault consumer disconnected')
        else:
            n17 = mmu.evaluate('N17', bits('u_cpu/u_cpu_wrapper/u_cpu/core/_memory_io_pma_i_paddr', address))
            # ADS factors the high-RAM allowance into the frontend consumer.
            values = bits('io_pma_i_paddr', address)
            values.update({'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/N17': n17, 'pfAdvance': 1})
            fault = frontend.evaluate(instruction_fault_target, values)
        check(fault == int(not permitted), 'PMA instruction-access mismatch at ' + hex(address))
        for lane, valid, refresh in itertools.product(range(2), range(2), range(2)):
            suffix = '_' + str(lane)
            values = bits('pairKeyA' + suffix, address >> 5, 27)
            values.update({'s0ValValidA' + suffix: valid, 's0KeyRefreshA' + suffix: refresh})
            if supervisor_pma:
                values['io_dataTranslationActive'] = 0
            actual = rsmem.evaluate('scanKnownCached' + suffix, values)
            check(actual == int(valid and not refresh and not uncacheable(address)),
                  'RsMem hint mismatch ' + repr((lane, hex(address), valid, refresh)))
            if supervisor_pma:
                values['io_dataTranslationActive'] = 1
                check(rsmem.evaluate('scanKnownCached' + suffix, values) == 0,
                      'RsMem hint must be disabled during address translation')
            hint_cases += 1
    control_names = ['branch0', 'branch1', 'branch2', 'branch3', 'found',
                     'selectedJal', 'selectedCond', 'pdRepair']
    control_names += [control_binding['call_target'], return_selector] if registered_metadata else ['selectedJalr'] if has_selected_jalr else [
        'isReturn', 'jalr_0', 'jalr_1', 'jalr_2', 'jalr_3']
    controls = {name: frontend.primitive(name) for name in control_names}
    for name, cell in controls.items():
        check(cell['type'].startswith('GTP_LUT'), 'Unexpected control primitive ' + name)
        width = 5 if cell['output'] == 'Z5' else int(re.fullmatch(r'GTP_LUT([1-6])D?', cell['type'])[1])
        mask = (1 << (1 << width)) - 1
        check((cell['init'] & mask) not in (0, mask), 'Constant control ' + name)
    repair_inputs = ['branch0', 'branch1', 'branch2', 'branch3', 'found', 'selectedJal', 'selectedCond']
    check(set(repair_inputs) <= frontend.fanin('pdRepair'), 'Predecode controls missing from repair fan-in')
    check(path.read_bytes() == original_bytes, 'Netlist changed while its control cones were being checked')
    return dict(schema_version=1, status='PASS', profile='CPU integrated RV32IMA without obsolete DMA carve-out',
                scope='selected post-ADS combinational LUT cones; not whole-design gate simulation, STA or board acceptance',
                netlist_sha256=hashlib.sha256(original_bytes).hexdigest(),
                frontend_cases=frontend_cases, return_cases=return_cases,
                pma_address_cases=pma_cases, rsmem_hint_cases=hint_cases,
                frontend_extra_state_cofactors=['trainValid', 'trainLength[1]', 'pdHistTaken'],
                registered_metadata_proof=metadata_proof, registered_return_selector=return_selector,
                frontend_ib_binding=frontend_ib_binding, ib_rf_metadata_contract=ib_rf_proof,
                instruction_fault_targets=[instruction_fault_target, instruction_page_target],
                pma_device_windows=['02000000..0200ffff', '1fe00000..1fefffff'],
                boot_bram_cached='1c000000..1c01ffff, including 1c018000..1c01bfff', uncached_alias='80000000..bfffffff',
                controls=controls, pma_contract=pma_contract,
                repair_structural_fanin=repair_inputs,
                refresh=[rsmem.primitive('s0KeyRefreshA_' + str(i)) for i in range(2)],
                hint=[rsmem.primitive('scanKnownCached_' + str(i)) for i in range(2)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input-snapshot', type=Path, help='Optional actual PDS input snapshot for evidence binding')
    args = parser.parse_args()
    try:
        result = audit(args.netlist)
        if args.input_snapshot:
            snapshot_bytes = args.input_snapshot.read_bytes()
            snapshot = json.loads(snapshot_bytes.decode('utf-8'))
            result['input_snapshot_sha256'] = hashlib.sha256(snapshot_bytes).hexdigest()
            result['input_snapshot_run_id'] = snapshot['run_id']
            result['cpu_rtl_sha256'] = snapshot['inputs']['rtl/cpu/CoreTop.sv']
            result['cpu_emit_config_sha256'] = snapshot['inputs']['rtl/cpu/emit-config.json']
            result['production_rom_sha256'] = snapshot['inputs']['artifacts/bootrom.hex']
            if 'scripts/audit_ib_rf_metadata_ads.py' in snapshot['inputs']:
                ib=result.get('ib_rf_metadata_contract')
                source_path=args.input_snapshot.resolve().parent.parent/'rtl/cpu/CoreTop.sv'
                source_bytes=source_path.read_bytes()
                check(hashlib.sha256(source_bytes).hexdigest()==snapshot['inputs']['rtl/cpu/CoreTop.sv'],
                      'IB RF CPU source binding differs')
                required=('io_popRfMeta_0' in source_bytes.decode('utf-8') or
                          'PangoFallbackTargetPad' in source_bytes.decode('utf-8'))
                if required:
                    check(ib and ib['status']=='IB_RF_METADATA_CAPTURE_ADS_PASS_NOT_STA_OR_BOARD' and
                          ib['metadata_storage_bits']==64,'IB RF metadata native proof required')
                    ib['required']=True
                else:
                    check(ib is None,'Undeclared IB RF metadata in native netlist')
                    ib=dict(status='LEGACY_CPU_WITHOUT_IB_RF_METADATA_NO_CAPTURE_CLAIM',required=False)
                    result['ib_rf_metadata_contract']=ib
                ib['source_sha256']={}
                for name in ['audit_ib_rf_metadata_ads.py','ads_frontend_ib_cone.py','ads_bdd.py']:
                    actual=hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    check(snapshot['inputs']['scripts/'+name]==actual,'IB RF checker binding differs: '+name)
                    ib['source_sha256'][name]=actual
            if 'scripts/audit_fallback_target_pad_ads.py' in snapshot['inputs']:
                from audit_fallback_target_pad_ads import bind_result as bind_fallback_target_pad
                result['fallback_target_pad_contract'] = bind_fallback_target_pad(args.netlist, args.input_snapshot)
                check(result['fallback_target_pad_contract']['netlist_sha256'] == result['netlist_sha256'],
                      'Netlist changed between CPU and fallback-target audits')
            release=tuple(int(part) for part in snapshot['release'].lstrip('Vv').split('.'))
            if release >= (6,5):
                # A separate module keeps the V3.5 proof boundary explicit;
                # it shares this file's mapped-LUT parser, not the acceptance
                # result. Bind its exact bytes to the same frozen snapshot.
                from audit_rob_owner_ads import audit as audit_rob, bind_result
                rob=audit_rob(args.netlist.read_text(encoding='utf-8'))
                check(rob['status']=='PASS','ROB mapped contract did not pass: '+rob['status'])
                result['rob_owner_contract']=bind_result(rob,args.netlist,args.input_snapshot)
            if 'scripts/audit_uart_tx_pad_ads.py' in snapshot['inputs']:
                # Capability is frozen with the new hold-fix recipe. Earlier
                # V6.5 snapshots keep their original, narrower audit scope.
                from audit_uart_tx_pad_ads import audit as audit_uart, bind_result as bind_uart
                uart = audit_uart(args.netlist.read_text(encoding='utf-8'))
                result['uart_tx_pad_contract'] = bind_uart(uart, args.netlist, args.input_snapshot)
                check(result['uart_tx_pad_contract']['vm_sha256'] == result['netlist_sha256'],
                      'Netlist changed between CPU and UART audits')
        result['audit_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except Exception as error:
        result = dict(status='FAIL', error=str(error))
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        raise
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('ADS_CONTROLS_PASS frontend={frontend_cases} returns={return_cases} '
          'pma={pma_address_cases} hints={rsmem_hint_cases}'.format(**result))


if __name__ == '__main__':
    main()
