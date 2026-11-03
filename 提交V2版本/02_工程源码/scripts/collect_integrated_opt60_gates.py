"""Freeze current correctness/software/resource gate hashes for a new PnR."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--replacements',type=Path,help='Map existing required receipt names to current paired receipts; statuses and count stay fixed')
    ap.add_argument('--resource-optimization',action='store_true')
    a=ap.parse_args();assert not a.output.exists()
    expected={
      'opt60-batch-driver-01/result.json':'ACTUAL_BATCH_DRIVER_TRANSACTION_STUB_PASS_NOT_KERNEL_OR_BOARD',
      'opt60-batch-runtime-01/result.json':'PIKAFISH_BATCH_REAL_RUNTIME_ORACLE_PASS_NOT_BOARD',
      'opt60-batch-rtl-02/result.json':'PIKAFISH_BATCH_SHARED_AXI_DEPENDENCY_EXPORT_SCORE_RECOVERY_PASS_NOT_BOARD',
      'opt60-vision-batch-01/result.json':'VISION32_AND_PIKAFISH_SIMULTANEOUS_AXI_PASS_NOT_BOARD',
      'opt60-pikafish-official0-01/result.json':'PIKAFISH_DEDICATED_C_REFERENCE_CACHE_AND_RECOVERY_PASS_NOT_BOARD',
      'opt60-pikafish-pads-official1-01/result.json':'PIKAFISH_DEDICATED_C_REFERENCE_CACHE_AND_RECOVERY_PASS_NOT_BOARD',
      'opt60-voice-model-ram-01/result.json':'VOICE2_BALANCED24_FULL_MODEL_BACKEND_AND_RTL_PASS_NOT_BOARD',
      'opt60-voice-quant-ram-01/result.json':'VOICE_CNN_QUANT_INDEPENDENT_INTEGER_ORACLE_PASS_NOT_BOARD',
      'opt60-voice-raw-ram-01/result.json':'VOICE_CNN_TILE_DIFFERENTIAL_PASS_NOT_BOARD',
      'opt60-voice-driver-01/result.json':'ACTUAL_VOICE_QUANT_DRIVER_TRANSACTION_STUB_PASS_NOT_KERNEL_OR_BOARD',
      'opt60-voice-stream-01/result.json':'VOICE2_STREAM_BATCH_ALL5_LAYERS_INTEGER_PARITY_STRICT_BACKEND_PASS_NOT_BOARD',
      'opt60-picture-original-02/result.json':'ORIGINAL_THREE_GRAPHS_SPATIAL_ORACLE_AND_JOB_REDUCTION_PASS_NOT_BOARD',
      'opt60-picture-interface-final-02/result.json':'PICTURE_NEW_VISION32_HOST_RV32_INTERFACE_PASS_WEIGHTS_DEFERRED_NOT_BOARD',
      'opt60-vision-driver-01/result.json':'ACTUAL_VISION32_DRIVER_OWNERSHIP_CONFIG_FAILURE_AND_DRAIN_PASS_NOT_KERNEL_OR_BOARD',
      'opt60-vision-real-ddr-01/result.json':'VISION32_PRODUCTION_DDR_CDC_INTEGER_ORACLE_PASS_NOT_BOARD',
      'opt60-clock-01/result.json':'CPU60_PLL_VENDOR_WAVEFORM_PASS_NOT_STA_OR_BOARD',
      'opt60-native-cpu-02.json':'PASS',
      'opt60-native-pma-faults-02/result.json':'INTEGRATED_OPT60_NATIVE_PMA_1024_CASES_AND_FIVE_FAULTS_PASS_NOT_STA',
      'opt60-native-cache-02.json':'VISION32_NATIVE_CACHE_PORTS_CAPACITY_DECODERS_AND_MUTATIONS_PASS_NOT_STA',
      'opt60-native-resources-01.json':'INTEGRATED_OPT60_NATIVE_RESOURCE_AND_RETAINED_ENGINES_PASS_NOT_STA_OR_BOARD',
      'opt60-audit-selection-02.json':'COMBINED_CPU_AUDIT_EXACT_SELECTORS_AND_PROOF_GUARDS_PASS_NOT_PDS',
      'opt60-kernel-01/build.json':'VOICE_NNUE_FROZEN_KERNEL_BUILD_PASS_NOT_BOARD',
      'opt60-pikafish-rv32-01/result.json':'PIKAFISH75_PIPELINE_SEARCH_AND_GUI_RV32_BUILD_PASS_NOT_BOARD',
      'opt60-voice-production-01/result.json':'VOICE2_SMALL_STRICT_RV32_LINUX_BUILD_PASS_NOT_BOARD',
      'opt60-voice-profile-bin-01/result.json':'VOICE2_SMALL_STRICT_RV32_LINUX_BUILD_PASS_NOT_BOARD',
      'opt60-picture-bench-01/result.json':'ORIGINAL_THREE_GRAPHS_HOST_CPU_AND_RV32_LOAD_PASS_NOT_BOARD',
      'opt60-sd-kit-01/manifest.json':'INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING',
      'batch60-full-regression-integrated-opt60-02.json':'SOC_ALL_TESTS_PASS_NOT_BOARD'}
    replacements=json.loads(a.replacements.read_text()) if a.replacements else {}
    assert set(replacements)<=set(expected),'Cannot remove or invent required gates'
    for name in replacements.values():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert (ROOT/'build'/name).resolve().is_relative_to(ROOT/'build')
    expected={replacements.get(name,name):status for name,status in expected.items()}
    assert len(expected)==28,'Required gates must remain distinct'
    if a.resource_optimization:
        expected['opt60-video-line-pack-03/result.json']='PACKED_VIDEO_LINE_RAM_CYCLE_EQUIVALENCE_PASS_NOT_NATIVE_OR_BOARD'
        expected['opt60-r2-load-packing-01.json']='NATIVE_LSU_LOAD_PIN_PACKING_AND_12_FAULTS_PASS_NOT_STA'
        expected['opt60-r2-clock-resource-faults-01.json']='PACKED_VIDEO_CLOCK_RESOURCE_NATIVE_AND_SEVEN_FAULTS_PASS_NOT_STA'
    checks={};files={}
    for rel,status in expected.items():
        p=ROOT/'build'/rel;record=json.loads(p.read_text(encoding='utf-8-sig'));assert record['status']==status,(rel,record.get('status'))
        for key in ['source_sha256','sources_sha256','inputs_sha256']:
            for name,h in record.get(key,{}).items():
                source=Path(name);source=source if source.is_absolute() else ROOT/source
                if rel=='opt60-audit-selection-02.json':source=ROOT/'scripts'/name
                assert sha(source)==h,('Gate source changed',rel,name)
                # Vendor inputs outside the worktree are also frozen by absolute path.
                files[source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else source.as_posix()]=h
        files[p.relative_to(ROOT).as_posix()]=sha(p);checks[rel]=status
    for name in ['scripts/build_integrated_opt60_pnr.ps1','scripts/collect_integrated_opt60_resources.py',
                 'scripts/collect_integrated_opt60_gates.py','scripts/audit_cpu85_half_ads.py',
                 'scripts/audit_pikafish_linear_hold_ads.py','scripts/vision32_cache_contract.py']:
        files[name]=sha(ROOT/name)
    if a.resource_optimization:
        for name in ['scripts/audit_cpu_ads.py','scripts/test_integrated60_load_packing.py',
                     'scripts/test_video_fb_line_ram.py','scripts/vision32_resource_contract.py',
                     'scripts/audit_cpu_dedicated_pll_ads.py','scripts/test_integrated60_clock_resources.py']:
            files[name]=sha(ROOT/name)
    result=dict(status='INTEGRATED_OPT60_CORRECTNESS_SOFTWARE_RESOURCE_GATES_PASS_NOT_STA_OR_BOARD',
                created_utc=datetime.now(timezone.utc).isoformat(),files=files,checks=checks,
                replacements=replacements,resource_optimization=a.resource_optimization)
    if a.replacements:result['replacement_manifest_sha256']=sha(a.replacements)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
