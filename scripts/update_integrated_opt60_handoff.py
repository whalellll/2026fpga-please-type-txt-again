"""Refresh only the new optimization block; preserve prior board evidence."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase')
    ap.add_argument('--native-root',type=Path)
    ap.add_argument('--resource-evidence',type=Path)
    ap.add_argument('--publication-receipt',type=Path)
    a = ap.parse_args()
    out = ROOT/'build/integrated-opt60-status.json'
    prior = json.loads(out.read_text()) if out.exists() else {}
    checks = {}
    for p in sorted((ROOT/'build').glob('opt60-*/result.json')):
        d = json.loads(p.read_text(encoding='utf-8-sig'))
        checks[p.parent.name] = dict(status=d.get('status'), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    state = dict(updated_utc=datetime.now(timezone.utc).isoformat(),
                 source_root=ROOT.as_posix(),
                 branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
                 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                 phase=a.phase or prior.get('phase','Integration and tests in progress; no native build yet'),
                 cpu_hz=60000000, sys_hz=49500000, display='1080p30',
                 checks=checks, native_root=a.native_root.as_posix() if a.native_root else prior.get('native_root'),
                 synthesis=False, final_sta=False, board=False, push=False, delivery=False)
    resource=a.resource_evidence or ROOT/prior.get('resource_evidence',{}).get('path','build/opt60-native-resources-01.json')
    resource=(resource if resource.is_absolute() else ROOT/resource).resolve()
    assert resource.is_relative_to(ROOT/'build'),'Resource evidence must be a local build receipt'
    if resource.exists():
        r=json.loads(resource.read_text());state['synthesis']=r['status']=='INTEGRATED_OPT60_NATIVE_RESOURCE_AND_RETAINED_ENGINES_PASS_NOT_STA_OR_BOARD'
        state['resource_evidence']=dict(path=resource.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(resource.read_bytes()).hexdigest(),counts=r['whole_chip'])
        frozen=Path(r['native_root'])/'resource-evidence/result.json'
        if frozen.exists():
            inputs=json.loads(frozen.read_text(encoding='utf-8-sig'))['inputs']
            accepted=r.get('reviewed_checker_changes',{})
            changed=[]
            for name,h in inputs.items():
                p=ROOT/name
                current=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
                if current!=h and current!=accepted.get(name,{}).get('current'):
                    changed.append(name)
            state['resource_source_differences']=changed
            state['synthesis']=state['synthesis'] and not changed
    if state['native_root']:
        native=Path(state['native_root']);launch=native/'physical-launch.json';snap=native/'pds/build_snapshot.json'
        if launch.exists():
            r=json.loads(launch.read_text(encoding='utf-8-sig'))
            state['physical_record']={k:r.get(k) for k in ['status','source_commit','owner_pid','started_utc','run_id','pnr_complete','error']}
            state['physical_record']['sha256']=hashlib.sha256(launch.read_bytes()).hexdigest()
            state['final_sta']=r['status']=='ROUTED_FULL_STA_PASS_NOT_BOARD'
        if snap.exists():
            r=json.loads(snap.read_text(encoding='utf-8-sig'));state['native_snapshot']=dict(run_id=r['run_id'],sha256=hashlib.sha256(snap.read_bytes()).hexdigest())
    publication=ROOT/'artifacts/INTEGRATED_OPT60_MAIN.json'
    if publication.exists():
        m=json.loads(publication.read_text())
        state['main_publication']=dict(status=m['status'], manifest_sha256=hashlib.sha256(publication.read_bytes()).hexdigest(),
                                      mixed_audio_pass=m['mixed_audio_pass'], formal_delivery=m['formal_delivery'])
        state['board']='MEASURED_WITH_MIXED_AUDIO_FAILURE'
    receipt=a.publication_receipt or (ROOT/prior['publication_receipt']['path'] if prior.get('publication_receipt') else None)
    if receipt:
        receipt=receipt.resolve()
        r=json.loads(receipt.read_text())
        assert r['status']=='MAIN_PUSH_REMOTE_COMMIT_AND_ARTIFACT_READBACK_PASS'
        state['push']=True
        state['publication_receipt']=dict(path=receipt.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),remote_commit=r['remote_commit'])
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(state,indent=2)+'\n')
    begin='<!-- INTEGRATED_OPT60_20261024_BEGIN -->'
    end='<!-- INTEGRATED_OPT60_20261024_END -->'
    block='\n'.join([begin,'## Integrated accelerator optimization CPU60 (2026-10-24)','',
        f"Source `{state['source_root']}`, branch `{state['branch']}`, HEAD `{state['head']}`.",
        'CPU60 / SYS49.5 / 1080p30. Baseline127ff9a + dedicated batch8ba3df6; old board and standalone batch evidence remain separate.',
        state['phase'],
        'Targets: reduce vision19444 small jobs and CPU graph overhead, profile and reduce voice CNN overhead, integrate batch ownership/ABI, repair lin_pack-to-LUTRAM hold.',
        f"Resource synthesis={state['synthesis']}; final STA={state['final_sta']}; board={state['board']}; push={state['push']}; formal delivery={state['delivery']}. Main publication={json.dumps(state.get('main_publication',{}),separators=(',',':'))}; remote readback={json.dumps(state.get('publication_receipt',{}),separators=(',',':'))}. Native root={state['native_root']}, physical record={json.dumps(state.get('physical_record',{}),separators=(',',':'))}, frozen snapshot={json.dumps(state.get('native_snapshot',{}),separators=(',',':'))}. Recorded PID must be rechecked against the live command before resuming or stopping a job.",
        f"Checks: {json.dumps(checks,separators=(',',':'))}.",
        'Plan and recovery: `performance_soc_integrated_opt60_20261024/docs/Integrated_Optimization_CPU60_20261024.md`; status `build/integrated-opt60-status.json`.',
        end])
    for p in [ROOT/'docs/CPU_Frequency_Handoff.md', ROOT.parent/'HANDOFF.md',
              ROOT.parent/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
        text=p.read_text(encoding='utf-8-sig') if p.exists() else '# FPGA/SoC handoff\n'
        if begin in text:
            assert text.count(begin)==text.count(end)==1
            text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1)
        else:
            first,_,tail=text.partition('\n');text=first+'\n\n'+block+'\n\n'+tail
        p.write_text(text,encoding='utf-8',newline='\n')
    print(state['phase'])

if __name__=='__main__':main()
