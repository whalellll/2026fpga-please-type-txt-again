"""Run the standard complete regression with a durable exit/log receipt."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(R/'scripts/run_all_tests.ps1'),
 '-IcarusBin','G:/fpga/workspace/tools/msys64/ucrt64/bin','-MsysRoot','G:/fpga/workspace/tools/msys64',
 '-ToolchainBin','G:/fpga/workspace/tools/riscv32-gcc16/bin','-PythonPath','G:/py/ana/python.exe',
 '-HostGccPath','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe','-PdsRoot','G:/fpga/PDS_2022.2-SP6.4',
 '-PllWslDistro','pikafish-verify','-PolicyFixtureRoot',str(R/'prebuilt/cpu80-policy-fixture')]
files=list((R/'rtl').rglob('*.v'))+list((R/'rtl').rglob('*.sv'))+[R/'config/clocks.json',R/'pds/soc.fdc']
hashes={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
record=dict(status='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),command=cmd,source_sha256=hashes)
(out/'launch.json').write_text(json.dumps(record,indent=2)+'\n')
with (out/'run.log').open('wb') as log:r=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=7200)
body=(out/'run.log').read_bytes()
record.update(exit_code=r.returncode,completed_utc=datetime.now(timezone.utc).isoformat(),log_sha256=hashlib.sha256(body).hexdigest())
unchanged=all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
record['status']='SOC_ALL_TESTS_PASS_NOT_BOARD' if r.returncode==0 and b'SOC_ALL_TESTS_PASS' in body and unchanged else 'FAILED_PRESERVED'
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status']);raise SystemExit(0 if record['status'].startswith('SOC_ALL_TESTS_PASS') else 1)
