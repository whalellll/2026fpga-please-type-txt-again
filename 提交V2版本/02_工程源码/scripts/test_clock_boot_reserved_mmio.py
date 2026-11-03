"""Keep the low CLINT MMIO aperture out of Linux's buddy allocator."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('clock_boot',ROOT/'linux/opensbi/build_clock_candidate.py')
clock_boot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock_boot)

class ReservedMmioTest(unittest.TestCase):
    def check_reserved(self,text):
        match=re.search(r'clint-mmio@2000000\s*\{([^}]+)\}',text)
        self.assertIsNotNone(match,'CLINT must not be allocatable Linux RAM')
        self.assertRegex(match[1],r'reg\s*=\s*<0x02000000\s+0x00010000>')
        self.assertIn('no-map;',match[1])

    def test_boot_candidate_reserves_clint(self):
        old=(ROOT/'artifacts/voice_hw_candidate_20261016/boot/voice.soc.dts').read_text(encoding='utf-8')
        self.check_reserved(clock_boot.reserve_clint_mmio_dts(clock_boot.enable_stagea_gather_dts(old)))

    def test_main_device_tree_reserves_clint(self):
        self.check_reserved((ROOT/'linux/soc.dts').read_text(encoding='utf-8'))

    def test_reservation_is_idempotent(self):
        old=(ROOT/'linux/soc.dts').read_text(encoding='utf-8')
        self.assertEqual(clock_boot.reserve_clint_mmio_dts(old),old)

    def test_malformed_existing_reservation_rejected(self):
        old=(ROOT/'linux/soc.dts').read_text(encoding='utf-8').replace('0x02000000 0x00010000','0x02000000 0x00001000')
        with self.assertRaises(ValueError):clock_boot.reserve_clint_mmio_dts(old)

if __name__=='__main__':unittest.main()
