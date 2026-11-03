"""Bind frozen native resources, actual cache/pads and reviewed checker updates."""
from pathlib import Path
import argparse, hashlib, json
from report_pikafish_resources import read
from pikafish_dedicated_resource_contract import pikafish_dedicated_resource_contract
from vision32_resource_contract import vision32_resource_contract
from audit_pikafish_linear_hold_ads import audit
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--cache-evidence',type=Path)
    ap.add_argument('--cpu-evidence',type=Path)
    ap.add_argument('--load-evidence',type=Path)
    ap.add_argument('--clock-resource-evidence',type=Path)
    a=ap.parse_args()
    assert not a.output.exists();n=a.native_root.resolve()
    receipt=json.loads((n/'resource-evidence/result.json').read_text(encoding='utf-8-sig'))
    assert receipt['status']=='SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
    allowed={
      'scripts/audit_cpu_dedicated_pll_ads.py':'Replace fixed video12DRM component only after verifying actual eight packed video primitives, modes, bank/row/clock pins and native subtree; all PLL and exact aggregate requirements retained',
      'scripts/audit_cpu_ads.py':'Identify permuted exception-packed LSU load pins by the exact named controls and native OR producer; architectural Boolean oracle unchanged, five equivalent packings and twelve native faults checked',
      'scripts/audit_cpu85_half_ads.py':'Direct three-export PMA1024-case proof; unchanged CPU oracle, five native faults rejected',
      'scripts/vision32_cache_contract.py':'Actual full hierarchical WE ROBDD proof for split1024+128 cache and all36 decoders; eleven native faults rejected',
      'scripts/audit_pikafish_linear_hold_ads.py':'Account for four provably constant activation sign bits; 56 live DI pads and64 DI bindings',
      'scripts/pikafish_dedicated_resource_contract.py':'Exact measured optional voice scalar epilogue footprint and register-file rejection',
      'scripts/build_cpu_ads_gate.ps1':'Correct live-DI count and dedicated-profile guard',
      'scripts/build_fpga.ps1':'Consume original preflight hold proof and require all16 routed identity LUTs',
      'scripts/build_snapshot.ps1':'Dedicated hold-profile detection only; all actual RTL/clock/constraint inputs fixed'}
    changes={}
    for rel,h in receipt['inputs'].items():
        assert sha(n/rel)==h,('Frozen native input changed',rel)
        if sha(ROOT/rel)!=h:
            assert rel in allowed,('Unreviewed source difference',rel)
            changes[rel]=dict(frozen=h,current=sha(ROOT/rel),reason=allowed[rel])
    cache_evidence=None
    if 'scripts/vision32_cache_contract.py' in changes:
        assert a.cache_evidence,'Changed cache checker requires same-VM negative evidence'
        c=json.loads(a.cache_evidence.read_text())
        assert c['status']=='VISION32_NATIVE_CACHE_PORTS_CAPACITY_DECODERS_AND_MUTATIONS_PASS_NOT_STA'
        assert c['native_vm_sha256']==sha(n/'pds/synthesize/soc_top_syn.vm')
        assert c['checker_sha256']==sha(ROOT/'scripts/vision32_cache_contract.py') and c['rejected_mutations']==11
        assert c['positive']['weight_mapping']=='split_1024_128' and c['positive']['weight_decoder_roots_proven']==36
        assert c['positive']['native_read_boundary']['proof_method']=='complete hierarchical ROBDD equality'
        cache_evidence=dict(path=a.cache_evidence.as_posix(),sha256=sha(a.cache_evidence))
    cpu_evidence=None
    if 'scripts/audit_cpu_ads.py' in changes:
        assert a.cpu_evidence and a.load_evidence,'Changed CPU structural checker requires full same-VM audit and native faults'
        cpu=json.loads(a.cpu_evidence.read_text());load=json.loads(a.load_evidence.read_text())
        vm_hash=sha(n/'pds/synthesize/soc_top_syn.vm')
        assert cpu['status']=='PASS' and cpu['netlist_sha256']==vm_hash
        assert [cpu[k] for k in ['frontend_cases','return_cases','pma_address_cases','rsmem_hint_cases']]==[85760,10240,2144,17152]
        assert load['status']=='NATIVE_LSU_LOAD_PIN_PACKING_AND_12_FAULTS_PASS_NOT_STA'
        assert load['netlist_sha256']==vm_hash and load['rejected_mutations']==12 and len(load['equivalent_permutations'])==5
        assert cpu['audit_script_sha256']==load['audit_script_sha256']==sha(ROOT/'scripts/audit_cpu_ads.py')
        assert load['test_script_sha256']==sha(ROOT/'scripts/test_integrated60_load_packing.py')
        cpu_evidence=[dict(path=p.as_posix(),sha256=sha(p)) for p in [a.cpu_evidence,a.load_evidence]]
    clock_evidence=None
    if 'scripts/audit_cpu_dedicated_pll_ads.py' in changes:
        assert a.clock_resource_evidence,'Changed clock/resource checker requires same-VM native fault evidence'
        c=json.loads(a.clock_resource_evidence.read_text())
        assert c['status']=='PACKED_VIDEO_CLOCK_RESOURCE_NATIVE_AND_SEVEN_FAULTS_PASS_NOT_STA'
        assert c['native_vm_sha256']==sha(n/'pds/synthesize/soc_top_syn.vm') and c['rejected_mutations']==7
        assert c['audit_script_sha256']==sha(ROOT/'scripts/audit_cpu_dedicated_pll_ads.py')
        assert c['test_script_sha256']==sha(ROOT/'scripts/test_integrated60_clock_resources.py')
        assert c['positive']['cpu_hz']==60000000 and c['positive']['video_resources']['drm']==8
        assert c['positive']['resources']['drm']==133.5 and c['positive']['resources']['apm']==105
        clock_evidence=dict(path=a.clock_resource_evidence.as_posix(),sha256=sha(a.clock_resource_evidence))
    vm=n/'pds/synthesize/soc_top_syn.vm';snr=n/'pds/synthesize/soc_top.snr'
    text=vm.read_text();report=snr.read_text();top=(n/'rtl/soc/soc_top.v').read_text()
    protected=pikafish_dedicated_resource_contract(text,report,top)
    vision=vision32_resource_contract(text,report);hold=audit(text);counts=read(snr)['total']
    assert counts['lut']<=66600 and counts['ff']<=133200 and counts['drm36k']<=140 and counts['apm']<=195
    assert protected['voice_quant'] and hold['padded_di_pins']==56
    result=dict(status='INTEGRATED_OPT60_NATIVE_RESOURCE_AND_RETAINED_ENGINES_PASS_NOT_STA_OR_BOARD',
                native_root=n.as_posix(),whole_chip=counts,pikafish_voice=protected,vision=vision,hold=hold,
                frozen_inputs=len(receipt['inputs']),reviewed_checker_changes=changes,
                native_vm_sha256=sha(vm),native_snr_sha256=sha(snr),native_receipt_sha256=sha(n/'resource-evidence/result.json'),
                cache_mutation_evidence=cache_evidence,
                cpu_structural_checker_evidence=cpu_evidence,
                clock_resource_checker_evidence=clock_evidence,
                checker_sha256=sha(Path(__file__)))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],counts=counts)))
if __name__=='__main__':main()
