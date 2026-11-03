"""Verify the new1080p native implementation and matching runtime before any board load."""
from pathlib import Path
import argparse,hashlib,json,subprocess,struct
from verify_cpu80_delivery import timing
from build_cpu80_conv_sd import fdt_properties
from verify_gui1080_cpu import CPU,RTL,validate_cpu
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(root,work):
    root=Path(root).resolve();work=Path(work).resolve();flow=read(work/'flow.json')
    assert flow['status']=='COMBINED_ROM_GUI1080_NATIVE_ALL_GATES_PASS_BOARD_PENDING'
    assert flow['pnr_started'] is True and Path(flow['native_root']).resolve()==root
    snap=read(root/'artifacts/build_snapshot.json');ev=read(root/'artifacts/build_evidence.json');freeze=read(work/'soc-freeze.json')
    assert snap['run_id']==ev['run_id']==flow['run_id']
    assert snap['inputs']==ev['inputs']==freeze['inputs']
    assert freeze['soc_implementation_commit']==flow['soc_implementation_commit']
    physical=flow.get('physical_review')
    assert len(snap['inputs'])==(462 if physical else 461)
    if physical:
        from gui1080_physical import validate_review,is_p6,is_p8,has_sd_argument_reuse,delta_from_p3
        review=validate_review(root,physical)
        assert flow['physical_review_sha256']==sha(Path(physical))
        assert snap['inputs']==review['current_inputs']
    assert sha(root/'rtl/cpu/CoreTop.sv')==RTL
    qualification=flow['resource_comparison']
    assert qualification['status']==(('MUL_SD_AND_STREAMED_CONV_WEIGHT_RESOURCE_FIRST_P8' if is_p8(review) else 'MUL_AND_SD_ARGUMENT_RESOURCE_FIRST_THEN_MEASURED_CPU_ROUTES_P6' if is_p6(review) else 'MUL_RESOURCE_FIRST_THEN_EXACT_PHYSICAL_ONLY_P5') if physical else 'MUL_ONLY_RESOURCE_FIRST_CPU_BOUNDARIES_AND_CAPACITY_PRESERVED')
    assert qualification['parent_run']=='68c91ab7662945f48247e660221e0c3a'
    assert qualification['current_inputs']==snap['inputs']
    expected={'rtl/cpu/CoreTop.sv','rtl/cpu/source.json','artifacts/bootloader.build.json'}
    if physical:expected |= delta_from_p3(review)
    assert set(qualification['changed_inputs'])==expected
    for name,h in qualification['changed_inputs'].items():assert snap['inputs'][name]==h,name
    assert qualification['resources']==freeze['resources']
    assert qualification['proof_sha256']==sha(work/'resource-mul.json')
    if physical and has_sd_argument_reuse(review):
        assert qualification['sd_argument_proof_sha256']==sha(work/'resource-sd-argument.json')
        faults=read(work/'resource-sd-argument-faults.json');assert qualification['sd_argument_faults_sha256']==sha(work/'resource-sd-argument-faults.json')
        assert faults['status']=='SD_NATIVE_THREE_REAL_PIN_FAULTS_REJECTED_NOT_STA_OR_BOARD' and len(faults['cases'])==3
        assert faults['checker_sha256']==sha(root/'scripts/check_sd_argument_native.py') and faults['test_sha256']==sha(root/'scripts/test_sd_argument_native.py')
        counter=read(work/'sd-argument-cycle/result.json');assert counter['status']=='SD_ARGUMENT_THREE_FULL_PROTOCOL_CYCLE_MITERS_PASS_NOT_NATIVE_OR_BOARD' and len(counter['cases'])==3 and len(counter['negative_cases'])==3
        for label in ['resource','native']:
            proof=read(work/(label+'-sd-argument.json'))
            assert proof['status']=='NATIVE_SD_ARGUMENT_SHADOW_REMOVED_STATE_MEMORY_PROTOCOL_PIN_EQ_PASS_NOT_STA_OR_BOARD'
            assert proof['checker_sha256']==sha(root/'scripts/check_sd_argument_native.py')
            item={v['name']:v for v in flow['phases']}[label+'-sd-argument'];assert item['exit_code']==0 and item['log_sha256']==sha(work/(label+'-sd-argument.log'))
        assert proof['candidate_vm_sha256']==sha(root/'pds/synthesize/soc_top_syn.vm')
    contract=root/'docs/validation/gui1080-20261023/cpu-correctness/cpu-binding.json'
    assert qualification['cpu_contract_sha256']==flow['cpu_contract_sha256']==sha(contract)
    cpu_proof=validate_cpu(contract)
    phases={item['name']:item for item in flow['phases']}
    if physical:
        item=phases['placement-route-contract']
        assert item['exit_code']==0 and sha(work/'placement-route-contract.log')==item['log_sha256']
        assert read(work/'placement-route-fixture.json')['count']==(82 if is_p8(review) else 75 if is_p6(review) else 69)
        assert ev['outputs']['artifacts/gui1080_placement.json']==sha(root/'artifacts/gui1080_placement.json')
    for name,marker in [('zero-stage',b'SD_ZERO_STAGE_HOST_PASS_NOT_BOARD'),('full-soc',b'SOC_ALL_TESTS_PASS')]:
        item=phases[name];log=work/(name+'.log')
        assert item['exit_code']==0 and sha(log)==item['log_sha256'] and marker in log.read_bytes(),name
    if 'gui1080-reused-exact-inputs' in phases:
        item=phases['gui1080-reused-exact-inputs'];previous=Path(item['result_path'])
        assert item['exit_code']==0 and sha(previous)==item['result_sha256']
    else:
        item=phases['gui1080'];previous=work/'gui1080/result.json'
        assert item['exit_code']==0 and sha(work/'gui1080.log')==item['log_sha256']
    gui=read(previous)
    assert gui['status']=='SELECTED_GUI1080_OFFLINE_CHECKS_PASS_NOT_PNR_OR_BOARD' and set(gui['checks'])=={'font','host','preview','controls','pointer','legacy','clock','pll','cpu-reset','rv32','scanout'}
    assert sha(previous.parent/'inputs.json')==gui['inputs_sha256']
    for name,h in read(previous.parent/'inputs.json').items():assert sha(root/name)==h,name
    for check in gui['results']:assert check['pass'] and sha(previous.parent/(check['check']+'.log'))==check['log_sha256']
    for name in ['resource-map-faults','native-map-faults']:
        item=phases[name];assert item['exit_code']==0 and sha(work/(name+'.log'))==item['log_sha256'],name
    assert 'config/display.json' in snap['inputs']
    assert sha(root/'artifacts/build_snapshot.json')==ev['input_snapshot_sha256']
    for name,h in snap['inputs'].items():assert sha(root/name)==h,name
    for name,h in ev['outputs'].items():assert sha(root/name)==h,name
    assert sha(root/'artifacts/soc_top.sbit')==flow['bitstream_sha256']
    assert ev['timing']=='All Constraints Met' and ev['timing_scope_verified'] and ev['max_skew_verified']
    assert timing((root/'artifacts/final_timing_xml.xml').read_bytes())==116
    assert 'Design Summary : All Constraints Met.' in (root/'artifacts/final_timing_report.txt').read_text()
    assert sha(root/'pds/bootrom.hex')==sha(root/'artifacts/bootrom.hex')
    src=read(root/'rtl/cpu/source.json');assert src['source_reference_commit']==CPU and src['sha256']==RTL==sha(root/'rtl/cpu/CoreTop.sv')
    display=read(root/'config/display.json');clocks=read(root/'config/clocks.json')
    assert (display['width'],display['height'],display['pixel_hz'],display['fb0_phys'],display['fb1_phys'])==(1920,1080,148500000,'0x1b800000','0x1bc00000')
    assert clocks['cpu_hz']==80000000 and clocks['sys_hz']==49500000
    proof=read(work/'native-map-audit/result.json')
    assert proof['status']=='NATIVE_FOLDED_STORE_MAC512_CHECKSUM32_READ_BOUNDARIES_CPU_DRM_PASS_NOT_STA'
    assert proof['candidate']['netlist_sha256']==sha(root/'pds/synthesize/soc_top_syn.vm')
    metadata=read(work/'native-metadata.json')
    assert metadata['status']=='NATIVE_WEIGHT_METADATA_110_FF_REMOVED_ALL_OTHER_STORE_FF_RETAINED_NOT_STA'
    assert metadata['candidate_vm_sha256']==proof['candidate']['netlist_sha256'] and metadata['candidate_ff']==808 and metadata['baseline_ff']==918
    affine=read(work/'native-map-audit/fold-ads-proof.json')
    assert affine['status']=='NATIVE_UPPER_FOLD_AFFINE_EXACT_PROOF_PASS_NOT_STA' and affine['netlist_sha256']==proof['candidate']['netlist_sha256']
    assert affine['independent_input_bits']==512 and affine['output_bits']==32
    for label in ['resource','native']:
        mapping=read(work/(label+'-mul.json'))
        assert mapping['status']=='GUI1080_SIGNED_MUL_NATIVE_172_INPUT_32_WRITEBACK_BITS_RESOURCE_PASS_NOT_STA_OR_BOARD'
        if physical:assert mapping['physical_review_sha256']==flow['physical_review_sha256']
        assert mapping['cpu_commit']==CPU and mapping['rtl_sha256']==RTL and mapping['cpu_correctness']==cpu_proof
        assert mapping['cpu_contract_sha256']==sha(contract)
        assert mapping['firmware_metadata_rebinding']==dict(only_changed_key='build_inputs.rtl/cpu/source.json',firmware_bytes_identical=True)
        assert mapping['local_before']['ff']==33 and mapping['local_after']['ff']==1
        assert mapping['local_after']['apm']==mapping['local_before']['apm']==4
        assert mapping['whole_after']['ff']<=mapping['whole_before']['ff']-32 and mapping['whole_after']['lut']<mapping['whole_before']['lut']
        for k in ['lutram','apm','drm36k_equivalent']:assert mapping['whole_before'][k]==mapping['whole_after'][k]
        if label=='native':assert mapping['run_id']==snap['run_id'] and mapping['native_vm_sha256']==sha(root/'pds/synthesize/soc_top_syn.vm')
        for name,h in mapping['checkers_sha256'].items():
            path=root/'scripts'/name if name in ['audit_cpu_ads.py','ads_bdd.py','profile_native_resources.py','check_gui1080_mul_native.py','gui1080_physical.py'] else root/'scripts/gui1080_mul'/name
            assert sha(path)==h,name
        for name,h in mapping['solver_files_sha256'].items():assert sha(root/'scripts/gui1080_mul'/name)==h,name
        faults=read(work/(label+'-mul-faults.json'))
        assert faults['status']=='GUI1080_MUL_POSITIVE_AND_12_NATIVE_FAULTS_REJECTED_NOT_STA_OR_BOARD'
        assert len(faults['cases'])==12 and all(c['rejected'] for c in faults['cases'])
        assert faults['native_vm_sha256']==mapping['native_vm_sha256']
        assert faults['checker_sha256']==sha(root/'scripts/gui1080_mul/inspect_mul_signed_mapping.py') and faults['test_sha256']==sha(root/'scripts/test_gui1080_mul_native.py')
        folder=work/(label+'-mul-vendor');vendor=read(folder/'result.json')
        assert vendor['status']=='NATIVE_MUL_APM_VENDOR_WAVEFORM_PASS_NOT_STA_OR_BOARD'
        assert vendor['native_vm_sha256']==mapping['native_vm_sha256'] and vendor['cycles']==9488 and vendor['captures']==7256 and vendor['held']==2232
        assert vendor['testbench_sha256']==sha(folder/'tb_native_mul_apms.sv')
        for name,h in vendor['logs_sha256'].items():assert sha(folder/(name+'.log'))==h
        for name in [label+'-mul-map',label+'-mul-faults',label+'-mul-vendor']:
            item=phases[name];assert item['exit_code']==0 and sha(work/(name+'.log'))==item['log_sha256'],name
    kit=work.parent/'sd-runtime-02';m=read(kit/'manifest.json')
    assert m['status']=='GUI1080_CPU80_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' and len(m['tests'])==18
    assert len(m['sd_root_files'])==8
    for name,item in m['sd_root_files'].items():assert sha(kit/'sd-root'/name)==item['sha256']
    assert m['support_sources_sha256']['bootloader/fat_ro.c']==sha(root/'sw/bootloader/fat_ro.c')
    runtime=read(work.parent/'runtime-02/result.json')
    assert runtime['status']=='GUI1080_RUNTIME_CPIO_DTB_18_LOADER_TESTS_PASS_NO_BOARD'
    assert runtime['sd_manifest_sha256']==sha(kit/'manifest.json')
    assert runtime['source_dts_sha256']==sha(root/'linux/soc.dts')
    assert runtime['rootfs_sha256']==m['sd_root_files']['rootfs.cpio']['sha256']
    assert runtime['kernel_sha256']==m['sd_root_files']['Image']['sha256']=='3ed55853869ff00401b112d28c61687d1b22161e0518afe6d26351d03859d770'
    assert runtime['gui_sha256']==m['gui_sha256']=='583c94b4b60e508933b18d0d267e9054a13d5ac7e84f7559e1f3b7ad5998e448'
    assert m['sd_root_files']['pikafish.pff']['sha256']=='de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260'
    assert m['sd_root_files']['pikafish.atk']['sha256']=='2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c'
    assert sha(root/'linux/boot/soc.dtb')==m['sd_root_files']['soc.dtb']['sha256']==m['sd_root_files']['mmode.dtb']['sha256']
    blob=(kit/'sd-root/soc.dtb').read_bytes();props=fdt_properties(blob)
    value=lambda key:struct.unpack_from('>I',blob,props[key][0])[0]
    assert value('/chosen/linux,initrd-end')==0x03000000+runtime['rootfs_bytes']
    assert value('/cpus/timebase-frequency')==value('/cpus/cpu@0/clock-frequency')==80000000
    assert any(key.endswith('/framebuffer@1b800000/reg') and blob[off:off+size]==struct.pack('>II',0x1b800000,0x800000) for key,(off,size) in props.items())
    # Reuse the actual native evidence gate; this performs no PDS or board operation.
    code="$ErrorActionPreference='Stop'; . ./scripts/build_snapshot.ps1; $e=Get-Content -Raw -Encoding UTF8 ./artifacts/build_evidence.json|ConvertFrom-Json; Assert-FpgaReleaseEvidence (Get-Location).Path $e; Write-Output GUI1080_NATIVE_RELEASE_EVIDENCE_PASS"
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',code],cwd=root,capture_output=True,timeout=180)
    assert p.returncode==0 and b'GUI1080_NATIVE_RELEASE_EVIDENCE_PASS' in p.stdout,(p.stdout+p.stderr)[-3000:]
    full_audit=read(work/'project-audit/result.json')
    assert full_audit['status']=='GUI1080_COMPLETE_FROZEN_PROJECT_AUDIT_PASS_NOT_DELIVERY_OR_BOARD'
    assert full_audit['run_id']==snap['run_id'] and full_audit['soc_implementation_commit']==flow['soc_implementation_commit'] and full_audit['bitstream_sha256']==flow['bitstream_sha256']
    assert full_audit['snapshot_sha256']==sha(root/'artifacts/build_snapshot.json') and full_audit['evidence_sha256']==sha(root/'artifacts/build_evidence.json')
    adapter=root/'scripts/audit_gui1080_candidate.ps1'
    assert full_audit['audit_script_sha256']==sha(adapter) and full_audit['project_hashes_sha256']==sha(root/'SHA256SUMS.txt')
    for name,h in full_audit['added_files_sha256'].items():assert sha(root/name)==h,name
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(adapter),'-Root',str(root),'-ExpectedRunId',snap['run_id'],'-CheckHashes'],cwd=root,capture_output=True,timeout=180)
    assert p.returncode==0 and b'SOC_GUI1080_CANDIDATE_PROJECT_AUDIT_PASS' in p.stdout,(p.stdout+p.stderr)[-3000:]
    return dict(status='GUI1080_NATIVE_CORRECTNESS_116_STA_20_SKEW_RUNTIME_PASS_BOARD_PENDING',run_id=flow['run_id'],soc_implementation_commit=flow['soc_implementation_commit'],cpu_implementation_commit=CPU,cpu_correctness=cpu_proof,frozen_inputs=len(snap['inputs']),bitstream_sha256=flow['bitstream_sha256'],runtime_manifest_sha256=sha(kit/'manifest.json'),project_audit_sha256=sha(work/'project-audit/result.json'),board_tested=False)
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);a=ap.parse_args();print(json.dumps(validate(a.root,a.work)))
