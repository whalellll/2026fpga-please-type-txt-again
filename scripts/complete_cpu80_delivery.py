"""Extract an immutable CPU80 ZIP, run full regression, bind completion to ZIP SHA256.

No FPGA, UART, Flash, SD or remote Git operation is performed.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, subprocess, sys, time
sys.dont_write_bytecode = True
from verify_cpu80_delivery import validate, check_zip, sha, need, read, RUN, CPU, RTL, BIT

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zip', type=Path, required=True)
    ap.add_argument('--extract', type=Path, required=True)
    ap.add_argument('--evidence', type=Path, required=True)
    ap.add_argument('--tools', type=Path, default=Path('G:/fpga/workspace/tools'))
    ap.add_argument('--pds', default='G:/fpga/PDS_2022.2-SP6.4')
    ap.add_argument('--pll-wsl-distro', default='pikafish-verify')
    a = ap.parse_args()
    need(not a.extract.exists() and not a.evidence.exists(), 'Use fresh extraction/evidence directories')
    a.evidence.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    record = dict(status='RUNNING', owner_pid=os.getpid(), started_utc=started,
                  archive=str(a.zip.resolve()), archive_sha256=sha(a.zip), run_id=RUN,
                  cpu_implementation_commit=CPU, cpu_rtl_sha256=RTL, bitstream_sha256=BIT,
                  extraction=str(a.extract.resolve()), commands=[])
    receipt = a.evidence/'result.json'
    def save(): receipt.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    save()
    gcc = str(a.tools/'msys64/mingw64/bin/gcc.exe')
    env = os.environ.copy()
    env['PATH'] = str(a.tools/'msys64/ucrt64/bin')+';'+str(a.tools/'msys64/mingw64/bin')+';'+env['PATH']
    def run(name, command, root, marker=None, timeout=3600):
        log = a.evidence/(name+'.log')
        entry = dict(name=name, command=list(map(str, command)), cwd=str(root), started_utc=datetime.now(timezone.utc).isoformat())
        record['commands'].append(entry); save()
        print('DELIVERY_CHECK_START '+name, flush=True)
        with log.open('wb') as out:
            proc = subprocess.Popen(entry['command'], cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
            entry['pid']=proc.pid; save()
            try: code=proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
                raise RuntimeError('Owned delivery check exceeded timeout: '+name)
        entry.update(exit_code=code, completed_utc=datetime.now(timezone.utc).isoformat(), log_sha256=sha(log))
        save(); need(code==0, name+' failed; inspect '+str(log))
        if marker: need(marker.encode() in log.read_bytes(), name+' completion marker missing')
        print('DELIVERY_CHECK_PASS '+name, flush=True)
    try:
        manifest=check_zip(a.zip)
        from zipfile import ZipFile
        a.extract.mkdir(parents=True)
        with ZipFile(a.zip) as z: z.extractall(a.extract)
        root=a.extract/'SOC'
        record['evidence_verification']=validate(root,gcc)
        frozen=read(root/'artifacts/build_snapshot.json')['inputs']
        before_build={n:read(root/n) for n in frozen if n.endswith('.build.json')}
        run('negative-policy',[sys.executable,'-B','scripts/test_cpu80_delivery.py','--root',root],root,timeout=300)
        run('skills',[sys.executable,'-B','skills/manage.py','verify-delivery','--package',root],root,'SKILLS_PASS',300)
        run('directory-index',[sys.executable,'-B','scripts/update_project_index.py','--project-root',root,'--check'],root,'PROJECT_DIRECTORY_INDEX_PASS',300)
        run('project-audit',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',root/'scripts/audit_project.ps1','-Root',root],root,'PASS',900)
        command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',root/'scripts/run_all_tests.ps1',
                 '-IcarusBin',a.tools/'msys64/ucrt64/bin','-MsysRoot',a.tools/'msys64',
                 '-ToolchainBin',a.tools/'riscv32-gcc16/bin','-PythonPath',sys.executable,
                 '-HostGccPath',gcc,'-PdsRoot',a.pds,'-PllWslDistro',a.pll_wsl_distro,
                 '-PolicyFixtureRoot',root/'prebuilt/cpu80-policy-fixture']
        run('full-regression',command,root,'SOC_ALL_TESTS_PASS',7200)
        changed={n:sha(root/n) for n,d in frozen.items() if sha(root/n)!=d}
        need(all(n in before_build for n in changed), 'Rebuilt frozen source/binary differs: '+str(changed))
        # Build receipts embed absolute host paths. Compare their semantic output
        # and input contracts while recording both original and rebuilt receipts.
        metadata={}
        for n in changed:
            old=before_build[n]; new=read(root/n)
            metadata[n]=dict(original_sha256=frozen[n], rebuilt_sha256=changed[n], old=old, rebuilt=new)
            need(old==new, 'Rebuilt firmware metadata differs: '+n)
        record['rebuilt_metadata']=metadata
        record['firmware_bytes_identical']=True
        record['frozen_inputs_unchanged_except_host_build_receipts']=True
        need(sha(a.zip)==record['archive_sha256'],'Archive changed during verification')
        record.update(status='CPU80_CLEAN_DELIVERY_PASS', completed_utc=datetime.now(timezone.utc).isoformat(),
                      files_in_archive=len(manifest['files_sha256']), frozen_inputs=len(frozen),
                      hdmi='USER_CONFIRMED', native_sta_rows=116,
                      note='Full regression ran from independent ZIP extraction; host build receipts retained. No board or remote operation.')
        save()
        print(json.dumps({k:v for k,v in record.items() if k not in ['commands','rebuilt_metadata']},indent=2),flush=True)
    except Exception as e:
        record.update(status='CPU80_DELIVERY_VERIFICATION_FAILED', error=str(e), completed_utc=datetime.now(timezone.utc).isoformat());save();raise

if __name__=='__main__':main()
