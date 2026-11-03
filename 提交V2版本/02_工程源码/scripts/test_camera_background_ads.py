"""Mutation tests for the background mode ADS gate (synthetic mapped cells)."""
import itertools
import argparse
import re
import sys
import unittest
from pathlib import Path

from audit_camera_background_ads import audit, audit_mode, audit_snapshot
from audit_cpu_ads import Cone, module_text

MAPPED_NETLIST = None


def lut(output, names, predicate):
    value = sum(int(predicate(*bits)) << sum(b << i for i, b in enumerate(bits))
                for bits in itertools.product((0, 1), repeat=len(names)))
    ports = ','.join('.I%d(%s)' % (i, name) for i, name in enumerate(names))
    return "GTP_LUT%d #(.INIT(%d'h%x)) cell_%s (.Z(%s),%s);\n" % (
        len(names), 1 << len(names), value, output, output, ports)


def ff(name, data, clock, ce=None):
    return 'GTP_DFF_C%s %s (.Q(%s),.D(%s),.CLK(%s),.C(reset)%s);\n' % (
        'E' if ce else '', name, name, data, clock, ',.CE(%s)' % ce if ce else '')


def mode_fixture():
    body = "module camera_capture_mode ();\nassign reset=1'b0;\n"
    for name, source, clock in (
            ('background_request_d1', 'background_request', 'ddr_clk'),
            ('background_request_d2', 'background_request_d1', 'ddr_clk'),
            ('background_ack_s1', 'background_active_ddr', 'sys_clk'),
            ('background_ack_s2', 'background_ack_s1', 'sys_clk')):
        body += ff(name, source, clock)
    body += lut('commit', ('session_idle_ddr', 'writer_idle_ddr', 'control_enable_ddr'),
                lambda idle, writer, enabled: idle and writer and not enabled)
    body += ff('background_active_ddr', 'background_request_d2', 'ddr_clk', 'commit')
    body += 'assign background_active_sys=background_ack_s2;\n'
    body += lut('effective_enable_sys', ('requested_enable', 'background_request', 'background_ack_s2'),
                lambda en, request, active: en and request == active)
    body += lut('camera_preview_sys', ('effective_enable_sys', 'frame_valid_sys', 'background_ack_s2'),
                lambda en, valid, active: en and valid and not active)
    body += lut('dma_enable_sys', ('camera_preview_sys', 'gui_enable_sys'), lambda preview, gui: preview or gui)
    body += lut('dma_buffer_sys', ('camera_preview_sys', 'gui_buffer_sys', 'camera_buffer_sys'),
                lambda preview, gui, camera: camera if preview else gui)
    return body + 'endmodule\n'


class CameraAdsTest(unittest.TestCase):
    def test_actual_netlist_and_mutations(self):
        if MAPPED_NETLIST is None:
            self.skipTest('actual ADS netlist supplied separately')
        source = MAPPED_NETLIST.read_text(encoding='utf-8')
        self.assertEqual(audit(source)['writer_transition_cases'], 1024)
        changes = (
            ('camera_capture_mode', r'\.D\s*\(background_request_d1\)', '.D(background_request)'),
            ('camera_capture_mode', r'\.I1\s*\(session_idle_ddr\)', ".I1(1'b1)"),
            ('camera_capture_mode', r'\.I4\s*\(camera_buffer_sys\)', '.I4(gui_buffer_sys)'),
            ('camera_frame_writer', r'\.D\s*\(background_capture\)', ".D(1'b0)"),
            ('camera_buffer_control', r'\.I0\s*\(background_capture\)', ".I0(1'b0)"),
        )
        for kind, pattern, replacement in changes:
            block = module_text(source, kind)
            changed, count = re.subn(pattern, replacement, block)
            self.assertGreater(count, 0)
            with self.subTest(kind=kind, mutation=pattern):
                with self.assertRaises(ValueError):
                    audit(source.replace(block, changed, 1))
        block = module_text(source, 'camera_buffer_control')
        changed, count = re.subn(r'\.Q\s*\(published_buffer\)', '.Q(published_dead)', block)
        self.assertEqual(count, 1)
        changed = changed.replace('endmodule', "assign published_buffer=1'b0;\nendmodule")
        with self.assertRaises(ValueError):
            audit(source.replace(block, changed, 1))

    def test_mode_and_legacy_truth_tables(self):
        self.assertEqual(audit_mode(Cone(mode_fixture(), 'camera_capture_mode'))['gui_mux_cases'], 128)

    def test_reject_tied_mux_and_broken_synchronizer_and_commit(self):
        source = mode_fixture()
        mutations = [source.replace('.D(background_ack_s1)', '.D(background_active_ddr)'),
                     source.replace('.CE(commit)', ".CE(1'b1)"),
                     source.replace('.I0(camera_preview_sys)', ".I0(1'b1)"),
                     source.replace('.CLK(ddr_clk)', '.CLK(sys_clk)', 1)]
        for changed in mutations:
            with self.subTest(mutation=changed):
                with self.assertRaises(ValueError):
                    audit_mode(Cone(changed, 'camera_capture_mode'))

    def test_snapshot_source_and_missing_background_mux(self):
        source = 'module camera_buffer_control ();\n' + "assign reset=1'b0;\n"
        source += ff('hold_seen', 'snapshot_hold', 'clk')
        source += ff('published_buffer', 'writer_completed_buffer', 'clk')
        source += lut('bank', ('background_capture', 'published_buffer', 'display_buffer'),
                      lambda bg, published, display: published if bg else display)
        source += ff('snapshot_buffer', 'bank', 'clk', 'snapshot_hold') + 'endmodule\n'
        self.assertEqual(audit_snapshot(Cone(source, 'camera_buffer_control'))['snapshot_bank_cases'], 16)
        with self.assertRaises(ValueError):
            audit_snapshot(Cone(source.replace('.D(bank)', '.D(display_buffer)'), 'camera_buffer_control'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--mapped-netlist', type=Path)
    args, remaining = parser.parse_known_args()
    MAPPED_NETLIST = args.mapped_netlist
    sys.argv = [sys.argv[0]] + remaining
    unittest.main()
