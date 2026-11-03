"""Package the checked PN08 software candidate; never access the board or SD."""
from pathlib import Path
import argparse,hashlib,json,zipfile
from picture_workspace import ROOT,workspace_path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['candidate','loader-proof','installer-proof','coach-proof','geometry-proof','numeric-proof',
                 'copy-proof','kernel-proof','fullmock-proof','present-proof','matched-benchmark','output','desktop-directory']:
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--revision',choices=['r01','r02'],default='r02')
    a=ap.parse_args();assert a.output.absolute().is_relative_to(ROOT/'build')
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    candidate=workspace_path(a.candidate);manifest=json.loads((candidate/'manifest.json').read_text())
    assert manifest['prefix']=='PN08' and not manifest['hardware_used'] and not manifest['sd_written']
    for name,value in manifest['source_inputs'].items():
        data=Path(name).read_bytes();assert sha(data)==value['sha256'] and len(data)==value['bytes'],name
    receipts={}
    evidence={}
    for name in ['loader','installer','coach','geometry','numeric','copy','kernel','fullmock','present']:
        path=workspace_path(getattr(a,name+'_proof'));data=path.read_bytes();receipts[name]=json.loads(data)
        assert not receipts[name]['hardware_used'];evidence[name]={'status':receipts[name]['status'],'receipt_sha256':sha(data)}
    assert receipts['loader']['status']=='PN08_SEVEN_PAYLOAD_LOADER_HOST_SAME_GCC16_RV32_PASS_NOT_BOARD'
    assert len(receipts['loader']['tests'])==37 and all(t['pass_'] for t in receipts['loader']['tests'])
    assert receipts['installer']['status']=='PASS' and len(receipts['installer']['tests'])==51
    assert all(t['status']=='PASS' for t in receipts['installer']['tests'])
    assert receipts['coach']['status']=='PASS' and receipts['coach']['geometry_fast_candidate'] and receipts['coach']['geometry_arith_candidate']
    assert receipts['geometry']['status']=='GEOMETRY_ARITH_BIT_EQUAL_HOST_RV32_PASS_NOT_BOARD'
    assert receipts['numeric']['status']=='GEOMETRY_EXACT_DIV_ADD_MASK_HOST_RV32_ASAN_UBSAN_PASS_NOT_BOARD'
    assert receipts['copy']['status']=='WORD_SAFE_BULK_BOUNDARIES_HOST_RV32_SANITIZERS_NEGATIVE_CONTROLS_PASS_NOT_BOARD'
    assert receipts['kernel']['status']=='E42_BULK_IO32_INCREMENTAL_KERNEL_BUILD_PASS_NOT_BOARD'
    assert receipts['fullmock']['status']=='PN08_THREE_PRIVATE_FRAME_HWC_PACKETS_EQUAL_ORIGINAL_CPU_PASS_NOT_BOARD'
    assert receipts['present']['status']=='REAL_MAIN_LOOP_HOST_RV32_PASS_NOT_BOARD'
    assert all(receipts['present'][k] for k in ['display_submit_timing_verified','invalid_clock_rejected','cancel_never_reported_as_capture_completion'])
    for name,digest in receipts['present']['source_sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
    assert len(receipts['fullmock']['cases'])==3 and all(t['complete_packet_equal_original_cpu_reference'] for t in receipts['fullmock']['cases'])
    options=manifest['software_options']
    for key,value in {'detector_hwc_candidate':'1','exact_epilogue':'1','grid_recovery_candidate':'1',
            'exact_fp32_bilinear_candidate':'1','geometry_fast':'1','geometry_arith':'1','geometry_add':'0',
            'geometry_row_local':'0','hwc_rgb_quant_candidate':'0','graph_profile':'0'}.items():assert options[key]==value
    kernel=candidate/'sd-update/PN08K.BIN';assert sha(kernel.read_bytes())==manifest['kernel_sha256']==receipts['kernel']['outputs_sha256']['Image']
    worker_sha=manifest['coach_contract']['worker_sha256']
    assert worker_sha==receipts['coach']['outputs_sha256']['worker-coach-qemu/xq-coach-worker']
    benchmark=workspace_path(a.matched_benchmark);bench_proof=json.loads((benchmark/'result.json').read_text())
    bench=(benchmark/'matched-benchmark.zip').read_bytes();assert sha(bench)==bench_proof['package_sha256'] and not bench_proof['hardware_used']
    original=(candidate/'pn08-update.zip').read_bytes();assert sha(original)==receipts['loader']['package']['sha256']
    summary=dict(status='PN08_OFFLINE_SOFTWARE_COMPLETE_NOT_INSTALLED_NOT_BOARD_ACCEPTED',hardware_used=False,
        sd_written=False,flash_written=False,selector_modified=False,production_ready=False,coremark_deferred=True,
        main_commit='e7288be9e49f348b37832a65415b6989c444384c',hardware_publication='b24249d942ce19664582bf64aba60492942f08a2',
        target_bitstream_sha256=manifest['target_bitstream_sha256'],kernel_sha256=manifest['kernel_sha256'],worker_sha256=worker_sha,
        software_options=options,loader_checks=37,installer_checks=51,old_pn07_files_and_checksums_preserved_host_rv32=True,
        timing_endpoint='after_GUI_buffer_present_not_external_HDMI',photo_present_time_valid_required=True,
        three_private_hwc_packets_match_original_cpu=True,all_graph_weights_unchanged=True,all_pipeline_int8=False,
        package_script_sha256=sha(Path(__file__).read_bytes()),evidence=evidence,
        recognition_under_300s_accepted=False,recognition_accuracy_accepted=False,
        pending=['fresh_identity_and_PN08_boot','real_bulk_driver_vectors_and_cancel_drain','matched57s_detector_board_comparison',
                 'same_saved_standard32_frame_board_timing','complete_camera_framing','fresh_correct_full_board_under300s',
                 'physical_Space_Esc_display_and_audio','training_side_HWC178_dev37_report'],
        no_private_images_positions_frame_ids_or_result_hashes_in_package=True)
    readme='''# PN08：离线软件已完成，尚未安装或上板验收

按最新要求暂停板测；现在无需复制SD或重新连接板卡。
本包选用已经合入的main/e42、HWC与exact路径，并启用逐位等价的几何优化和
批量32位搬运内核。冻结r14权重、QR/RANSAC、阈值、棋规及P3/PN07回退保留。
RGB缓存、行遍历和新增加法候选不选用。INT8/S16/S32并存，几何仍使用binary64。

本轮已完成：加载器37项、安装器51项、host/RV32生产者生命周期、精确算术及
ASan/UBSan、带缺失屏障反例的字搬运检查，以及三帧完整HWC模拟与原CPU参考一致。
新内核已独立构建并检查字访问循环，未实际启动；不能据此承诺板速或准确率。
本版新增XINYI_PHOTO_PRESENT，计时在GUI缓冲区提交之后；仅time_valid=1有效。
取消不会产生完成记录，倒退/无效时钟不会成为低耗时PASS。外部HDMI仍需实板确认。

实际同帧几何测试：原版214.237秒，优化候选100.500秒，角点/统计逐位一致。
此前成功32子实景为484.258秒；最近新拍摄369.591秒，但棋盘下缘出了画面，
严格几何拒绝，不能作为识别提速验收。原版与优化版对此帧的CPU结果包一致。
当前目标是整盘正确识别五分钟以内，仍未通过。荐着另计。
上游57.18秒仅是合成detector图及三个F32头，不是拍摄到整盘显示。

未来恢复板测时，使用sd-update中的六个新文件：
PN08BOOT.BIN、PN08K.BIN、PN08.DTB、PN08UPD.GZ、PN08.JSN、PN08.SHA。
保留全部旧文件和XQBOOT.CFG，不格式化、不改选择器、不写Flash。
仍依赖原PN04SBI.BIN、PN04FS.BIN、PN04NN.PFF、PN04ATK.BIN，加载器会校验。
PN08K.BIN是新的批量字搬运内核，不能与旧PN07/PN06内核混用。
恢复后先核对e42/运行身份、七项载荷CRC、真实驱动向量、取消及五BUSY/相机排空；
再比较相同保存帧及diagnostics/matched-benchmark.zip，最后在完整取景下测新帧。
物理Space/Esc、HDMI、语音及五分钟目标仍待实板验收。训练侧HWC178+dev37报告
仍待回传，工程侧不打开封存game2/CAMERA_v2图像。
'''.encode()
    entries={}
    with zipfile.ZipFile(candidate/'pn08-update.zip') as z:
        for name in z.namelist():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts;entries[name]=z.read(name)
    entries['README.zh.md']=readme;entries['validation/summary.json']=(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode()
    entries['diagnostics/matched-benchmark.zip']=bench
    entries['SHA256SUMS']=''.join(sha(v)+'  '+k+'\n' for k,v in sorted(entries.items())).encode()
    archive=out/('xinyi-pn08-e42-'+a.revision+'-20261026.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(entries.items()):z.writestr(name,data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(entries)
        assert all(z.read(name)==data for name,data in entries.items())
    assert a.desktop_directory.is_dir();destination=a.desktop_directory/archive.name
    with destination.open('xb') as f:f.write(archive.read_bytes())
    assert sha(destination.read_bytes())==sha(archive.read_bytes())
    summary.update(package_sha256=sha(archive.read_bytes()),package_bytes=archive.stat().st_size,desktop_package=str(destination))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['status','package_bytes','package_sha256','desktop_package']},ensure_ascii=False))
if __name__=='__main__':main()
