"""Verify the repaired ROM's frozen native image before volatile CRAM testing.

This is a separate run-specific gate. Legacy accepted-run verifiers are unchanged.
No hardware, media or remote operation is performed.
"""
from pathlib import Path
import argparse, gzip, hashlib, json, sys

CPU='fefd93052c4974c5a45fcebb7a34cc3d44f9a8d9'
RTL='95a5a197b07719948c36941b3a64308183704297d3cb4702347dc985ad2708f0'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def need(ok,why):
    if not ok:raise ValueError(why)
def validate(root,work):
    root=Path(root).resolve();work=Path(work).resolve()
    flow=read(work/'flow.json')
    need(flow['status']=='REPAIRED_SD_ROM_NATIVE_ALL_GATES_PASS_BOARD_PENDING','Native repair flow incomplete')
    snapshot=read(root/'artifacts/build_snapshot.json');evidence=read(root/'artifacts/build_evidence.json')
    need(snapshot['run_id']==evidence['run_id']==flow['run_id'],'Native run mismatch')
    need(sha(root/'artifacts/build_snapshot.json')==evidence['input_snapshot_sha256'],'Snapshot identity mismatch')
    need(snapshot['inputs']==read(work/'soc-freeze.json')['inputs'],'Implementation freeze differs')
    for n,h in snapshot['inputs'].items():need(sha(root/n)==h,'Frozen input differs: '+n)
    for n,h in evidence['outputs'].items():need(sha(root/n)==h,'Native output differs: '+n)
    need(evidence['timing']=='All Constraints Met' and evidence['max_skew_verified'] is True and evidence['timing_scope_verified'] is True,'Incomplete final STA gates')
    sys.path.insert(0,str(root/'scripts'))
    from verify_cpu80_delivery import timing
    need(timing((root/'artifacts/final_timing_xml.xml').read_bytes())==116,'Incomplete final STA coverage')
    need('Design Summary : All Constraints Met.' in (root/'artifacts/final_timing_report.txt').read_text(),'Native RTR failed')
    src=read(root/'rtl/cpu/source.json')
    need(src['source_reference_commit']==CPU and src['sha256']==RTL==sha(root/'rtl/cpu/CoreTop.sv'),'CPU pairing differs')
    need(sha(root/'artifacts/soc_top.sbit')==flow['bitstream_sha256'],'Wrong repaired bitstream')
    need(sha(root/'pds/bootrom.hex')==sha(root/'artifacts/bootrom.hex'),'ROM simulation alias differs')
    firmware=read(root/'artifacts/bootloader.build.json')
    need(firmware['binary_sha256']==sha(root/'artifacts/bootloader.bin'),'Firmware manifest mismatch')
    need(firmware['build_inputs']['sw/bootloader/sd_boot_load.h']==sha(root/'sw/bootloader/sd_boot_load.h'),'Repair header not in firmware closure')
    need(sha(root/'artifacts/bootloader.bin')!='72649f52dc1e096c29386796be00b8205ec4e45239f5bffd2f3bc9b1786024af','Old unfixed ROM selected')
    phases={x['name']:x for x in flow['phases']}
    for name,marker in [('zero-stage',b'SD_ZERO_STAGE_HOST_PASS_NOT_BOARD'),('full-soc',b'SOC_ALL_TESTS_PASS')]:
        item=phases[name];log=work/(name+'.log')
        need(item['exit_code']==0 and sha(log)==item['log_sha256'] and marker in log.read_bytes(),'Correctness evidence failed: '+name)
    proof=read(work/'native-map-audit/result.json')
    need(proof['status']=='NATIVE_FOLDED_STORE_MAC512_CHECKSUM32_READ_BOUNDARIES_CPU_DRM_PASS_NOT_STA','Folded register/cache audit failed')
    vm_file=root/'pds/synthesize/soc_top_syn.vm'
    if vm_file.is_file():vm=sha(vm_file)
    else:
        vm=hashlib.sha256(gzip.decompress((root/'artifacts/cpu80_conv_sdboot_20261022/native/soc_top_syn.vm.gz').read_bytes())).hexdigest()
    need(proof['candidate']['netlist_sha256']==vm,'Folded audit bound to another VM')
    affine=read(work/'native-map-audit/fold-ads-proof.json')
    need(affine['status']=='NATIVE_UPPER_FOLD_AFFINE_EXACT_PROOF_PASS_NOT_STA' and affine['netlist_sha256']==vm and affine['independent_input_bits']==512 and affine['output_bits']==32,'Affine proof differs')
    return dict(status='REPAIRED_ROM_NATIVE_CONTENT_STA_CORRECTNESS_PASS_NOT_BOARD',run_id=flow['run_id'],
                soc_implementation_commit=flow['soc_implementation_commit'],cpu_implementation_commit=CPU,
                bitstream_sha256=flow['bitstream_sha256'],firmware_sha256=sha(root/'artifacts/bootloader.bin'),
                frozen_inputs=len(snapshot['inputs']),sta_rows=116,skew_rows=20,board_tested=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();r=validate(a.root,a.work)
    if a.output:
        need(not a.output.exists(),'Never overwrite verification receipt')
        a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(r))
