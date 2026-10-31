#!/usr/bin/env python3
"""Negative PMA wiring/LUT fixtures against a real same-run ADS VM."""
import argparse
import hashlib
import re
from pathlib import Path

from audit_cpu_ads import (PMA_LSU_SHARED, Cone, audit_pma_consumers,
                           instance_ports, module_text, pma_output_names)
from test_cpu_ads import change_init


ADDRESSES = {0, 0x02000000, 0x02010000, 0x1c018000,
             0x1fe00000, 0x1ff00000, 0x80000000, 0xc0000000}


def replace_module(source, original, replacement):
    if source.count(original) != 1:
        raise AssertionError('ADS fixture module occurrence is ambiguous')
    return source.replace(original, replacement, 1)


def expect_rejection(name, source, fragment):
    try:
        audit_pma_consumers(source, ADDRESSES)
    except ValueError as error:
        if fragment not in str(error):
            raise AssertionError(f'{name}: wrong failure: {error}') from error
    else:
        raise AssertionError(f'{name}: damaged PMA netlist was accepted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', required=True, type=Path)
    args = parser.parse_args()
    original = args.netlist.read_bytes()
    source = original.decode('utf-8')
    result = audit_pma_consumers(source, ADDRESSES)
    fused_pma = pma_output_names(source) == ('N7',)
    expected_cases = 32 * len(ADDRESSES) if fused_pma else 2 * len(ADDRESSES)
    if result['address_cases'] != len(ADDRESSES) or result['consumer_cases'] != expected_cases:
        raise AssertionError('PMA positive fixture did not cover both consumers')

    memory = module_text(source, 'CoreMemory')
    lsu = re.search(r'\bLsu\s+u_lsu\s*\((.*?)\);', memory, re.S)
    if not lsu:
        raise AssertionError('Missing PMA-to-LSU fixture instance')
    if fused_pma:
        if instance_ports(source, 'CoreMemory', 'Lsu', 'u_lsu').get(PMA_LSU_SHARED) != 'u_pma/attributes/N7':
            raise AssertionError('Unknown fused PMA-to-LSU fixture shape')
        pattern = r'\.' + re.escape('\\' + PMA_LSU_SHARED) + r'\s*\(\s*(\\u_pma/attributes/N7)\s*\)'
        matches = list(re.finditer(pattern, lsu.group()))
        if len(matches) != 1:
            raise AssertionError('Could not identify fused PMA-to-LSU wire')
        begin, end = matches[0].span(1)
        damaged_lsu = lsu.group()[:begin] + "1'b0" + lsu.group()[end:]
    else:
        pma_outputs = set(pma_output_names(source))
        n965_inputs = set(Cone(source, 'Lsu').primitive('N965')['ports'].values())
        uncached_outputs = pma_outputs & n965_inputs
        if len(uncached_outputs) != 1:
            raise AssertionError('Unknown PMA uncached-output LUT shape')
        uncached_output = uncached_outputs.pop()
        if instance_ports(source, 'CoreMemory', 'Lsu', 'u_lsu').get(uncached_output) != uncached_output:
            raise AssertionError('Unknown PMA-to-LSU fixture shape')
        connection = '.' + uncached_output + ' (' + uncached_output + ')'
        damaged_lsu = lsu.group().replace(connection, '.' + uncached_output + " (1'b0)", 1)
    if damaged_lsu == lsu.group():
        raise AssertionError('Could not disconnect PMA-to-LSU wire')
    damaged_memory = memory.replace(lsu.group(), damaged_lsu, 1)
    expect_rejection('consumer_wire_cut', replace_module(source, memory, damaged_memory),
                     'PMA output is disconnected before LSU')

    attributes = module_text(source, 'PhysicalMemoryAttributes')
    damaged_attributes, count = re.subn(r"\.INIT\(64'b[01]{64}\)",
                                       ".INIT(64'b" + '0' * 64 + ')', attributes, count=1)
    if count != 1:
        raise AssertionError('Could not force one PMA LUT to zero')
    expect_rejection('pma_lut_stuck_zero', replace_module(source, attributes, damaged_attributes),
                     'PMA output LUT is constant')
    negative_cases = 2
    if fused_pma and 'N972' in Cone(source, 'Lsu').drivers:
        store = Cone(source, 'Lsu').primitive('N23')
        named = {'aMemOp[8]', PMA_LSU_SHARED,
            'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_io_dAccessFault_T_1',
            'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_accessFault',
            'u_cpu/u_cpu_wrapper/u_cpu/core/memory/u_pma/_tlb_io_response_bits_pageFault'}
        fault = ({store['ports'].get('I'+str(i)) for i in range(6)} - named).pop()
        producer = Cone(source, 'Lsu').primitive(fault)
        expect_rejection('address_fault_truth_bit_corrupted',
                         change_init(source, 'Lsu', fault, producer['init'] ^ 1),
                         'Supervisor PMA address-fault producer truth table differs')
        negative_cases += 1
        # Exercise the packing change that exposed a fixed-I0 assumption:
        # swap the atomic and address-fault input pins, reindex INIT, and
        # require semantic equivalence; the same wiring without reindexing
        # must still fail the architectural consumer checks.
        fault_pin = next(i for i in range(6) if store['ports']['I'+str(i)] == fault)
        atomic_pin = next(i for i in range(6) if store['ports']['I'+str(i)] == 'aMemOp[8]')
        lsu_body = module_text(source, 'Lsu')
        instance = re.search(r'\\?' + re.escape(store['instance']) + r'\s*\((.*?)\);', lsu_body, re.S)
        if not instance:
            raise AssertionError('Missing atomic LUT for input permutation fixture')
        connections = instance[1]
        swapped = re.sub(r'\.I([0-5])\s*\(',
            lambda m: '.I'+str(atomic_pin if int(m[1]) == fault_pin else
                              fault_pin if int(m[1]) == atomic_pin else int(m[1]))+' (', connections)
        begin,end = instance.span(1)
        swapped_source = replace_module(source,lsu_body,lsu_body[:begin]+swapped+lsu_body[end:])
        remapped_init = 0
        for index in range(64):
            old_index = index
            if ((index >> fault_pin) ^ (index >> atomic_pin)) & 1:
                old_index ^= (1 << fault_pin) | (1 << atomic_pin)
            remapped_init |= ((store['init'] >> old_index) & 1) << index
        audit_pma_consumers(change_init(swapped_source, 'Lsu', 'N23', remapped_init), ADDRESSES)
        expect_rejection('atomic_fault_pin_swap_without_init', swapped_source,
                         'Supervisor PMA atomic consumer mismatch')
        negative_cases += 1
        load = Cone(source, 'Lsu').primitive('N972')
        # Both original aGo and its proved duplicate are legal packings. The
        # unused query input must not influence Z5 in either variant. Flip one
        # low cofactor bit to prove the truth-table gate still rejects damage.
        expect_rejection('load_cofactor_corrupted',
                         change_init(source, 'Lsu', 'N972', load['init'] ^ 1),
                         'Supervisor PMA load consumer mismatch')
        negative_cases += 1
    if hashlib.sha256(args.netlist.read_bytes()).digest() != hashlib.sha256(original).digest():
        raise AssertionError('Source ADS VM changed during PMA fixtures')
    print('CPU_ADS_PMA_NEGATIVE_FIXTURES_PASS cases=' + str(negative_cases) +
          ' positive_addresses=' + str(len(ADDRESSES)))


if __name__ == '__main__':
    main()
