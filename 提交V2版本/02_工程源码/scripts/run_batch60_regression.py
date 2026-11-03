"""Run complete regression with explicit exit, log and implementation binding."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--attempt',required=True);a=ap.parse_args()
 stem=ROOT/'build'/('batch60-full-regression-'+a.attempt)
 log=stem.with_suffix('.log');assert not log.exists()
 sources=[]
 for directory in ('rtl','sw','ip','config','sim'):
  sources.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in ('.v','.sv','.c','.h','.json') and '__pycache__' not in p.parts)
 sources.extend(ROOT/'scripts'/name for name in ['run_all_tests.ps1','test_mac_open_service.py','clock_policy.ps1','audit_cpu_dedicated_pll_ads.py','pikafish_dedicated_resource_contract.py'])
 before={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
 command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/run_all_tests.ps1',
  '-IcarusBin','G:/fpga/workspace/tools/msys64/ucrt64/bin','-MsysRoot','G:/fpga/workspace/tools/msys64',
  '-ToolchainBin','G:/fpga/workspace/tools/riscv32-gcc16/bin','-PythonPath','G:/py/ana/python.exe',
  '-HostGccPath','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe','-PdsRoot','G:/fpga/PDS_2022.2-SP6.4',
  '-PllWslDistro','pikafish-verify','-PolicyFixtureRoot',str(ROOT/'prebuilt/cpu80-policy-fixture')]
 record=dict(status='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),command=command,sources_sha256=before)
 receipt=stem.with_suffix('.json');receipt.write_text(json.dumps(record,indent=2)+'\n')
 with log.open('xb') as f:r=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=7200)
 record.update(exit_code=r.returncode,completed_utc=datetime.now(timezone.utc).isoformat(),log_sha256=sha(log))
 record['sources_unchanged']=all(sha(ROOT/p)==h for p,h in before.items())
 passed=r.returncode==0 and record['sources_unchanged'] and b'SOC_ALL_TESTS_PASS' in log.read_bytes()
 record['status']='SOC_ALL_TESTS_PASS_NOT_BOARD' if passed else 'FAILED_PRESERVED_NOT_BOARD'
 receipt.write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
 if not passed:raise SystemExit(1)
if __name__=='__main__':main()
