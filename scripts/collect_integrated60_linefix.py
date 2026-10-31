"""Collect the distinct native-line fix after the complete physical flow passes."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,shutil,subprocess,sys
from report_pikafish_resources import read as counts
from vision32_resource_contract import vision32_resource_contract
from pikafish_dedicated_resource_contract import pikafish_dedicated_resource_contract
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native-root',type=Path,default=Path('G:/i60pnr4'));a=ap.parse_args()
    n=a.native_root.resolve();launch=read(n/'physical-launch.json');snap=read(n/'pds/build_snapshot.json')
    assert launch['status']=='ROUTED_FULL_STA_PASS_NOT_BOARD' and launch['pnr_complete']
    assert launch['run_id']==snap['run_id']=='dc951f8b1b7f4cf9962e5f509f165d0f'
    assert launch['native_line_fix'] and launch['source_commit']=='e8d666add46987aec84778890b4aacda74ca6586'
    proof=read(n/'artifacts/build_evidence.json')
    assert proof['run_id']==launch['run_id'] and proof['timing']=='All Constraints Met'
    assert proof['timing_scope_verified'] and proof['max_skew_verified']
    for rel,h in snap['inputs'].items():
        assert sha(n/rel)==h,rel
        if not rel.startswith('scripts/') and rel!='VERSION':assert sha(R/rel)==h,rel
    for rel,h in launch['reports'].items():assert sha(n/'pds'/rel)==h,rel
    candidate=R/'artifacts/integrated60_linefix_20261024';evidence=R/'docs/validation/integrated60-linefix-physical-20261024'
    assert not candidate.exists() and not evidence.exists()
    vm=(n/'pds/synthesize/soc_top_syn.vm').read_text();snr=(n/'pds/synthesize/soc_top.snr').read_text()
    resources=dict(whole_chip=counts(n/'pds/synthesize/soc_top.snr')['total'],
        vision=vision32_resource_contract(vm,snr),
        retained=pikafish_dedicated_resource_contract(vm,snr,(n/'rtl/soc/soc_top.v').read_text()))
    candidate.mkdir();evidence.mkdir()
    subprocess.run([sys.executable,str(R/'scripts/report_pikafish_physical.py'),'--native-root',str(n),'--output',str(evidence/'physical-summary.json')],check=True)
    summary=read(evidence/'physical-summary.json');assert not summary['violations'] and summary['summary_row_count']==116
    bit=n/'pds/generate_bitstream/soc_top.sbit';shutil.copyfile(bit,candidate/'soc_top.sbit')
    assert sha(bit)==sha(candidate/'soc_top.sbit')
    for name,p in {'physical-launch.json':n/'physical-launch.json','build_snapshot.json':n/'pds/build_snapshot.json',
                   'build_evidence.json':n/'artifacts/build_evidence.json','pnr-history.json':n/'pnr-history.json'}.items():
        shutil.copyfile(p,evidence/name);assert sha(p)==sha(evidence/name)
    for rel in ['report_timing/soc_top.rtr','report_timing/rtr.db','synthesize/soc_top.snr']:
        p=n/'pds'/rel;(evidence/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
        assert gzip.decompress((evidence/(p.name+'.gz')).read_bytes())==p.read_bytes()
    result=dict(status='INTEGRATED60_NATIVE_LINE_FIX_FULL_PHYSICAL_STA_PASS_NOT_BOARD',created_utc=datetime.now(timezone.utc).isoformat(),
        run_id=launch['run_id'],native_root=str(n),physical_source_commit=launch['source_commit'],hardware_implementation_commit='3fab80f',
        cpu_hz=60000000,sys_hz=49500000,display='1080p30',native_line_fix=True,sta_pass=True,strict_original_flow_pass=True,independent_review_pass=False,
        bitstream=dict(path='soc_top.sbit',bytes=bit.stat().st_size,sha256=sha(bit)),resources=resources,sta_focus=summary['focus'],
        evidence_root=str(evidence.relative_to(R)),evidence_sha256={p.name:sha(p) for p in evidence.iterdir()},
        model_policy='Existing byte-exact Picture_new three graphs and balanced24; streamed voice software/SD bound separately',
        board=False,sd=False,flash=False,pushed=False,formal_delivery=False,
        scope='New native-line RTL fix; complete physical-flow pass does not replace paired software, real SD boot or image/voice functional acceptance.')
    data=json.dumps(result,indent=2)+'\n';(candidate/'manifest.json').write_text(data);(evidence/'summary.json').write_text(data)
    print(result['status'],result['bitstream']['sha256'])

if __name__=='__main__':main()
