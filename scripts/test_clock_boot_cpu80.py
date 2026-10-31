"""Clock intent to OpenSBI bridge ratio, including the CPU80 reference."""
import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('clock_boot',Path(__file__).resolve().parents[1]/'linux/opensbi/build_clock_candidate.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class ClockRatio(unittest.TestCase):
    def test_profiles(self):
        for mode,vco,div,hz,expected in [('video891',891000000,15,59400000,(5,6)),('dedicated850p5',850500000,12,70875000,(44,63)),('dedicated675',675000000,9,75000000,(33,50)),('dedicated800',800000000,10,80000000,(99,160))]:
            c=dict(pll_vco_hz=891000000,sys_hz=49500000,timebase_hz=49500000,cpu_clock_source=mode,cpu_pll_vco_hz=vco,cpu_divisor=div,cpu_hz=hz,cpu_reference_hz=125000000 if mode=='dedicated800' else 27000000)
            self.assertEqual(mod.clock_candidate_ratio(c),expected)
    def test_bad_cpu80(self):
        good=dict(pll_vco_hz=891000000,sys_hz=49500000,timebase_hz=49500000,cpu_clock_source='dedicated800',cpu_pll_vco_hz=800000000,cpu_divisor=10,cpu_hz=80000000,cpu_reference_hz=125000000)
        for key,value in [('cpu_reference_hz',27000000),('cpu_divisor',9),('cpu_hz',81000000),('cpu_pll_vco_hz',850500000)]:
            with self.assertRaises((AssertionError,ValueError)):mod.clock_candidate_ratio(dict(good,**{key:value}))
    def test_fractional_cpu80(self):
        c=dict(pll_vco_hz=891000000,sys_hz=49500000,timebase_hz=49500000,cpu_clock_source='dedicated1080frac',cpu_pll_vco_hz=1080000000,cpu_divisor=27,cpu_hz=80000000,cpu_reference_hz=27000000,cpu_output_divisor_eighths=108)
        self.assertEqual(mod.clock_candidate_ratio(c),(99,160))
    def test_fractional_cpu85(self):
        c=dict(pll_vco_hz=891000000,sys_hz=49500000,timebase_hz=49500000,cpu_clock_source='dedicated1147p5frac',cpu_pll_vco_hz=1147500000,cpu_divisor=27,cpu_hz=85000000,cpu_reference_hz=27000000,cpu_output_divisor_eighths=108)
        self.assertEqual(mod.clock_candidate_ratio(c),(99,170))
        for key,value in [('cpu_hz',85050000),('cpu_pll_vco_hz',1080000000),('cpu_output_divisor_eighths',107)]:
            with self.assertRaises((AssertionError,ValueError)):mod.clock_candidate_ratio(dict(c,**{key:value}))
if __name__=='__main__':unittest.main()
