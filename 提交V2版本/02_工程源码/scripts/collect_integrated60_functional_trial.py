"""Freeze the user's functional CRAM trial while retaining native STA failure."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[1];N=Path('G:/i60pnr4')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    launch=read(N/'physical-launch.json');snap=read(N/'pds/build_snapshot.json')
    assert launch['status']=='ROUTED_STA_FAILED_NOT_BOARD' and launch['pnr_complete']
    assert launch['error']=='Final PDS report_timing constraints are not met'
    assert launch['run_id']==snap['run_id']=='dc951f8b1b7f4cf9962e5f509f165d0f'
    scope_test=R/'build/integrated-functional-scope-test-02.json';tested=read(scope_test)
    assert tested['status']=='FUNCTIONAL_SCOPE_ACTUAL_FAILURE_AND_SIX_FAULTS_CHECKED_NO_BOARD_ACCESS'
    assert tested['source_sha256']==sha(R/'scripts/review_integrated60_functional_trial.ps1')
    for rel,h in launch['reports'].items():assert sha(N/'pds'/rel)==h,rel
    for rel,h in snap['inputs'].items():
        assert sha(N/rel)==h,rel
        if not rel.startswith('scripts/') and rel!='VERSION':assert sha(R/rel)==h,rel
    e=R/'docs/validation/integrated60-linefix-functional-trial-20261024-02'
    c=R/'artifacts/integrated60_linefix_trial_20261024'
    assert not e.exists() and not c.exists();e.mkdir()
    subprocess.run([sys.executable,str(R/'scripts/report_pikafish_physical.py'),'--native-root',str(N),'--output',str(e/'physical-summary.json')],check=True)
    summary=read(e/'physical-summary.json')
    assert summary['summary_row_count']==116 and summary['violations']
    for row in summary['violations']:
        assert row['kind']=='hold' and row['clocks'] in [['cpu_clk','cpu_clk'],['sys_clk','sys_clk']]
        assert -.05<=row['wns_ns']<0 and 0<row['violating_endpoints']<=8,row
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(R/'scripts/review_integrated60_functional_trial.ps1'),'-OutputPath',str(e/'functional-coverage.json')],check=True)
    log=(N/'pds/input-snapshots'/snap['run_id']/'pds.stdout.log').read_text(errors='replace')
    assert 'Executing : gen_bit_stream ' in log and 'Process "Generate Bitstream" done.' in log
    assert not any(line.startswith('E:') for line in log.splitlines())
    bit=N/'pds/generate_bitstream/soc_top.sbit';assert bit.stat().st_size==3791112
    c.mkdir();shutil.copyfile(bit,c/'soc_top.sbit');assert sha(bit)==sha(c/'soc_top.sbit')
    for name,p in {'physical-launch.json':N/'physical-launch.json','build_snapshot.json':N/'pds/build_snapshot.json','scope-negative-tests.json':scope_test}.items():
        shutil.copyfile(p,e/name);assert sha(p)==sha(e/name)
    for rel in ['report_timing/soc_top.rtr','report_timing/rtr.db','synthesize/soc_top.snr']:
        p=N/'pds'/rel;(e/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    result=dict(status='INTEGRATED60_LINEFIX_FUNCTIONAL_TRIAL_STA_FAILED_NOT_RELEASE',run_id=snap['run_id'],
        created_utc=datetime.now(timezone.utc).isoformat(),native_root=str(N),cpu_hz=60000000,sys_hz=49500000,
        display='1080p30',native_line_fix=True,sta_pass=False,strict_original_flow_pass=False,
        functional_trial_authorized=True,bitstream=dict(path='soc_top.sbit',bytes=bit.stat().st_size,sha256=sha(bit)),
        violations=summary['violations'],sta_focus=summary['focus'],evidence_root=e.relative_to(R).as_posix(),
        evidence_sha256={p.name:sha(p) for p in e.iterdir()},board=False,flash=False,formal_delivery=False)
    (c/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');(e/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],sha(bit))
if __name__=='__main__':main()
