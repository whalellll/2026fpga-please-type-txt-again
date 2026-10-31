"""Reject missing PE lanes, reintroduced legacy conv, or excess RAM."""
import unittest
from vision32_resource_contract import vision32_resource_contract as check


class Contract(unittest.TestCase):
    vm = 'module vision32_layer; endmodule\nmodule vision32_pe;\n' + 'GTP_APM_E2 u();\n'*32 + 'endmodule\n'
    report = 'Total DRM = 140.0 of 155\n| + g_vision32.u_vision32 | 7000 | 5000 | 256 | 44 | 8 | 0 |\n'

    def test_valid(self):
        self.assertEqual(check(self.vm, self.report)['pe_apm'], 32)

    def test_mutations(self):
        for vm, report in [(self.vm.replace('GTP_APM_E2 u();\n', '', 1), self.report),
                           (self.vm+self.vm, self.report),
                           (self.vm+'module mac_conv_compute_core; endmodule\n', self.report),
                           (self.vm+'module mac_conv_weight_dma; endmodule\n', self.report),
                           (self.vm, self.report.replace(' | 8 |', ' | 8.5 |')),
                           (self.vm, self.report.replace('140.0', '141.0')),
                           (self.vm, self.report.replace(' | 8 |', ' | 0 |')),
                           (self.vm, self.report.replace('7000', '0')),
                           (self.vm, self.report.replace(' | 44 |', ' | 20 |'))]:
            with self.assertRaises(AssertionError):
                check(vm, report)


if __name__ == '__main__':
    unittest.main()
