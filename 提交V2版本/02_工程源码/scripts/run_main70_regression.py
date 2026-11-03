"""Run the complete suite in a fresh regular Git worktree inside this workspace.

The accepted native tree and its generated artifacts are never test outputs.
The caller creates --test-root from the software freeze, preserving Git history
needed by historical SD contract tests. This helper never accesses a board.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from workspace_paths import workspace_path

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--test-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    source, target, out = map(workspace_path, (a.source, a.test_root, a.output))
    assert source != target and (target/'.git').is_file()
    out.mkdir(parents=True, exist_ok=False)
    tmp = out/'tmp'; tmp.mkdir()
    names = subprocess.check_output(['git','ls-files','-z'],cwd=source).decode().split('\0')
    inventory = {}
    for name in filter(None,names):
        src = source/name
        if not src.is_file(): continue
        assert not src.is_symlink() and src.resolve().is_relative_to(source.resolve())
        dst=target/name; dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst); inventory[name]=sha(src)
        assert sha(dst)==inventory[name]
    # Reviewable test-tool updates do not alter the native RTL/config/ROM.
    tool_source=Path(__file__).resolve().parent
    for name in ('simulation_tools.ps1','run_cpu_tests.ps1','test_program_cram_evidence.ps1'):
        shutil.copyfile(tool_source/name,target/'scripts'/name)
        inventory['scripts/'+name]=sha(tool_source/name)
    (out/'inputs.json').write_text(json.dumps(inventory,indent=2)+'\n')
    cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(target/'scripts/run_all_tests.ps1'),
         '-IcarusBin','G:/fpga/workspace/tools/msys64/ucrt64/bin',
         '-MsysRoot','G:/fpga/workspace/tools/msys64',
         '-ToolchainBin','G:/fpga/workspace/tools/riscv32-gcc16/bin',
         '-PythonPath','G:/py/ana/python.exe',
         '-HostGccPath','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe',
         '-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-PllWslDistro','pikafish-verify',
         '-MacPeWslDistro','pikafish-verify',
         '-PolicyFixtureRoot','G:/fpga/performance_soc_lut_compact_20261025/prebuilt/cpu80-policy-fixture']
    record=dict(status='RUNNING_COMPLETE_SOC_REGRESSION_NOT_BOARD',owner_pid=os.getpid(),
                started_utc=datetime.now(timezone.utc).isoformat(),command=cmd,
                source=str(source),test_root=str(target),input_receipt_sha256=sha(out/'inputs.json'))
    def save(): (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    save()
    env=dict(os.environ,TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp))
    try:
        with (out/'regression.log').open('xb') as log:
            p=subprocess.run(cmd,cwd=target,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=7200)
        record['exit']=p.returncode
        assert p.returncode==0 and b'SOC_ALL_TESTS_PASS' in (out/'regression.log').read_bytes()
        record['status']='SOC_ALL_TESTS_PASS_NOT_BOARD'
    except Exception as e:
        record.update(status='FAILED_PRESERVED',error=repr(e)); raise
    finally:
        record.update(completed_utc=datetime.now(timezone.utc).isoformat(),
                      log_sha256=sha(out/'regression.log'))
        save()
    print(record['status'])

if __name__=='__main__': main()
