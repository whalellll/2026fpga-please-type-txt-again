"""Reject incorrect constraints and evidence using a source-bound native fixture."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('csr',R/'scripts/audit_cpu_csr_placement.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class Checks(unittest.TestCase):
    def test_real_inputs_and_exact_cardinality(self):
        q,r=m.inputs(R);self.assertEqual(len(r),32);self.assertEqual(q['cpu_hz'],75000000)
    def test_reject_unchecked_missing_duplicate_extra_or_invalid_requests(self):
        text=(R/'pds/cpu75_csr_reference.pcf').read_text();lines=[s for s in text.splitlines() if s.startswith('def_inst_site')]
        for bad in [text+'\n'+lines[0],text.replace(lines[0],''),text.replace(' FYB',' FYB -no_check'),text.replace('def_inst_site','unknown'),text.replace('CLMA_','CLMX_')]:
            with self.subTest(bad=bad[:60]):
                if bad==text:continue
                with tempfile.TemporaryDirectory() as tmp:
                    p=Path(tmp);(p/'pds').mkdir();(p/'rtl/cpu').mkdir(parents=True);(p/'config').mkdir()
                    for name in ['pds/cpu75_csr_reference.json','rtl/cpu/CoreTop.sv','config/clocks.json']:(p/name).write_bytes((R/name).read_bytes())
                    (p/'pds/cpu75_csr_reference.pcf').write_text(bad)
                    with self.assertRaises(ValueError):m.inputs(p)
    def test_post_reject_bad_execution_mapping_actual_and_type(self):
        q,want=m.inputs(R)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in ['pds/cpu75_csr_reference.json','pds/cpu75_csr_reference.pcf','rtl/cpu/CoreTop.sv','config/clocks.json','scripts/audit_cpu_csr_placement.py']:
                (p/name).parent.mkdir(parents=True,exist_ok=True);(p/name).write_bytes((R/name).read_bytes())
            (p/'pds/place_route').mkdir()
            frozen={n:m.sha(p/n) for n in ['pds/cpu75_csr_reference.json','pds/cpu75_csr_reference.pcf','scripts/audit_cpu_csr_placement.py']}
            snapshot=p/'pds/build_snapshot.json';snapshot.write_text(json.dumps(dict(run_id='explicit-native-fixture',inputs=frozen)))
            cells=''.join('Inst\n'+r['cell']+';'+r['cell_type']+'\n' for r in q['selected'])
            net=p/'pds/place_route/soc_top_pnr.netlist';net.write_text(cells);(p/'pds/place_route/soc_top_pnr.adf').write_bytes(b'fixture-only')
            lines=[f'def_inst_site {{{n}}} {a} {b}' for n,(a,b) in want.items()]
            stdout=p/'stdout';mapped=p/'mapped';actual=p/'actual'
            good='\n'.join('Executing : '+s+' successfully.' for s in lines)+'\n'
            stdout.write_text(good);mapped.write_text('\n'.join(lines));actual.write_text('\n'.join(s+' -no_check' for s in lines))
            self.assertEqual(m.post(p,stdout,mapped,actual)['cells'],32)
            for path,bad in [(stdout,''),(stdout,good+'\n'+good.splitlines()[0]),(mapped,''),(actual,''),(net,cells.replace(q['selected'][0]['cell_type'],'WRONG_TYPE',1)),(snapshot,json.dumps(dict(run_id='foreign',inputs={})))]:
                old=path.read_bytes();path.write_text(bad)
                with self.subTest(path=path.name):
                    with self.assertRaises(ValueError):m.post(p,stdout,mapped,actual)
                path.write_bytes(old)
if __name__=='__main__':unittest.main()
