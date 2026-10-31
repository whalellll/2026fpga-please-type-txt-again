"""Regression for the RAM loader's word-only uncached CRC contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ClockBootWordCrc(unittest.TestCase):
    def test_generated_clock_payloads_use_word_safe_crc(self):
        source = (ROOT/'linux/opensbi/build_clock_candidate.py').read_text(encoding='utf-8')
        self.assertIn('copy_to_uncached(0x18000000u,sizeof(fw_jump_bin))', source)
        self.assertIn('copy_to_uncached(0x1a000000u,sizeof(clock_dtb_bin))', source)
        self.assertNotIn('crc32_fast(0xffffffffu,(const void *)(uintptr_t)0x9a000000u', source)
        self.assertNotIn('crc32_fast(0xffffffffu,(const void *)(uintptr_t)0x98000000u', source)

    def test_source_loader_has_word_tail_handling(self):
        source = (ROOT/'artifacts/voice_hw_candidate_20261016/loader/loader.c').read_text(encoding='utf-8')
        begin = source.index('static uint32_t copy_to_uncached(')
        end = source.index('\n}', begin)
        helper = source[begin:end]
        self.assertIn('count & ~3u', helper)
        self.assertIn('uint32_t tail = uncached[count >> 2]', helper)
        self.assertIn('tail >>= 8', helper)

if __name__ == '__main__':
    unittest.main()
