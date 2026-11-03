"""Reject wrong clocks, missing SD files and loader failures without UART."""
import unittest
from board_boot_contract import contract,validate


class BootContract(unittest.TestCase):
    def data(self,prefix='VOICE_NNUE',hz=75000000):
        _,success,_=contract(prefix,hz)
        return (b'\r\n'+success+b'\r\n'+b''.join(b'Loading '+n+b'\r\n' for n in
            [b'fw_jump.bin',b'Image',b'rootfs.cpio',b'soc.dtb',b'pikafish.pff',b'pikafish.atk'])+b'/ # ')

    def test_profiles(self):
        for prefix,hz in [('CPU80',80000000),('VOICE_NNUE',75000000),('VOICE_NNUE',70000000),('VOICE_NNUE',60000000)]:
            validate(self.data(prefix,hz),prefix,hz)

    def test_cpu60_exact_timer_ratio(self):
        data=self.data('VOICE_NNUE',60000000)
        for bad in [data.replace(b'33/40',b'99/160'),data.replace(b' ratio=33/40',b''),data.replace(b'60000000',b'75000000')]:
            with self.assertRaises(AssertionError):validate(bad,'VOICE_NNUE',60000000)

    def test_wrong_clocks(self):
        for data in [self.data().replace(b'75000000',b'80000000'),
                     self.data().replace(b'49500000',b'49500001'),
                     self.data().replace(b'sys=49500000',b'sys=495000000')]:
            with self.assertRaises(AssertionError):validate(data,'VOICE_NNUE',75000000)

    def test_native_progress_prefix(self):
        data=self.data().replace(b'VOICE_NNUE_SD_PAYLOADS',b'.'*35+b'VOICE_NNUE_SD_PAYLOADS')
        validate(data,'VOICE_NNUE',75000000)
        for bad in [data.replace(b'75000000',b'75000001'),data.replace(b'.'*35,b'BAD...'),data+b'VOICE_NNUE_SD_LOAD_OR_CRC_FAIL']:
            with self.assertRaises(AssertionError):validate(bad,'VOICE_NNUE',75000000)

    def test_missing_payload_or_shell(self):
        for text in [b'Loading pikafish.atk',b'/ # ']:
            with self.assertRaises(AssertionError):validate(self.data().replace(text,b''),'VOICE_NNUE',75000000)

    def test_failure_even_with_success(self):
        for failure in [b'VOICE_NNUE_SD_LOAD_OR_CRC_FAIL',b'VOICE_NNUE_SD_CLOCK_MISMATCH',b'Kernel panic']:
            with self.assertRaises(AssertionError):validate(self.data()+failure,'VOICE_NNUE',75000000)

    def test_invalid_contract(self):
        for prefix,hz in [('CPU80',75000000),('VOICE_NNUE',80000000),('OTHER',75000000)]:
            with self.assertRaises(AssertionError):contract(prefix,hz)


if __name__=='__main__':unittest.main()
