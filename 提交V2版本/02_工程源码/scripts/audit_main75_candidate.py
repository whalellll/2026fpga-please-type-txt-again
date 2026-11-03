"""Exact CPU75 native/ROM/STA identity for CRAM testing; not release audit."""
from pathlib import Path
import argparse,copy,hashlib,json
from workspace_paths import workspace_path
RUN='9302a6212eac40b08fae353321f31d1c'
COMMIT='7cabd17a564f5b6d7e25a0fa68cdae8305b4ea64'
BIT='d2ab7f6dfdbfdb7def8fba6f872ba3ce302ee1b914bee093477060ff97939675'
EVIDENCE='13b3d0da83a361e695ba57621c6e4c5e96568141ad4a057539763de9f26a77bf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def contract(record):
    assert record['status']=='CPU75_JOINT_FULL_REGRESSION_ROUTED_ALL_CORNER_STA_AND_HASH_READBACK_PASS_NOT_BOARD'
    assert record['native_run']==RUN and record['source_commit']==COMMIT
    assert record['bitstream_sha256']==BIT and record['build_evidence_sha256']==EVIDENCE
    assert record['cpu_hz']==75000000 and record['sys_hz']==49500000
    assert record['timing_scope']==dict(clocks=18,summary_rows=116,unconstrained_ports=187,status='PASS_WITH_DISCLOSED_BASELINE_IO_GAPS')
    assert record['cpu_timing']==[{'check': 'Setup', 'corner': 'Slow', 'launch': 'cpu_clk', 'capture': 'cpu_clk', 'wns_ns': 0.191, 'tns_ns': 0.0, 'violating_endpoints': 0, 'total_endpoints': 68313}, {'check': 'Hold', 'corner': 'Slow', 'launch': 'cpu_clk', 'capture': 'cpu_clk', 'wns_ns': 0.141, 'tns_ns': 0.0, 'violating_endpoints': 0, 'total_endpoints': 68313}, {'check': 'Setup', 'corner': 'Fast', 'launch': 'cpu_clk', 'capture': 'cpu_clk', 'wns_ns': 5.066, 'tns_ns': 0.0, 'violating_endpoints': 0, 'total_endpoints': 68313}, {'check': 'Hold', 'corner': 'Fast', 'launch': 'cpu_clk', 'capture': 'cpu_clk', 'wns_ns': 0.105, 'tns_ns': 0.0, 'violating_endpoints': 0, 'total_endpoints': 68313}]

def validate(root,native_result,bitstream):
    logical=Path(root).absolute();root=workspace_path(root)
    assert root==logical,'Use a regular worktree, not an alias'
    r=read(native_result);contract(r)
    assert sha(bitstream)==BIT==sha(root/'artifacts/soc_top.sbit')
    epath=root/'artifacts/build_evidence.json';assert sha(epath)==EVIDENCE
    e=read(epath);snap=read(root/'pds/build_snapshot.json')
    assert snap['run_id']==e['run_id']==RUN and len(snap['inputs'])==517
    assert sha(root/'pds/build_snapshot.json')==e['input_snapshot_sha256']==sha(root/'artifacts/build_snapshot.json')
    assert e['timing']=='All Constraints Met' and e['max_skew_verified'] and e['timing_scope_verified']
    assert e['max_skew_rows']==20 and e['timing_scope']==r['timing_scope']
    maps={'inputs':snap['inputs'],'reports':e['report_hashes'],'outputs':e['outputs']}
    assert len(maps['reports'])==46 and len(maps['outputs'])==49
    for label,mapping in maps.items():
        for rel,h in mapping.items():
            p=root/rel;assert p.is_relative_to(root) and p.is_file() and not p.is_symlink()
            assert sha(p)==h,label+': '+rel
    csr=read(root/'artifacts/cpu75_csr_placement.json')
    assert csr['status']=='CPU75_CSR_NATIVE_STRICT_EXECUTION_AND_FINAL_SITES_PASS_NOT_STA_OR_BOARD'
    assert csr['cells']==32 and csr['run_id']==RUN and csr['snapshot_sha256']==sha(root/'pds/build_snapshot.json')
    cfg=read(root/'config/clocks.json')
    assert cfg['cpu_hz']==75000000 and cfg['sys_hz']==49500000 and cfg['cpu_clock_source']=='dedicated675'
    return dict(status='EXACT_MAIN75_NATIVE_ROM_STA_INPUTS_OUTPUTS_PASS_NOT_FORMAL_RELEASE',
        source_ref=COMMIT,run_id=RUN,bitstream_sha256=BIT,firmware_binary_sha256=sha(root/'artifacts/bootloader.bin'),
        cpu_rtl_sha256=sha(root/'rtl/cpu/CoreTop.sv'),cpu_source_manifest_sha256=sha(root/'rtl/cpu/source.json'),
        pds_snapshot_sha256=sha(root/'pds/build_snapshot.json'),pds_build_evidence_sha256=EVIDENCE,
        native_result_sha256=sha(native_result),audit_script_sha256=sha(Path(__file__)),
        frozen_inputs=517,native_reports=46,native_outputs=49,raw_sta_summary_rows=116,raw_sta_max_skew_rows=20,
        formal_sta_pass=True,native_preflight_complete=True,formal_release=False,
        scope='Exact frozen hardware candidate only. Full release documentation, board/performance/model/SD/package acceptance remain separate; baseline187 I/O gaps retained.')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True);ap.add_argument('--native-result',type=Path,required=True)
    ap.add_argument('--bitstream',type=Path,required=True);ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args();result=validate(a.root,a.native_result,a.bitstream)
    if a.self_test:
        original=read(a.native_result)
        variants={'cpu_hz':60000000,'sys_hz':75000000,'native_run':'0'*32,'source_commit':'0'*40,'bitstream_sha256':'0'*64,'build_evidence_sha256':'0'*64,'timing_scope':{},'cpu_timing':{}}
        for name,value in variants.items():
            bad=copy.deepcopy(original);bad[name]=value
            try:contract(bad)
            except AssertionError:continue
            raise AssertionError('Bad candidate accepted: '+name)
        result['rejected_identity_mutations']=len(variants)
    print(json.dumps(result))

if __name__=='__main__':main()
