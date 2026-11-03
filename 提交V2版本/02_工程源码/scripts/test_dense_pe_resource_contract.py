"""Keep full/half/quarter native resource profiles closed and distinct."""
import unittest
from dense_pe_resource_contract import dense_pe_resource_contract

def report(apm):return f'| + pe | 111 | 222 | 0 | {apm} | 6 | 0 |\n'

class DenseResource(unittest.TestCase):
    def test_all_profiles(self):
        for profile,apm in [(0,160),(1,80),(2,40)]:
            result=dense_pe_resource_contract(report(apm),f'.HALF_OUTPUT({profile})')
            self.assertEqual(result,dict(profile=profile,apm=apm,output_groups=1<<profile))

    def test_faults_reject(self):
        for text,top in [(report(80),'.HALF_OUTPUT(2)'),(report(40),'.HALF_OUTPUT(1)'),
                         (report(40),'.HALF_OUTPUT(3)'),(report(40),'.HALF_OUTPUT(mode)'),
                         (report(40),'.HALF_OUTPUT(2) .HALF_OUTPUT(2)'),
                         ('','.HALF_OUTPUT(2)'),(report(40)*2,'.HALF_OUTPUT(2)')]:
            with self.assertRaises((AssertionError,ValueError)):
                dense_pe_resource_contract(text,top)

if __name__=='__main__':unittest.main()
