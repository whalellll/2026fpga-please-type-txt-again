"""Exercise the C tiler, its dense packing, parser and strict device policy."""
import struct
import os
import subprocess
import unittest
import zlib
from pathlib import Path

from dense_tiled_conv import ConvSpec, dense_reference, make_jobs, write_cases


class DenseTiledRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.directory = cls.root / 'build/vision/dense_tiled_20261005/host_tests'
        cls.directory.mkdir(parents=True, exist_ok=True)
        cls.wsl_root = ('/mnt/' + cls.root.drive[0].lower() + cls.root.as_posix()[2:]
                        if os.name == 'nt' else str(cls.root))
        cls.command_prefix = ['wsl', '-d', 'chiplab_sim', '--'] if os.name == 'nt' else []
        cls.host = cls.directory / 'runner-host'
        cls.device = cls.directory / 'runner-device-host'
        source = 'linux/mac_accel/pango_mac_tiled_conv_test.c'
        for path, define in ((cls.host, '-DDENSE_CONV_EMULATED'), (cls.device, '')):
            command = ('cd ' + cls.wsl_root + '\ngcc -std=c11 -O2 -Wall -Wextra -Werror ' +
                       define + ' ' + source + ' -o ' + path.relative_to(cls.root).as_posix())
            subprocess.run(cls.command_prefix + ['bash', '-c', command],
                           check=True, capture_output=True)

    def case(self):
        spec = ConvSpec(5, 4, 128, 57, 3, 1, 1)
        x = bytes((i*71+3) % 256 for i in range(spec.width*spec.height*spec.cin))
        w = bytes((i*113+31) % 256 for i in range(spec.cout*spec.cin*9))
        bias = [i*71-123 for i in range(spec.cout)]
        return {'name': 'k1152_tail57', 'spec': spec, 'input': x, 'weights': w,
                'bias': bias, 'shift': 10, 'expected': dense_reference(spec, x, w, bias)}

    def invoke(self, path, device=False):
        exe = self.device if device else self.host
        args = [self.wsl_root+'/'+exe.relative_to(self.root).as_posix(),
                self.wsl_root+'/'+path.relative_to(self.root).as_posix(), '1']
        return subprocess.run(self.command_prefix + args, capture_output=True,
                              text=True, encoding='utf-8', errors='replace')

    def test_host_driver_packing_and_full_integer_outputs(self):
        case = self.case()
        path = self.directory/'good.bin'
        write_cases([case], path)
        result = self.invoke(path)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        crc = 0
        for job in make_jobs(case['spec'], case['input'], case['weights']):
            crc = zlib.crc32(job.inputs, crc)
            crc = zlib.crc32(job.weights, crc)
        self.assertIn('packed_crc32=%08x' % crc, result.stdout)
        self.assertIn('DENSE_TILED_CONV_HOST_PASS', result.stdout)
        self.assertNotIn('BOARD_PASS', result.stdout)

    def test_payload_and_golden_corruption_rejected(self):
        path = self.directory/'corrupt.bin'
        write_cases([self.case()], path)
        data = bytearray(path.read_bytes()); data[-1] ^= 1
        path.write_bytes(data)
        self.assertNotEqual(self.invoke(path).returncode, 0)
        struct.pack_into('<I', data, 16, zlib.crc32(data[20:]))
        path.write_bytes(data)
        result = self.invoke(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('mismatch', result.stderr)

    def test_invalid_geometry_and_truncation_rejected(self):
        path = self.directory/'bad.bin'
        write_cases([self.case()], path)
        data = bytearray(path.read_bytes())
        struct.pack_into('<I', data, 52, 0)  # first case width
        struct.pack_into('<I', data, 16, zlib.crc32(data[20:]))
        path.write_bytes(data)
        self.assertNotEqual(self.invoke(path).returncode, 0)
        path.write_bytes(data[:-20])
        self.assertNotEqual(self.invoke(path).returncode, 0)

    def test_device_mode_has_no_cpu_fallback(self):
        path = self.directory/'device.bin'
        write_cases([self.case()], path)
        result = self.invoke(path, device=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('PASS', result.stdout)
        self.assertIn('/dev/pango-mac0', result.stderr)


if __name__ == '__main__':
    unittest.main()
