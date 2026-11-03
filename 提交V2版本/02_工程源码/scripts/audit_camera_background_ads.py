"""Evaluate the background camera control cones in the actual ADS netlist.

This is a pre-route structural/Boolean check, not a timing or board result.
Unknown mapped cells and missing registers fail closed.
"""
import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path

from audit_cpu_ads import Cone, check, instance_ports, signal


MODE_PORTS = {
    'sys_clk': 'sys_clk', 'sys_resetn': 'sys_resetn',
    'ddr_clk': 'ddr_clk', 'ddr_resetn': 'ddr_resetn',
    'requested_enable': 'camera_control_enable_cpu',
    'background_request': 'camera_background_request_sys',
    'frame_valid_sys': 'camera_frame_valid_cpu', 'gui_enable_sys': 'fb_enable_sys',
    'gui_buffer_sys': 'fb_requested_buffer_sys',
    'camera_buffer_sys': 'camera_published_buffer_sys',
    'session_idle_ddr': 'camera_buffer_idle_ddr',
    'writer_idle_ddr': 'camera_writer_idle_ddr',
    'control_enable_ddr': 'camera_control_enable_d2',
    'effective_enable_sys': 'camera_control_enable_effective_sys',
    'background_active_ddr': 'camera_background_active_ddr',
    'background_active_sys': 'camera_background_active_sys',
    'camera_preview_sys': 'camera_scanout_enable_sys',
    'dma_enable_sys': 'fb_dma_enable_sys',
    'dma_buffer_sys': 'fb_dma_requested_buffer_sys',
}


def resolve(cone, name):
    seen = set()
    name = signal(name)
    while name in cone.aliases:
        check(name not in seen, 'Alias cycle: ' + name)
        seen.add(name)
        name = cone.aliases[name]
    return name


def register(cone, name, clock):
    target = resolve(cone, name)
    check(target not in ("1'b0", "1'b1"), 'Register collapsed to a constant: ' + name)
    if target not in cone.drivers:
        matches = [(q, n) for q, (n, p) in cone.drivers.items() if p == 'Q' and
                   n['name'] in (name, name + '_vname')]
        check(len(matches) == 1, 'Missing/ambiguous mapped register: ' + name)
        target, _ = matches[0]
    node, port = cone.drivers.get(target, ({}, None))
    check(port == 'Q' and node['kind'] in
          ('GTP_DFF_C', 'GTP_DFF_CE', 'GTP_DFF_P', 'GTP_DFF_PE'),
          'Missing supported retained register: ' + name)
    check(node['ports']['CLK'] == clock, 'Wrong register clock: ' + name)
    check(all(resolve(cone, node['ports'][pin]) != "1'b1" for pin in ('C', 'P')
              if pin in node['ports']), 'Register is permanently reset: ' + name)
    if name != target:
        cone.aliases[name] = target
    return target, node


def state(cone):
    # Boolean transition proofs below run with reset deasserted. Integrated
    # reset bindings are checked separately; RTL regression exercises reset.
    values = {name: 0 for name, (node, port) in cone.drivers.items() if port == 'Q'}
    for node, port in cone.drivers.values():
        if port == 'Q':
            for pin in ('C', 'P'):
                if pin in node['ports']:
                    values[node['ports'][pin]] = 0
    return values


def next_value(cone, name, values, clock):
    target, node = register(cone, name, clock)
    ports = node['ports']
    for reset in ('C', 'P'):
        if reset in ports and cone.evaluate(ports[reset], values):
            return int(reset == 'P')
    if 'CE' in ports and not cone.evaluate(ports['CE'], values):
        return values[target]
    return cone.evaluate(ports['D'], values)


