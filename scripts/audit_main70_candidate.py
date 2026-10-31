"""Exact CPU70 native/ROM/STA identity for CRAM testing; not release audit."""
from pathlib import Path
import argparse,copy,hashlib,json
from workspace_paths import workspace_path
RUN='6d01c26066a1467690d01ca479739158'
COMMIT='c50bb15873dda846cce2863d99c92ff9aa665167'
BIT='24226a3a2cf41e96554e4f4ea677f133964cbf942993cb1f751c60c5928a8a02'
EVIDENCE='f32a6dc1b32f982c8841f349ebc2c4669ab26800851604ed99bcba1101a7fd6a'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def contract(record):
    assert record['status']=='MERGED_MAIN_CPU70_SYNTHESIS_ROUTE_FINAL_ALL_CORNER_STA_AND_HASH_READBACK_PASS_NOT_BOARD'
    assert record['native_run']==RUN and record['source_commit']==COMMIT
    assert record['bitstream_sha256']==BIT and record['build_evidence_sha256']==EVIDENCE
    assert record['cpu_hz']==70000000 and record['sys_hz']==49500000
    assert record['timing_scope']==dict(clocks=18,summary_rows=116,unconstrained_ports=187,status='PASS_WITH_DISCLOSED_BASELINE_IO_GAPS')
    assert record['cpu_timing']==dict(setup_slow_ns=.394,setup_fast_ns=5.412,hold_slow_ns=.158,hold_fast_ns=.118)

def validate(root,native_result,bitstream):
    logical=Path(root).absolute();root=workspace_path(root)
    assert root==logical,'Use a regular worktree, not an alias'
    r=read(native_result);contract(r)
    assert sha(bitstream)==BIT==sha(root/'artifacts/soc_top.sbit')
    epath=root/'artifacts/build_evidence.json';assert sha(epath)==EVIDENCE
    e=read(epath);snap=read(root/'pds/build_snapshot.json')
    assert snap['run_id']==e['run_id']==RUN and len(snap['inputs'])==513
    assert sha(root/'pds/build_snapshot.json')==e['input_snapshot_sha256']==sha(root/'artifacts/build_snapshot.json')
    assert e['timing']=='All Constraints Met' and e['max_skew_verified'] and e['timing_scope_verified']
    assert e['max_skew_rows']==20 and e['timing_scope']==r['timing_scope']
    maps={'inputs':snap['inputs'],'reports':e['report_hashes'],'outputs':e['outputs']}
    assert len(maps['reports'])==42 and len(maps['outputs'])==47
    for label,mapping in maps.items():
        for rel,h in mapping.items():
            p=root/rel;assert p.is_relative_to(root) and p.is_file() and not p.is_symlink()
            assert sha(p)==h,label+': '+rel
    cfg=read(root/'config/clocks.json')
    assert cfg['cpu_hz']==70000000 and cfg['sys_hz']==49500000 and cfg['cpu_clock_source']=='dedicated945frac'
    return dict(status='EXACT_MAIN70_NATIVE_ROM_STA_INPUTS_OUTPUTS_PASS_NOT_FORMAL_RELEASE',
        source_ref=COMMIT,run_id=RUN,bitstream_sha256=BIT,firmware_binary_sha256=sha(root/'artifacts/bootloader.bin'),
        cpu_rtl_sha256=sha(root/'rtl/cpu/CoreTop.sv'),cpu_source_manifest_sha256=sha(root/'rtl/cpu/source.json'),
        pds_snapshot_sha256=sha(root/'pds/build_snapshot.json'),pds_build_evidence_sha256=EVIDENCE,
        native_result_sha256=sha(native_result),audit_script_sha256=sha(Path(__file__)),
        frozen_inputs=513,native_reports=42,native_outputs=47,raw_sta_summary_rows=116,raw_sta_max_skew_rows=20,
        formal_sta_pass=True,native_preflight_complete=True,formal_release=False,
        scope='Exact frozen hardware candidate only. Full release documentation, board/performance/model/SD/package acceptance remain separate; baseline187 I/O gaps retained.')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True);ap.add_argument('--native-result',type=Path,required=True)
    ap.add_argument('--bitstream',type=Path,required=True);ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args();result=validate(a.root,a.native_result,a.bitstream)
    if a.self_test:
        original=read(a.native_result)
        variants={'cpu_hz':60000000,'sys_hz':70000000,'native_run':'0'*32,'source_commit':'0'*40,'bitstream_sha256':'0'*64,'build_evidence_sha256':'0'*64,'timing_scope':{},'cpu_timing':{}}
        for name,value in variants.items():
            bad=copy.deepcopy(original);bad[name]=value
            try:contract(bad)
            except AssertionError:continue
            raise AssertionError('Bad candidate accepted: '+name)
        result['rejected_identity_mutations']=len(variants)
    print(json.dumps(result))

if __name__=='__main__':main()
