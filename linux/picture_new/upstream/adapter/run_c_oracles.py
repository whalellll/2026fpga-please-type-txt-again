"""Compile delivered C unchanged; outputs stay outside training packages."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--gcc',default='D:/LJL/WORK/msys64/ucrt64/bin/gcc.exe');a=p.parse_args()
    out=HERE/'validation';out.mkdir(exist_ok=True)
    evidence=REPO/'docs/validation/picture-p20-combined-20261020'
    env=dict(os.environ);env['PATH']=str(Path(a.gcc).parent)+os.pathsep+env['PATH']
    jobs=[('fallback',[HERE/'geometry_fallback/c_ref/geometry_ref.c',HERE/'geometry_fallback/c_ref/test_harness.c'],
           [str(HERE/'geometry_fallback/test_vectors/vectors.tsv')],None,HERE,'30/30 passed'),
          ('integer',[HERE.parent/'vision-model-20261020/golden/quantization/golden_mac_reference.c'],[],
           HERE.parent/'vision-model-20261020/golden/quantization/candidate_v1/golden_mac_vectors.txt',
           HERE.parent/'vision-model-20261020/golden/quantization/candidate_v1','C_GOLDEN_PASSED 323')]
    results=[]
    for name,sources,args,stdin,cwd,marker in jobs:
        exe=out/(name+'-oracle.exe')
        command=[a.gcc,'-std=c11','-O2','-Wall','-Wextra',*map(str,sources),'-lm','-o',str(exe)]
        compiled=subprocess.run(command,env=env,capture_output=True,timeout=60)
        if compiled.returncode:raise RuntimeError(compiled.stderr.decode(errors='replace'))
        run=subprocess.run([str(exe),*args],cwd=cwd,env=env,input=stdin.read_bytes() if stdin else None,capture_output=True,timeout=60)
        stdout=run.stdout.decode(errors='replace');stderr=run.stderr.decode(errors='replace')
        (evidence/(name+'-c.stdout.txt')).write_text(stdout,encoding='utf-8')
        result=dict(name=name,command=command,source_sha256={str(p):sha(p) for p in sources},
                    binary_sha256=sha(exe),compiler_sha256=sha(Path(a.gcc)),exit_code=run.returncode,
                    compiler_warnings=compiled.stderr.decode(errors='replace'),stderr=stderr,marker=marker,
                    passed=run.returncode==0 and marker in stdout,scope='Host C reference; not RV32/device bit-exact acceptance')
        results.append(result);print('P20_C_ORACLE',name,result['passed'],stdout.splitlines()[-1:] if stdout else stderr)
    (evidence/'c-reference-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
