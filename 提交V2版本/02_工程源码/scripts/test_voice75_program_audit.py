"""Check the closed inherited-function exception with no PDS/device access."""
from pathlib import Path
import hashlib,json,shutil,subprocess,tempfile,unittest
from program_with_project_audit import adapt_voice75_functions,VOICE75_FUNCTIONS,GUI1080_FUNCTIONS

ROOT=Path(__file__).resolve().parents[1]
AUDIT=(ROOT/'scripts/audit_gui1080_candidate.ps1').read_text(encoding='utf-8-sig')
SOURCE='rtl/mac_accel/mac_conv_weight_dma.v'


class ClosedFunctionException(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='program-audit-test-',dir=ROOT/'build')
        self.root=Path(self.temp.name)
        for n in ['config/clocks.json','config/display.json','rtl/soc/soc_top.v',SOURCE]:
            target=self.root/n;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(ROOT/n,target)

    def tearDown(self):self.temp.cleanup()

    def update(self,name,key,value):
        p=self.root/name;data=json.loads(p.read_text());data[key]=value;p.write_text(json.dumps(data))

    def test_exact_parent_source_and_function(self):
        source=(ROOT/SOURCE).read_bytes()
        parent=subprocess.check_output(['git','show','2f3d0ab:'+SOURCE],cwd=ROOT)
        self.assertEqual(source,parent)
        self.assertEqual(hashlib.sha256(source).hexdigest(),VOICE75_FUNCTIONS[SOURCE])
        effective,hashes=adapt_voice75_functions(self.root,AUDIT)
        self.assertEqual(hashes,VOICE75_FUNCTIONS)
        self.assertNotIn(GUI1080_FUNCTIONS[SOURCE],effective)
        self.assertEqual(effective.count(VOICE75_FUNCTIONS[SOURCE]),1)

    def test_clocks_and_display_reject(self):
        for name,key,value in [('config/clocks.json','sys_hz',49500001),
                               ('config/display.json','refresh_hz',60),
                               ('config/display.json','pixel_hz',148500000),
                               ('config/display.json','height',720)]:
            original=(self.root/name).read_bytes();self.update(name,key,value)
            with self.assertRaises(AssertionError):adapt_voice75_functions(self.root,AUDIT)
            (self.root/name).write_bytes(original)

    def test_modified_function_source_reject(self):
        p=self.root/SOURCE;p.write_bytes(p.read_bytes()+b'\nfunction injected; endfunction\n')
        with self.assertRaises(AssertionError):adapt_voice75_functions(self.root,AUDIT)

    def test_disabled_pipeline_reject(self):
        p=self.root/'rtl/soc/soc_top.v';p.write_text(p.read_text().replace('.ENABLE_NNUE_PIPELINE(1)','.ENABLE_NNUE_PIPELINE(0)'))
        with self.assertRaises(AssertionError):adapt_voice75_functions(self.root,AUDIT)

    def test_unreviewed_audit_reject(self):
        with self.assertRaises(AssertionError):adapt_voice75_functions(self.root,AUDIT.replace(GUI1080_FUNCTIONS[SOURCE],'unreviewed'))


if __name__=='__main__':unittest.main()
