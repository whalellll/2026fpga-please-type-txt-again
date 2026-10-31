"""Check the RAM boot device-tree contract for driver-managed PFF1 gather."""
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('clock_boot',ROOT/'linux/opensbi/build_clock_candidate.py')
clock_boot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock_boot)

class GatherDts(unittest.TestCase):
    def test_bind_gather_without_changing_other_nodes(self):
        source=(ROOT/'artifacts/voice_hw_candidate_20261016/boot/voice.soc.dts').read_text()
        changed=clock_boot.enable_stagea_gather_dts(source)
        self.assertIn('reg = <0x1fe10000 0x00000200>;',changed)
        self.assertIn('memory-region = <&mac_accel_mem &pikafish_pff1>;',changed)
        self.assertIn('pikafish_pff1: pikafish-pff1@10000000',changed)
        reverted=changed.replace('reg = <0x1fe10000 0x00000200>;','reg = <0x1fe10000 0x00000100>;')
        reverted=reverted.replace('memory-region = <&mac_accel_mem &pikafish_pff1>;','memory-region = <&mac_accel_mem>;')
        reverted=reverted.replace('pikafish_pff1: pikafish-pff1@10000000','pikafish-pff1@10000000')
        self.assertEqual(reverted,source)
    def test_reject_unknown_memory_contract(self):
        with self.assertRaises(ValueError):
            clock_boot.enable_stagea_gather_dts('mac-accel@1fe10000 {};')
    def test_active_dts_declares_driver_gather(self):
        source=(ROOT/'linux/soc.dts').read_text()
        self.assertIn('reg = <0x1fe10000 0x00000200>;',source)
        self.assertIn('memory-region = <&mac_accel_mem &pikafish_pff1>;',source)

if __name__=='__main__': unittest.main()
