"""Exact reviewed implementation delta contracts; no timing or board pass implied."""
from pathlib import Path
import hashlib,json
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
OLD={'pds/ddr3_test.rcf','pds/soc_post_synth.tcl','scripts/build_fpga.ps1','scripts/build_snapshot.ps1'}
NEW={'pds/gui1080_tage.pcf'}
P6={'rtl/soc/sd_native_mmio.v','pds/ddr3_test.rcf','pds/soc_post_synth.tcl','scripts/build_snapshot.ps1'}
P6_STATUS='REVIEWED_P6_SD_ARGUMENT_SHADOW_REUSE_TWO_MEASURED_CPU_ROUTES_EXPLICIT_NATIVE_STAGES_NOT_STA'
P8_STATUS='REVIEWED_P8_STREAMED_CONV_WEIGHT_PRELOAD_AND_MEASURED_FRONTEND_ROUTE_NOT_STA'

def is_p6(review):return review['status']==P6_STATUS
def is_p8(review):return review['status']==P8_STATUS
def has_sd_argument_reuse(review):return is_p6(review) or is_p8(review)

def delta_from_p3(review):return OLD|NEW|({'rtl/soc/sd_native_mmio.v'} if has_sd_argument_reuse(review) else set())|({'rtl/mac_accel/mac_conv_weight_dma.v','rtl/mac_accel/mac_conv_mmio_frontend.v'} if is_p8(review) else set())
def validate_review(root,review_path):
    root=Path(root);review_path=Path(review_path);r=read(review_path)
    six=is_p6(r)
    eight=is_p8(r)
    assert six or eight or r['status']=='REVIEWED_P5_ONE_TAGE_SITE_FIVE_ROUTE_NETS_NO_RTL_CLOCK_RUNTIME_CHANGE_NOT_STA'
    old={'rtl/mac_accel/mac_conv_weight_dma.v','rtl/mac_accel/mac_conv_mmio_frontend.v','pds/ddr3_test.rcf','scripts/build_snapshot.ps1'} if eight else P6 if six else OLD
    new=set() if six or eight else NEW
    parent=Path(r['parent_root']);p=read(parent/'pds/build_snapshot.json')
    assert p['run_id']==('c85a98e85a1c4b8495e3ec6a205dac6e' if eight else '3e77e387f74f4fc1a9d380b18acff740' if six else '329d099e29c5435898cd2bc28008991c') and len(p['inputs'])==(462 if six or eight else 461)
    assert sha(parent/'pds/build_snapshot.json')==r['parent_snapshot_sha256']
    assert set(r['changed_existing'])==old and set(r['added'])==new
    assert r['parent_inputs']==p['inputs']
    assert set(r['current_inputs'])==set(p['inputs'])|new and len(r['current_inputs'])==462
    assert {n for n,h in p['inputs'].items() if r['current_inputs'][n]!=h}==old
    for n,h in p['inputs'].items():assert sha(parent/n)==h,n
    for n,h in r['current_inputs'].items():assert sha(root/n)==h,n
    for n,h in (r['changed_existing']|r['added']).items():assert r['current_inputs'][n]==h,n
    assert r['cpu_contract_sha256']=='df74fc41f000e66473d6fc19a75a4ed9c185655f6618cc6ce833afc94e4a25d9'
    if eight:
        assert r['same_cpu_software_clocks_exceptions_storage_and_pipeline'] is True
        assert r['minimum_ff_saving']>=400 and r['minimum_lut_saving']>=100
        assert r['sd_argument_parent_root']=='G:/fpga/c80f1080p5'
        assert r['stream_protocol_proof']=='stream-fold/result.json'
        result=read(review_path.parent/r['stream_protocol_proof'])
        assert sha(review_path.parent/r['stream_protocol_proof'])==r['stream_protocol_proof_sha256']
        assert result['status']=='CONV_STREAM_FOLD_RAW_AND_FOLDED_FULL_PROTOCOL_CYCLE_MITERS_PASS_NOT_NATIVE_STA_OR_BOARD'
        assert len(result['cases'])==2 and len(result['negative_cases'])==3
        assert result['source_sha256']==sha(root/'rtl/mac_accel/mac_conv_weight_dma.v')
        assert result['checker_sha256']==sha(root/'scripts/test_conv_stream_fold.py')
        for name in ['rtl/soc/sd_native_mmio.v','rtl/mac_accel/mac_conv_input_dma.v']:
            assert sha(root/name)==p['inputs'][name]
    elif six:
        assert r['same_cpu_software_clocks_exceptions_storage_and_pipeline'] is True
        assert r['removed_duplicate_cmd_argument_bits']==32
        assert r['minimum_ff_saving']==30
        expected=(parent/'rtl/soc/sd_native_mmio.v').read_text()
        expected=expected.replace('    reg [31:0] cmd_arg_latched;\n','').replace("            cmd_arg_latched          <= 32'd0;\n",'')
        expected=expected.replace('                    cmd_arg_latched <= argument;',"                    // Header is stable in the existing TX register throughout CRC preparation.\n                    cmd_tx_shift[47:8] <= {2'b01, wdata[5:0], argument};")
        expected=expected.replace("                    cmd_arg_latched <= 32'd0;","                    cmd_tx_shift[47:8] <= {2'b01, 6'd12, 32'd0};")
        expected=expected.replace("                        cmd_tx_shift <= {2'b01, cmd_index_latched,\n                                         cmd_arg_latched,\n                                         command_crc_next, 1'b1};","                        cmd_tx_shift[7:0] <= {command_crc_next, 1'b1};")
        assert 'cmd_arg_latched' not in expected
        assert (root/'rtl/soc/sd_native_mmio.v').read_text()==expected,'SD change exceeds the reviewed immutable argument reuse'

    else:assert r['same_rtl_software_clocks_and_exceptions'] is True
    return r
