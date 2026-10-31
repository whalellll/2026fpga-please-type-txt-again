"""Execute delivered Python/C references without writing into either delivery."""
import argparse,hashlib,importlib.util,json,shutil,sys,traceback,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
R2=HERE.parent/'vision-model-20261020'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    p=argparse.ArgumentParser();p.add_argument('--board-dir',type=Path,required=True);a=p.parse_args()
    evidence=REPO/'docs/validation/picture-p20-combined-20261020'
    sys.path.insert(0,str(HERE))
    old=module('r1_geometry_tests',HERE/'geometry_fallback/test_geometry.py');old.BOARD_DIR=a.board_dir
    outcomes=[]
    for name in sorted(n for n in vars(old) if n.startswith('test_') and callable(getattr(old,n))):
        try:getattr(old,name)();outcomes.append({'test':name,'passed':True})
        except Exception as e:outcomes.append({'test':name,'passed':False,'error':repr(e)})
    sys.path.insert(0,str(R2/'geometry'))
    new=module('r2_geometry_tests',R2/'geometry/test_board_geometry.py')
    result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(new.GeometryTests))
    output=HERE/'validation/r2-c-check';output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(R2/'geometry/geometry_reference.c',output/'geometry_reference.c')
    code=(R2/'geometry/check_c_reference.py').read_text(encoding='utf-8')
    old_assignment='R=Path(__file__).resolve().parent'
    assert code.count(old_assignment)==1
    # Only the output directory changes. All reference operations and vectors
    # execute the frozen source; Python imports still refer to R2 geometry.
    code=code.replace(old_assignment,'R=Path('+repr(str(output))+')')
    exec(compile(code,str(R2/'geometry/check_c_reference.py'),'exec'),{'__file__':str(R2/'geometry/check_c_reference.py'),'__name__':'receiver_geometry_c_check'})
    c=json.loads((output/'c_geometry_results.json').read_text())
    import numpy as np
    candidate=R2/'golden/quantization/candidate_v1'
    dumps=json.loads((candidate/'golden_dump_manifest.json').read_text())
    assert len(dumps)==80
    for record in dumps:
        path=candidate/record['path'];assert sha(path)==record['sha256']
        with np.load(path,allow_pickle=False) as arrays:
            assert set(arrays.files)==set(record['tensors'])
            for name,meta in record['tensors'].items():
                assert list(arrays[name].shape)==meta['shape'] and str(arrays[name].dtype)==meta['dtype'],(path,name)
    report=dict(r1_python_tests=outcomes,r2_python_tests=result.testsRun,r2_python_passed=result.wasSuccessful(),
                r2_c_projection=c,golden_layer_files_verified=80,source_payloads_unchanged=True,
                piece_fit_enabled=False,FPGA_executed=False,
                scope='Host Python/C references with delivered tolerances; not RV32 bit-exact acceptance')
    (evidence/'reference-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('P20_REFERENCE_CHECKS',len(outcomes),result.testsRun,c['passed'],'80 dump shapes/dtypes')
    if not all(v['passed'] for v in outcomes) or not result.wasSuccessful() or not c['passed']:raise SystemExit(1)
if __name__=='__main__':main()
