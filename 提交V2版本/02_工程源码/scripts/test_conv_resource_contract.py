"""Fail-closed fixtures for the convolution-aware native resource gate."""
import unittest
from conv_resource_contract import conv_resource_contract

class Contract(unittest.TestCase):
    vm='\n'.join('module '+n+'; endmodule' for n in (
        'mac_conv_mmio_frontend','mac_conv_compute_core','mac_conv_input_dma',
        'mac_conv_weight_dma','mac_weight_double_buffer','mac_conv_compact_writer'))
    report='|   + g_conv.u_conv | 9000 | 3000 | 1024 | 14 | 2 | 0 |\n'
    def test_enabled(self):
        self.assertEqual(conv_resource_contract(self.vm,self.report,1)['drm'],2)
    def test_disabled(self):
        self.assertEqual(conv_resource_contract('','',0)['apm'],0)
    def test_missing_or_unknown_structure(self):
        for vm,report,enabled in [('',self.report,1),(self.vm,'',1),(self.vm+self.vm,self.report,1),
            (self.vm,self.report*2,1),(self.vm,self.report,0),('',self.report,0),(self.vm,self.report,2)]:
            with self.assertRaises(AssertionError):conv_resource_contract(vm,report,enabled)
    def test_resource_mutations(self):
        for old,new in [('9000','0'),('3000','0'),(' | 14 |',' | 0 |'),(' | 14 |',' | 8 |'),(' | 2 |',' | 32 |'),(' | 1024 |',' | 0 |')]:
            with self.assertRaises(AssertionError):conv_resource_contract(self.vm,self.report.replace(old,new),1)
if __name__=='__main__':unittest.main()
