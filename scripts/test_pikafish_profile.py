import unittest
from parse_pikafish_profile import parse
from profile_pikafish_nnue import STAGES


def fixture():
    lines = ["NNUE_LATENCY_CORRECTNESS_PASS", "NNUE_PROFILE_CALIBRATION pairs=10000 mean_pair_ns=100"]
    times = dict.fromkeys(STAGES, 1000)
    times.update(network=24000, accumulator=10000, refresh_vectors=6000, fc0=5000, fc0_submit=2000)
    for phase in ("cold", "warm"):
        for name in STAGES:
            calls = 40 if name.startswith("refresh_") else 20
            lines.append(f"NNUE_PROFILE phase={phase} stage={name} calls={calls} total_ns={times[name]*20} mean_us=1")
        lines.append(f"NNUE_LATENCY phase={phase} samples=20 mean_us=24 min_us=24 p50_us=24 p95_us=24 max_us=24")
    return '\n'.join(lines)


class ProfileTests(unittest.TestCase):
    def test_inclusive_accounting(self):
        result = parse(fixture())
        self.assertAlmostEqual(result['phases']['warm']['unattributed_ms']['network'], .003)
    def test_double_count_rejected(self):
        with self.assertRaises(ValueError): parse(fixture().replace("stage=fc0 calls=20 total_ns=100000", "stage=fc0 calls=20 total_ns=1"))
    def test_missing_phase_rejected(self):
        with self.assertRaises(ValueError): parse(fixture().replace("phase=warm stage=fc2", "phase=absent stage=fc2"))
    def test_perspective_count_rejected(self):
        with self.assertRaises(ValueError): parse(fixture().replace("stage=refresh_psqt calls=40", "stage=refresh_psqt calls=20"))
    def test_golden_required(self):
        with self.assertRaises(ValueError): parse(fixture().replace("NNUE_LATENCY_CORRECTNESS_PASS", ""))
    def test_strict_hardware_required(self):
        with self.assertRaises(ValueError): parse(fixture(), hardware=True)
    def test_uncalibrated_clock_rejected(self):
        with self.assertRaisesRegex(ValueError,"clock"):
            parse(fixture()+"\nNNUE_CLOCK_SOURCE source=linux", hardware=True)
    def test_partial_microbenchmark_rejected(self):
        with self.assertRaisesRegex(ValueError,"microbenchmark"):
            parse(fixture()+"\nNNUE_MICRO engine=gather", hardware=False)


if __name__ == '__main__': unittest.main()
