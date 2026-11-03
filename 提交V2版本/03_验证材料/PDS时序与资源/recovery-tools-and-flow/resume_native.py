"""Check preserved inputs or explicitly resume a new offline-only native attempt."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys
B=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--run',action='store_true')
p.add_argument('--attempt',type=int,default=2)
a=p.parse_args();assert 2<=a.attempt<=999
env=dict(os.environ,TEMP=str(B/'tmp'),TMP=str(B/'tmp'),TMPDIR=str(B/'tmp'),PYTHONDONTWRITEBYTECODE='1')
if not a.run:
    raise SystemExit(subprocess.run([sys.executable,'-X','utf8','-B',str(B/'run_pnr_compiler_only.py'),'--attempt',str(a.attempt),'--check-only'],cwd=B,env=env).returncode)
record_path=B/f'finish-native-flow{a.attempt:02}.json'
assert not record_path.exists(),'Use a fresh attempt number and preserve previous evidence'
assert not (B/f'pnr-{a.attempt:02}').exists(),'Use a fresh attempt number'
assert not (B/'final-review-02').exists(),'Review existing native final reports before starting another job'
q=dict(status='RUNNING_OFFLINE_ONLY',owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),attempt=a.attempt,steps=[])
def save():record_path.write_text(json.dumps(q,indent=2)+'\n')
save()
try:
    # Bind the existing report collector to the new attempt; preserve its old source.
    collector=B/f'collect_final_attempt{a.attempt:02}.py'
    assert not collector.exists()
    code=(B/'collect_final.py').read_text().replace("B/'pnr-01/input-binding.json'",f"B/'pnr-{a.attempt:02}/input-binding.json'").replace("pnr_attempt='pnr-01'",f"pnr_attempt='pnr-{a.attempt:02}'")
    assert f"B/'pnr-{a.attempt:02}/input-binding.json'" in code
    collector.write_text(code)
    steps=[('run_pnr_compiler_only.py',['--attempt',str(a.attempt)]),(collector.name,[]),('export_physical.py',[]),('verify_physical.py',[]),('generate_candidate_bitstream.py',[])]
    for name,extra in steps:
        log=B/(name.removesuffix('.py')+f'-attempt{a.attempt:02}.log');assert not log.exists()
        q['current_command']=name;save()
        with log.open('xb') as stream:
            child=subprocess.Popen([sys.executable,'-X','utf8','-B',str(B/name),*extra],cwd=B,env=env,stdout=stream,stderr=subprocess.STDOUT)
            q['child_pid']=child.pid;save();code=child.wait(timeout=15100 if name=='run_pnr_compiler_only.py' else 1200)
        q['steps'].append(dict(script=name,exit_code=code,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()));save()
        if code:raise RuntimeError(name+': '+log.read_text(errors='replace')[-4000:])
        if name==collector.name:assert json.loads((B/'final-review-02/result.json').read_text())['final_sta_pass']
    status=json.loads((B/'status.json').read_text())
    status.update(status='CPU125_CM60_ZERO_HARDWARE_DELTA_NATIVE_STA_PHYSICAL_BITSTREAM_PASS_BOARD_PENDING',
        final_sta_pass=True,new_bitstream_sta_pass=True,pnr_started=True,board_tested=False,main_merged=False,
        remote_pushed=False,formal_delivery=False,active_owner_pid=None,current_command='Offline native qualification completed; board deferred')
    (B/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    q.update(status=status['status'],child_pid=None,completed_utc=datetime.now(timezone.utc).isoformat());save()
except Exception as error:
    q.update(status='FAILED_PRESERVED',error=repr(error),completed_utc=datetime.now(timezone.utc).isoformat());save();raise
print(q['status'],flush=True)