def audit_mode(cone, expanded_writer=False):
    chains = [('background_request_d1', 'background_request', 'ddr_clk'),
              ('background_request_d2', 'background_request_d1', 'ddr_clk'),
              ('background_ack_s1', 'background_active_ddr', 'sys_clk'),
              ('background_ack_s2', 'background_ack_s1', 'sys_clk')]
    for target, source, clock in chains:
        q, node = register(cone, target, clock)
        if source == 'background_ack_s1':
            register(cone, source, clock)
        check(resolve(cone, node['ports']['D']) == resolve(cone, source) and
              'CE' not in node['ports'], 'Broken two-stage mode handshake: ' + target)
    ack, _ = register(cone, 'background_ack_s2', 'sys_clk')
    names = ('requested_enable', 'background_request', 'frame_valid_sys',
             'gui_enable_sys', 'gui_buffer_sys', 'camera_buffer_sys')
    cases = 0
    for values in itertools.product((0, 1), repeat=7):
        env = dict(zip(names + (ack,), values))
        en, request, valid, gui_en, gui_bank, cam_bank, active = values
        effective = int(en and request == active)
        preview = int(effective and valid and not active)
        expected = (active, effective, preview, 1 if preview else gui_en,
                    cam_bank if preview else gui_bank)
        for output, value in zip(('background_active_sys', 'effective_enable_sys',
                                  'camera_preview_sys', 'dma_enable_sys', 'dma_buffer_sys'), expected):
            check(cone.evaluate(output, env) == value, 'Mode/GUI mux mismatch: ' + output)
        cases += 1
    active, _ = register(cone, 'background_active_ddr', 'ddr_clk')
    request, _ = register(cone, 'background_request_d2', 'ddr_clk')
    for old, new, idle, writer_idle, enabled in itertools.product((0, 1), repeat=5):
        env = state(cone) | {active: old, request: new, 'ddr_resetn': 1,
                            'session_idle_ddr': idle, 'writer_idle_ddr': writer_idle,
                            'control_enable_ddr': enabled}
        # ADS inlines writer_idle as its one-hot IDLE bit AND !busy.
        # Exercise all three encodings of !writer_idle as well as IDLE.
        encodings = ((1, 0),) if writer_idle else ((0, 0), (0, 1), (1, 1))
        for machine_idle, busy in encodings if expanded_writer else ((0, 0),):
            if expanded_writer:
                env['u_camera_frame_writer/d_state_reg[0]'] = machine_idle
                env['camera_write_urgent'] = busy
            expected = new if idle and writer_idle and not enabled else old
            check(next_value(cone, active, env, 'ddr_clk') == expected,
                  'Mode changes during a live/draining DDR session')
    return {'gui_mux_cases': cases, 'mode_commit_cases': 32, 'synchronizer_stages': 4}


def audit_snapshot(cone):
    held, _ = register(cone, 'hold_seen', 'clk')
    published_q, _ = register(cone, 'published_buffer', 'clk')
    for background, published, display, old in itertools.product((0, 1), repeat=4):
        q, _ = register(cone, 'snapshot_buffer', 'clk')
        env = state(cone) | {'resetn': 1, held: 0, q: old, 'snapshot_hold': 1,
                            'background_capture': background,
                            'published_buffer': published, 'display_buffer': display}
        # published_buffer is a register output, not a primary input.
        env[published_q] = published
        check(next_value(cone, 'snapshot_buffer', env, 'clk') ==
              (published if background else display), 'HOLD selects the wrong bank')
    return {'snapshot_bank_cases': 16}


def audit_writer(cone):
    base = state(cone)
    machine = sorted(q for q, (n, p) in cone.drivers.items() if p == 'Q' and
                     re.fullmatch(r'd_state_reg\[[0-3]\]', n['name']))
    check(0 < len(machine) <= 8, 'Unknown writer FSM mapping')
    # Enumerate mapped state bits: at least one actual admitted frame must
    # select each of the four address regions. Every tested non-admission
    # must keep the previous latched address, independently of mode changes.
    old_address = 0x6d00000
    admitted = 0
    transitions = 0
    for machine_bits in itertools.product((0, 1), repeat=len(machine)):
        for background, bank, busy, enabled, start, live in itertools.product((0, 1), repeat=6):
            env = base | dict(zip(machine, machine_bits)) | {
                'ddr_resetn': 1, 'pixel_resetn': 1, 'enable': enabled, 'stop_request': 0,
                'background_capture': background, 'frame_start_buffer_pix': bank,
                'camera_write_urgent': busy, 'u_camera_buffer_control/N576[7]': live}
            for name in ('start_d2',):
                env[resolve(cone, name)] = start
            for bit in (19, 20, 21):
                q, _ = register(cone, 'frame_base_ddr[%d]' % bit, 'ddr_clk')
                env[q] = (old_address >> bit) & 1
            starts = next_value(cone, 'frame_started', env, 'ddr_clk')
            expected_start = int(enabled and not busy and start and live and
                                 env[register(cone, 'd_state_reg[0]', 'ddr_clk')[0]])
            check(starts == expected_start, 'Writer admission condition changed')
            address = (0x6e80000 if bank else 0x6e00000) if background else (
                0x6d00000 if bank else 0x6c80000)
            expected = address if starts else old_address
            for bit in (19, 20, 21):
                name = 'frame_base_ddr[%d]' % bit
                q = resolve(cone, name)
                actual = next_value(cone, name, env, 'ddr_clk') if q in base else cone.evaluate(name, env)
                check(actual == (expected >> bit) & 1, 'Writer frame base mismatch: ' + name)
            admitted += starts
            transitions += 1
    check(admitted >= 4, 'No admitted frames exercise all four private/legacy bases')
    # All three retained selector bits must feed the actual native AW address
    # register cones, not an unconsumed shadow. Common constant address bits
    # and complete burst addresses are covered by RTL and board acceptance.
    address_fanin = set()
    for q, (node, port) in cone.drivers.items():
        if port == 'Q' and re.fullmatch(r'native_addr\[\d+\]', node['name']):
            address_fanin |= cone.fanin(node['ports']['D'])
    check(all(resolve(cone, 'frame_base_ddr[%d]' % bit) in address_fanin
              for bit in (19, 20, 21)), 'Private base selector does not feed native AW')
    return {'writer_admitted_cases': admitted, 'writer_state_bits': len(machine),
            'writer_transition_cases': transitions}


