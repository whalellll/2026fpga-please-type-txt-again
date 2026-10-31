import argparse,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--revision',choices=('r01','r02','r03','r04','r05','r06'),default='r01');args=p.parse_args()
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1];WORK=REPO/('build/picture-p21-native/regression-'+args.revision)
OUT=REPO/'docs/validation/picture-p21-runtime-20261020'
data=json.loads((WORK/'inputs.json').read_text());target=Path(data['isolation'])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for kind in ('sources','tests','linux'):
    for name,digest in data[kind].items():assert sha(REPO/name)==sha(target/name)==digest,(kind,name)
stdout=(WORK/'stdout.log').read_text(encoding='utf-8-sig',errors='replace');assert stdout.splitlines().count('SOC_ALL_TESTS_PASS')==1
receipts={}
for name in ('stdout','stderr'):
    dest=OUT/('regression-'+args.revision+'.'+name+'.txt');assert not dest.exists();shutil.copyfile(WORK/(name+'.log'),dest)
    receipts[name]=dict(path=dest.relative_to(REPO).as_posix(),sha256=sha(dest),bytes=dest.stat().st_size)
result=dict(schema_version=1,status='PASS',exit_code=0,marker='SOC_ALL_TESTS_PASS',recorded_utc=datetime.now(timezone.utc).isoformat(),
    scope='Current full functional suite in isolated checkout; NOT PnR, M0 or BoardRelease',source_files_sha256=data['sources'],
    test_files_sha256=data['tests'],linux_files_sha256=data['linux'],isolation=data['isolation'],
    working_tree_and_isolation_inputs_match_after_execution=True,transcript=receipts)
dest=OUT/('regression.json' if args.revision=='r01' else 'regression-'+args.revision+'.json');assert not dest.exists();dest.write_text(json.dumps(result,indent=2)+'\n')
print('P21_FULL_REGRESSION_ARCHIVED',*[len(data[k]) for k in ('sources','tests','linux')])
