"""Bind a signed partial multiplier proof to the current frozen SoC and CPU."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,sys,traceback

HELPERS=Path(__file__).resolve().with_name('gui1080_mul')
sys.path.insert(0,str(HELPERS))
from inspect_mul_signed_mapping import audit
from native_sat_bits import z3
from profile_native_resources import profile
from verify_gui1080_cpu import validate_cpu

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def validate(root,baseline,contract_path,physical_review=None):
    root=Path(root).resolve();baseline=Path(baseline).resolve();contract_path=Path(contract_path).resolve()
    contract=read(contract_path);assert contract['status']=='GUI1080_MUL_CPU_CORRECTNESS_PAIRED_SOURCE_PASS_NOT_STA_OR_BOARD'
    cpu_proof=validate_cpu(contract_path)
    snap=read(root/'pds/build_snapshot.json');parent=read(baseline/'pds/build_snapshot.json')
    assert parent['run_id']=='68c91ab7662945f48247e660221e0c3a'
    cpu_changed={'rtl/cpu/CoreTop.sv','rtl/cpu/source.json','artifacts/bootloader.build.json'}
    if physical_review:
        from gui1080_physical import validate_review,delta_from_p3
        review=validate_review(root,physical_review)
        assert snap['inputs']==review['current_inputs']
        changed={n for n,h in snap['inputs'].items() if h!=parent['inputs'].get(n)}
        assert changed==cpu_changed|delta_from_p3(review),changed
    else:
        assert set(snap['inputs'])==set(parent['inputs']) and len(snap['inputs'])==461
        changed={n for n,h in snap['inputs'].items() if h!=parent['inputs'][n]}
        assert changed==cpu_changed,changed
    old_firmware=read(baseline/'artifacts/bootloader.build.json');new_firmware=read(root/'artifacts/bootloader.build.json')
    assert old_firmware['build_inputs']['rtl/cpu/source.json']==parent['inputs']['rtl/cpu/source.json']
    assert new_firmware['build_inputs']['rtl/cpu/source.json']==snap['inputs']['rtl/cpu/source.json']
    restored=json.loads(json.dumps(new_firmware));restored['build_inputs']['rtl/cpu/source.json']=old_firmware['build_inputs']['rtl/cpu/source.json']
    assert restored==old_firmware,'Firmware metadata changed beyond its exact CPU source binding'
    for name in ['bootloader.bin','bootloader.elf','bootrom.hex']:assert sha(root/'artifacts'/name)==sha(baseline/'artifacts'/name),name
    for n,h in snap['inputs'].items():assert sha(root/n)==h,n
    for n,h in parent['inputs'].items():assert sha(baseline/n)==h,n
    source=read(root/'rtl/cpu/source.json')
    assert source['source_reference_commit']==contract['cpu_commit'] and source['sha256']==contract['rtl_sha256']==sha(root/'rtl/cpu/CoreTop.sv')
    for n,h in contract['files_sha256'].items():assert sha(contract_path.parent/n)==h,n
    identity=read(HELPERS/'solver-identity.json');assert z3.get_version_string()==identity['version']
    for n,h in identity['files_sha256'].items():assert sha(HELPERS/n)==h,n
    dependencies=['inspect_mul_signed_mapping.py','native_sat_bits.py','native_data_boundary_graph_v2.py','native_boolean_graph_v3.py','native_hier_cone_vector_v2.py','native_hier_cone.py','solver-identity.json']
    lock={n:sha(HELPERS/n) for n in dependencies}
    for n in ['audit_cpu_ads.py','ads_bdd.py','profile_native_resources.py']:
        lock[n]=sha(HELPERS.parent/n)
    lock['check_gui1080_mul_native.py']=sha(Path(__file__))
    if physical_review:lock['gui1080_physical.py']=sha(HELPERS.parent/'gui1080_physical.py')
    vm=root/'pds/synthesize/soc_top_syn.vm';digest=sha(vm)
    proof=audit(vm.read_text())
    before=profile(baseline);after=profile(root)
    path='soc_top/u_cpu/u_cpu_wrapper/u_cpu/core/backend/u_fu_mdu/uMul'
    lookup=lambda p:{r['path']:r['inclusive'] for r in p['rows']}
    old,new=lookup(before),lookup(after)
    for label in [path,'soc_top']:
        assert new[label]['lut']<old[label]['lut'] and new[label]['ff']<=old[label]['ff']-32,(label,old[label],new[label])
        assert all(new[label][k]==old[label][k] for k in ['lutram','apm','drm36k_equivalent'])
    assert old[path]['apm']==new[path]['apm']==4 and old[path]['ff']==33 and new[path]['ff']==1
    assert proof['operand_bits_proven']==172 and proof['reconstruction_bits_proven']==32
    assert sha(vm)==digest and all(sha(root/n)==h for n,h in snap['inputs'].items())
    return dict(status='GUI1080_SIGNED_MUL_NATIVE_172_INPUT_32_WRITEBACK_BITS_RESOURCE_PASS_NOT_STA_OR_BOARD',
        run_id=snap['run_id'],snapshot_sha256=sha(root/'pds/build_snapshot.json'),native_vm_sha256=digest,
        cpu_commit=contract['cpu_commit'],rtl_sha256=contract['rtl_sha256'],cpu_contract_sha256=sha(contract_path),
        changed_inputs={n:snap['inputs'][n] for n in sorted(changed)},checkers_sha256=lock,proof=proof,
        local_before=old[path],local_after=new[path],whole_before=old['soc_top'],whole_after=new['soc_top'],
        solver_files_sha256=identity['files_sha256'],cpu_correctness=cpu_proof,
        physical_review_sha256=sha(physical_review) if physical_review else None,
        firmware_metadata_rebinding=dict(only_changed_key='build_inputs.rtl/cpu/source.json',firmware_bytes_identical=True))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['root','baseline','cpu-contract','output']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--physical-review',type=Path)
    a=ap.parse_args();assert not a.output.exists();result=dict(status='RUNNING')
    try:result=validate(a.root,a.baseline,a.cpu_contract,a.physical_review)
    except Exception:result.update(status='FAILED_NATIVE_MUL_MAPPING_PRESERVED_NOT_PNR',error=traceback.format_exc());raise
    finally:
        result['completed_utc']=datetime.now(timezone.utc).isoformat()
        a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'])