def audit(source):
    source = re.sub(r'\(\*.*?\*\)', '', source, flags=re.S)
    ports = instance_ports(source, 'soc_top', 'camera_capture_mode', 'u_camera_capture_mode')
    functional = {k: v for k, v in MODE_PORTS.items()
                  if k not in ('sys_resetn', 'ddr_resetn', 'writer_idle_ddr')}
    check(all(ports.get(k) == v for k, v in functional.items()),
          'Integrated mode controller bindings changed')
    check(ports.get('u_camera_frame_writer/d_state_reg') ==
          "{1'bx,1'bx,1'bx,u_camera_frame_writer/d_state_reg[0]}" and
          ports.get('camera_write_urgent') == 'camera_write_urgent',
          'Unknown inlined writer-idle wiring')
    for kind in ('camera_frame_writer', 'camera_buffer_control'):
        producer_ports = instance_ports(source, 'soc_top', kind, 'u_' + kind)
        check(producer_ports.get('background_capture') == 'camera_background_active_ddr',
              'Private-bank producer is disconnected: ' + kind)
    mode, writer, buffer, mmio = (Cone(source, kind) for kind in
        ('camera_capture_mode', 'camera_frame_writer', 'camera_buffer_control', 'camera_mmio'))
    mmio_ports = instance_ports(source, 'soc_top', 'camera_mmio', 'u_camera_regs')
    check(mmio_ports.get('background_request') == ports['background_request'] and
          mmio_ports.get('clk') == ports['sys_clk'], 'Missing SYS mode request producer')
    _, request_ff = register(mmio, 'background_request', 'clk')
    _, ack_ff = register(mode, 'background_ack_s1', 'sys_clk')
    check(mmio_ports[request_ff['ports']['C']] == ports[ack_ff['ports']['C']],
          'Mode SYS reset differs from its MMIO producer')
    check(register(mode, 'background_ack_s2', 'sys_clk')[1]['ports']['C'] == ack_ff['ports']['C'],
          'Mode SYS acknowledgement resets differ')
    ddr_reset = register(mode, 'background_active_ddr', 'ddr_clk')[1]['ports']['C']
    top = Cone(source, 'soc_top')
    reset_node, output = top.drivers[ports[ddr_reset]]
    check(reset_node['kind'] == 'GTP_INV' and output == 'Z' and
          reset_node['ports']['I'] == 'ddr_rst_pipe[2]', 'Unknown DDR reset binding')
    for name in ('background_request_d1', 'background_request_d2'):
        check(register(mode, name, 'ddr_clk')[1]['ports']['C'] == ddr_reset,
              'Mode DDR synchronizer resets differ')
    for kind, cone, names, clock in (
            ('camera_buffer_control', buffer, ('hold_seen', 'snapshot_buffer', 'published_buffer'), 'clk'),
            ('camera_frame_writer', writer, ('frame_base_ddr[19]', 'frame_base_ddr[20]', 'frame_base_ddr[21]'), 'ddr_clk')):
        producer_ports = instance_ports(source, 'soc_top', kind, 'u_' + kind)
        for name in names:
            _, node = register(cone, name, clock)
            reset = node['ports'].get('C', node['ports'].get('P'))
            check(producer_ports.get(reset) == ports[ddr_reset], 'Camera DDR reset mismatch: ' + name)
    check(register(writer, 'busy', 'ddr_clk')[0] == 'camera_write_urgent' and
          register(writer, 'd_state_reg[0]', 'ddr_clk')[1]['init'] == 1,
          'Inlined writer IDLE does not match its retained registers')
    for enable, stop in itertools.product((0, 1), repeat=2):
        check(buffer.evaluate('N576[7]', {'control_enable': enable, 'stop_request': stop}) ==
              int(enable and not stop), 'Writer admission lost its live-session guard')
    return (audit_mode(mode, expanded_writer=True) | audit_snapshot(buffer) | audit_writer(writer))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', type=Path, required=True)
    parser.add_argument('--input-snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.input_snapshot.read_text(encoding='utf-8-sig'))
    scripts = Path(__file__).resolve().parent
    checker, dependency = sha(Path(__file__)), sha(scripts / 'audit_cpu_ads.py')
    check(snapshot['inputs']['scripts/audit_camera_background_ads.py'] == checker and
          snapshot['inputs']['scripts/audit_cpu_ads.py'] == dependency,
          'Auditor differs from frozen snapshot')
    result = audit(args.netlist.read_text(encoding='utf-8'))
    result |= {'schema_version': 1, 'status': 'PASS', 'scope': 'ADS_ONLY',
               'input_snapshot_run_id': snapshot['run_id'],
               'input_snapshot_sha256': sha(args.input_snapshot),
               'netlist_sha256': sha(args.netlist), 'checker_sha256': checker,
               'parser_sha256': dependency}
    check(not args.output.exists(), 'Refuse to replace an earlier ADS result')
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('CAMERA_BACKGROUND_ADS_PASS ' + json.dumps(result))


if __name__ == '__main__':
    main()
