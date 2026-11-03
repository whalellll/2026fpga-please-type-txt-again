"""Bounded local integration flow. No board/media/Flash/remote access."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, subprocess, traceback, time

root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--work',type=Path,required=True)
ap.add_argument('--phase',choices=['correctness','native'],required=True)
ap.add_argument('--reuse-gui',type=Path)
ap.add_argument('--runtime-dir',type=Path)
ap.add_argument('--resource-root',type=Path,default=Path('G:/fpga/c80f1080r2'))
ap.add_argument('--native-root',type=Path,default=Path('G:/fpga/c80f1080p2'))
ap.add_argument('--qualified-resource',type=Path)
ap.add_argument('--route-parent-snapshot',type=Path)
ap.add_argument('--mul-cpu-contract',type=Path)
ap.add_argument('--reuse-mul-resource',type=Path)
ap.add_argument('--physical-review',type=Path)
ap.add_argument('--reuse-synthesis-only',action='store_true')
a=ap.parse_args();work=a.work.resolve()
assert work.parent==Path('G:/fpga/performance_soc_voice_hw/build/cpu80-gui1080-accept-20261023').resolve()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
py=['G:/py/ana/python.exe','-X','utf8']
ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File']
if a.phase=='correctness':
    work.mkdir(exist_ok=False)
    r=dict(status='COMBINED_CORRECTNESS_RUNNING',root=str(root),pid=os.getpid(),phases=[],
           started_utc=datetime.now(timezone.utc).isoformat(),pnr_started=False,board_accessed=False,remote_pushed=False)
else:
    r=read(work/'flow.json')
    assert r['status']=='COMBINED_CORRECTNESS_PASS_RESOURCE_PENDING'
    r['pid']=os.getpid()

def save():
    r['updated_utc']=datetime.now(timezone.utc).isoformat()
    (work/'flow.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')

def run(name,command,cwd=root,timeout=900,marker=None):
    item=dict(name=name,command=list(map(str,command)),cwd=str(cwd),started_utc=datetime.now(timezone.utc).isoformat())
    r['phases'].append(item);r['phase']=name;save()
    log=work/(name+'.log')
    with log.open('xb') as stream:
        proc=subprocess.Popen(item['command'],cwd=cwd,stdout=stream,stderr=subprocess.STDOUT)
        item['pid']=proc.pid;save()
        try:code=proc.wait(timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
            raise
    item.update(exit_code=code,completed_utc=datetime.now(timezone.utc).isoformat(),log_sha256=sha(log));save()
    assert code==0,(name,log.read_text(errors='replace')[-3500:])
    if marker:assert marker.encode() in log.read_bytes(),(name,'missing completion marker')
    print('COMBINED_PHASE_PASS '+name,flush=True)

try:
    if a.phase=='correctness':
        if a.reuse_gui:
            previous=a.reuse_gui.resolve();result=read(previous/'result.json')
            assert result['status']=='SELECTED_GUI1080_OFFLINE_CHECKS_PASS_NOT_PNR_OR_BOARD'
            assert set(result['checks'])=={'font','host','preview','controls','pointer','legacy','clock','pll','cpu-reset','rv32','scanout'}
            assert sha(previous/'inputs.json')==result['inputs_sha256']
            for name,h in read(previous/'inputs.json').items():assert sha(root/name)==h,name
            for item in result['results']:
                assert item['pass'] and sha(previous/(item['check']+'.log'))==item['log_sha256']
            r['phases'].append(dict(name='gui1080-reused-exact-inputs',result_path=str(previous/'result.json'),result_sha256=sha(previous/'result.json'),exit_code=0));save()
        else:
            run('gui1080',py+[root/'scripts/validate_gui1080.py','--output',work/'gui1080','--theme','light'],timeout=2400)
        runtime_receipt=(a.runtime_dir or work.parent/'runtime-02')/'result.json'
        deadline=time.monotonic()+1800
        while not runtime_receipt.exists():
            assert time.monotonic()<deadline,'Runtime preparation did not complete'
            time.sleep(1)
        assert read(runtime_receipt)['status']=='GUI1080_RUNTIME_CPIO_DTB_18_LOADER_TESTS_PASS_NO_BOARD'
        run('placement-contract',ps+[root/'scripts/test_gui1080_placement.ps1','-ReportPath',work/'placement-fixture.json'],marker='GUI1080_STRICT_PLACEMENT_FIXTURE_17_REJECTIONS_PASS_NOT_NATIVE_STA_OR_BOARD')
        run('sd-argument-cycle',py+[root/'scripts/test_sd_argument_reuse.py','--source',root/'rtl/soc/sd_native_mmio.v','--output',work/'sd-argument-cycle','--faults'],marker='SD_ARGUMENT_THREE_FULL_PROTOCOL_CYCLE_MITERS_PASS_NOT_NATIVE_OR_BOARD')
        run('zero-stage',py+[root/'scripts/test_sd_zero_stage.py','--gcc','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe','--output',work/'zero-stage'],marker='SD_ZERO_STAGE_HOST_PASS_NOT_BOARD')
        run('full-soc',ps+[root/'scripts/run_all_tests.ps1','-IcarusBin','G:/fpga/workspace/tools/msys64/ucrt64/bin',
            '-MsysRoot','G:/fpga/workspace/tools/msys64','-ToolchainBin','G:/fpga/workspace/tools/riscv32-gcc16/bin',
            '-PythonPath','G:/py/ana/python.exe','-HostGccPath','G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe',
            '-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-PllWslDistro','pikafish-verify',
            '-PolicyFixtureRoot',root/'prebuilt/cpu80-policy-fixture'],
            timeout=8000,marker='SOC_ALL_TESTS_PASS')
        r['status']='COMBINED_CORRECTNESS_PASS_RESOURCE_PENDING'
    else:
        # The complete SD contract is verified before freezing source inputs.
        if a.physical_review:
            assert not a.qualified_resource and not a.route_parent_snapshot
            if a.reuse_mul_resource:
                from gui1080_physical import is_p6
                assert is_p6(read(a.physical_review))
                assert read(a.reuse_mul_resource)['status']=='EXACT_RESOURCE_SYNTHESIS_REUSE_AFTER_HOST_PROOF_REVIEW_NOT_STA'
            run('placement-route-contract',ps+[root/'scripts/test_gui1080_placement.ps1','-ReportPath',work/'placement-route-fixture.json'],marker='GUI1080_STRICT_PLACEMENT_FIXTURE_17_REJECTIONS_PASS_NOT_NATIVE_STA_OR_BOARD')
            assert read(work/'placement-route-fixture.json')['count']==82
        sd=read(work.parent/'sd-runtime-02/manifest.json')
        assert sd['status']=='GUI1080_CPU80_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' and len(sd['tests'])==18
        if a.mul_cpu_contract:
            assert not a.qualified_resource and not a.route_parent_snapshot
            run('cpu-correctness',py+[root/'scripts/verify_gui1080_cpu.py','--contract',a.mul_cpu_contract],marker='GUI1080_CPU_123_TESTS_43_SUITES_PAIRED_ONLY_MUL_SAME_ROM_CYCLES_PASS_NOT_BOARD')
            r.update(cpu_contract=str(a.mul_cpu_contract.resolve()),cpu_contract_sha256=sha(a.mul_cpu_contract));save()
        resource=a.resource_root.resolve();native=a.native_root.resolve()
        assert not native.exists()
        if a.reuse_mul_resource:
            assert a.mul_cpu_contract and not a.qualified_resource and not a.route_parent_snapshot
            qualification=read(a.reuse_mul_resource)
            assert qualification['status'] in ['EXACT_RESOURCE_SYNTHESIS_REUSE_AFTER_CPU_METADATA_GUARD_CORRECTION_NOT_STA','EXACT_RESOURCE_SYNTHESIS_REUSE_AFTER_HOST_PROOF_REVIEW_NOT_STA']
            if qualification['status']=='EXACT_RESOURCE_SYNTHESIS_REUSE_AFTER_HOST_PROOF_REVIEW_NOT_STA':
                assert qualification['reason']=='Only host checker bindings/review changed; all462 synthesis inputs and raw native outputs unchanged'
                for n,h in qualification['native_files_sha256'].items():assert sha(resource/n)==h,n
            assert Path(qualification['resource_root']).resolve()==resource
            origin=Path(qualification['parent_work']);assert sha(origin/'flow.json')==qualification['parent_flow_sha256']
            assert sha(work/'reused-parent-flow.json')==qualification['parent_flow_sha256']
            snapshot=read(resource/'pds/build_snapshot.json');syn=read(resource/'pds/input-snapshots'/snapshot['run_id']/'synthesis-only.json')
            assert snapshot['run_id']==qualification['resource_run_id'] and sha(resource/'pds/build_snapshot.json')==qualification['snapshot_sha256']
            assert snapshot['inputs']==qualification['inputs'] and syn['pnr_started'] is False
            for n,h in snapshot['inputs'].items():assert sha(root/n)==sha(resource/n)==h,n
            for n,h in qualification['parent_proof_sha256'].items():assert sha(origin/n)==sha(work/n)==h,n
            for item in r['phases']:
                assert item['exit_code']==0,item['name']
                if 'log_sha256' in item:assert sha(work/(item['name']+'.log'))==item['log_sha256'],item['name']
            run('resource-mul-map',py+[root/'scripts/check_gui1080_mul_native.py','--root',resource,'--baseline','G:/fpga/c80f1080p3','--cpu-contract',a.mul_cpu_contract]+(['--physical-review',a.physical_review] if a.physical_review else [])+['--output',work/'resource-mul.json'])
            run('resource-mul-faults',py+[root/'scripts/test_gui1080_mul_native.py','--source',resource/'pds/synthesize/soc_top_syn.vm','--output',work/'resource-mul-faults.json'])
            run('resource-mul-vendor',py+[root/'scripts/gui1080_mul/run_mul_vendor_waveform.py','--root',resource,'--output',work/'resource-mul-vendor'])
            proof=read(work/'resource-mul.json');assert proof['status']=='GUI1080_SIGNED_MUL_NATIVE_172_INPUT_32_WRITEBACK_BITS_RESOURCE_PASS_NOT_STA_OR_BOARD'
            r['resource_comparison']=dict(status='MUL_ONLY_RESOURCE_FIRST_CPU_BOUNDARIES_AND_CAPACITY_PRESERVED',parent_run='68c91ab7662945f48247e660221e0c3a',current_inputs=snapshot['inputs'],changed_inputs=proof['changed_inputs'],resources=syn['resources'],cpu_contract_sha256=sha(a.mul_cpu_contract),proof_sha256=sha(work/'resource-mul.json'),resource_review_sha256=sha(work.parent/'resource-priority-03/analysis.json'))
            r['synthesis_reuse_sha256']=sha(a.reuse_mul_resource)
        elif a.qualified_resource:
            qualification=read(a.qualified_resource)
            assert qualification['status']=='RESOURCE_TRADEOFF_REVIEWED_110_FF_SAVED_2_LUT_INCREASE_NOT_STA'
            assert qualification['resource_run_id']=='6e76d64c19864674b25a1236209fd61a'
            assert Path(qualification['resource_root']).resolve()==resource
            snapshot=read(resource/'pds/build_snapshot.json')
            assert sha(resource/'pds/build_snapshot.json')==qualification['snapshot_sha256']
            assert snapshot['inputs']==qualification['source_inputs']
            for name,h in snapshot['inputs'].items():assert sha(root/name)==sha(resource/name)==h,name
            for name,h in qualification['root_source_sha256'].items():assert sha(root/name)==h,name
            origin=Path(qualification['parent_work'])
            for name,h in qualification['parent_proof_sha256'].items():
                assert sha(origin/name)==h,name
                copied=work/('reused-failed-parent-flow.json' if name=='flow.json' else name)
                assert sha(copied)==h,name
            for item in r['phases']:
                assert item['exit_code']==0,item['name']
                if 'log_sha256' in item:assert sha(work/(item['name']+'.log'))==item['log_sha256'],item['name']
            assert b'SOC_ALL_TESTS_PASS' in (work/'full-soc.log').read_bytes()
            syn=read(resource/'pds/input-snapshots'/snapshot['run_id']/'synthesis-only.json')
            assert syn['pnr_started'] is False
            assert read(work/'resource-metadata.json')['status']=='NATIVE_WEIGHT_METADATA_110_FF_REMOVED_ALL_OTHER_STORE_FF_RETAINED_NOT_STA'
            r['resource_comparison']=qualification
            r['qualified_resource_sha256']=sha(a.qualified_resource)
        else:
            assert not native.exists()
            if a.reuse_synthesis_only:
                assert resource.is_dir() and a.physical_review
            else:
                assert not resource.exists()
                run('resource-stage',ps+[root/'scripts/stage_cpu_timing_candidate.ps1','-SourceRoot',root,'-OutputRoot',resource,
                    '-Divisor','27','-CpuClockSource','dedicated1080frac','-DtcPath','G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
                run('resource-build',ps+[resource/'scripts/build_fpga.ps1','-SynthesisOnly','-UseExistingFirmware',
                    '-PythonPath','G:/py/ana/python.exe','-PdsTimeoutSeconds','14400'],cwd=resource,timeout=15000)
            snapshot=read(resource/'pds/build_snapshot.json')
            syn=read(resource/'pds/input-snapshots'/snapshot['run_id']/'synthesis-only.json')
            assert syn['pnr_started'] is False
            assert syn['status']=='SYNTHESIS_ONLY_PASS_NOT_TIMING_OR_BOARD_ACCEPTANCE'
            assert syn['input_snapshot_sha256']==sha(resource/'pds/build_snapshot.json')
            preflight_path=resource/'pds/input-snapshots'/snapshot['run_id']/'preflight_gate.json'
            assert sha(preflight_path)==syn['preflight_sha256']
            preflight=read(preflight_path)
            assert preflight['status']=='PASS' and preflight['run_id']==snapshot['run_id']
            for n,h in preflight['synth_hashes'].items():assert sha(resource/n)==h,n
            if a.reuse_synthesis_only:
                r['synthesis_only_reuse']=dict(status='EXACT_COMPLETED_SYNTHESIS_SNAPSHOT_AND_NATIVE_HASHES_REVALIDATED',run_id=snapshot['run_id'],
                    receipt_sha256=sha(resource/'pds/input-snapshots'/snapshot['run_id']/'synthesis-only.json'),preflight_sha256=sha(preflight_path),native_files_sha256=preflight['synth_hashes'])
                save()
            for n,h in snapshot['inputs'].items():assert sha(root/n)==sha(resource/n)==h,n
            (work/'resource-map-audit').mkdir()
            run('resource-map',py+[root/'scripts/check_conv_fold_native.py','--baseline','G:/fpga/c80cvr2','--candidate',resource,'--output',work/'resource-map-audit/result.json'])
            run('resource-map-faults',py+[root/'scripts/test_conv_fold_ads.py','--native',resource,'--output',work/'resource-map-faults'])
            run('resource-metadata',py+[root/'scripts/check_weight_metadata_native.py','--baseline','G:/fpga/c80f1080p1','--candidate',resource,'--output',work/'resource-metadata.json'])
            # This revision follows failed run5842's resource-first decision.
            if a.mul_cpu_contract:
                run('resource-mul-map',py+[root/'scripts/check_gui1080_mul_native.py','--root',resource,'--baseline','G:/fpga/c80f1080p3','--cpu-contract',a.mul_cpu_contract]+(['--physical-review',a.physical_review] if a.physical_review else [])+['--output',work/'resource-mul.json'])
                run('resource-mul-faults',py+[root/'scripts/test_gui1080_mul_native.py','--source',resource/'pds/synthesize/soc_top_syn.vm','--output',work/'resource-mul-faults.json'])
                run('resource-mul-vendor',py+[root/'scripts/gui1080_mul/run_mul_vendor_waveform.py','--root',resource,'--output',work/'resource-mul-vendor'])
                proof=read(work/'resource-mul.json')
                assert proof['status']=='GUI1080_SIGNED_MUL_NATIVE_172_INPUT_32_WRITEBACK_BITS_RESOURCE_PASS_NOT_STA_OR_BOARD'
                r['resource_comparison']=dict(status='MUL_ONLY_RESOURCE_FIRST_CPU_BOUNDARIES_AND_CAPACITY_PRESERVED',parent_run='68c91ab7662945f48247e660221e0c3a',current_inputs=snapshot['inputs'],changed_inputs=proof['changed_inputs'],resources=syn['resources'],cpu_contract_sha256=sha(a.mul_cpu_contract),proof_sha256=sha(work/'resource-mul.json'),resource_review_sha256=sha(work.parent/'resource-priority-03/analysis.json'))
            elif a.route_parent_snapshot:
                parent=read(a.route_parent_snapshot)
                assert parent['run_id']=='034de111f1ca40f7868683d2895d8b8c'
                assert set(parent['inputs'])==set(snapshot['inputs'])
                delta={k for k in snapshot['inputs'] if snapshot['inputs'][k]!=parent['inputs'][k]}
                assert delta=={'pds/ddr3_test.rcf','scripts/build_snapshot.ps1'},delta
                reviewed=read(work.parent/'route-priority-02/changed-inputs.json')
                for name,h in reviewed.items():assert snapshot['inputs'][name]==h
                previous=read(work.parent/'attempt-05/soc-freeze.json')['resources']
                assert syn['resources']==previous,'Route-only trial changed synthesized resources'
                r['resource_comparison']=dict(status='ROUTE_ONLY_AFTER_REVIEWED_RESOURCE_EXCHANGE_NO_NEW_RTL',parent_run=parent['run_id'],parent_inputs=parent['inputs'],current_inputs=snapshot['inputs'],changed_inputs=reviewed,resources=previous,resource_review_sha256=sha(work.parent/'route-priority-02/analysis.json'))
            else:
                previous=read(work.parent/'attempt-03/soc-freeze.json')['resources']
                assert syn['resources']['LUT']['used']<=previous['LUT']['used'],'No actual LUT saving'
                assert syn['resources']['FF']['used']<=previous['FF']['used']-100,'Duplicate metadata was not removed in mapping'
                for name in ['LUTRAM','DRM']:assert syn['resources'][name]['used']==previous[name]['used'],('Storage capacity/mapping changed',name)
                r['resource_comparison']=dict(previous_run='5842bd9df4f546fcbac537815fb79447',previous=previous,current=syn['resources'],gate='LUT nonincrease; >=100 FF removed; LUTRAM/DRM and audited read FF unchanged')
        if a.physical_review:
            from gui1080_physical import validate_review,is_p6,is_p8,has_sd_argument_reuse
            review=validate_review(root,a.physical_review)
            assert snapshot['inputs']==review['current_inputs']
            if has_sd_argument_reuse(review):
                sd_parent=review.get('sd_argument_parent_root',review['parent_root'])
                run('resource-sd-argument',py+[root/'scripts/check_sd_argument_native.py','--baseline',sd_parent,'--candidate',resource,'--output',work/'resource-sd-argument.json'])
                run('resource-sd-argument-faults',py+[root/'scripts/test_sd_argument_native.py','--baseline',sd_parent,'--output',work/'resource-sd-argument-faults.json'])
                previous=review['parent_resources']
                assert syn['resources']['LUT']['used']<=previous['LUT']['used']-review.get('minimum_lut_saving',0)
                assert syn['resources']['FF']['used']<=previous['FF']['used']-review['minimum_ff_saving']
                for key in ['LUTRAM','DRM']:assert syn['resources'][key]==previous[key],key
            else:assert syn['resources']==review['parent_resources'],'Physical-only change altered synthesized resource use'
            r['physical_review']=str(a.physical_review.resolve());r['physical_review_sha256']=sha(a.physical_review)
            r['resource_comparison']['status']='MUL_SD_AND_STREAMED_CONV_WEIGHT_RESOURCE_FIRST_P8' if is_p8(review) else 'MUL_AND_SD_ARGUMENT_RESOURCE_FIRST_THEN_MEASURED_CPU_ROUTES_P6' if is_p6(review) else 'MUL_RESOURCE_FIRST_THEN_EXACT_PHYSICAL_ONLY_P5'
            if has_sd_argument_reuse(review):
                r['resource_comparison']['sd_argument_proof_sha256']=sha(work/'resource-sd-argument.json')
                r['resource_comparison']['sd_argument_faults_sha256']=sha(work/'resource-sd-argument-faults.json')
            r['resource_comparison']['physical_review_sha256']=sha(a.physical_review)
            if is_p8(review):
                run('resource-stream-cycle',py+[root/'scripts/test_conv_stream_fold.py','--source',resource/'rtl/mac_accel/mac_conv_weight_dma.v','--output',work/'resource-stream-cycle','--faults'])
        r.update(status='COMBINED_SYNTHESIS_PASS_FREEZING',resource_run=snapshot['run_id'],resources=syn['resources']);save()
        # Local implementation freeze only, after correctness and mapped gates.
        run('freeze-add',['git','add','--sparse','-u'])
        run('freeze-add-tools',['git','add','--sparse','scripts/run_cpu80_gui1080_flow.py','scripts/build_gui1080_runtime.py',
            'scripts/linux/assemble_audio_service_sd.py','scripts/test_conv_fold_ads.py','scripts/test_weight_metadata_equivalence.py','scripts/check_weight_metadata_native.py',
            'sim/tb_weight_metadata_equivalence.sv','sim/reference/mac_weight_double_buffer_metadata.v',
            'scripts/audit_gui1080_candidate.ps1','scripts/verify_gui1080_native.py','scripts/board_console.py',
            'scripts/program_gui1080_candidate.py','scripts/tftp_gui1080_candidate.py','scripts/netboot_gui1080_candidate.py',
            'scripts/measure_gui1080_coremark_ab.py','scripts/collect_gui1080_board.py','docs/GUI1080_Acceptance_20261023.md'])
        if a.physical_review:
            run('freeze-add-physical',['git','add','--sparse','--force','pds/gui1080_tage.pcf','scripts/gui1080_physical.py','scripts/test_gui1080_placement.ps1',str(a.physical_review)])
            if is_p8(review):
                run('freeze-add-stream',['git','add','--sparse','--force','scripts/test_conv_stream_fold.py','scripts/prove_conv_stream_native.py','scripts/test_conv_stream_native.py',
                    'scripts/prove_conv_fold_ads.py','sim/reference/mac_conv_weight_dma_p6.v.gz','sim/reference/mac_conv_weight_dma_p6.v.json',
                    'docs/validation/gui1080-20261023/stream-fold/result.json','docs/MAC_Cache_Capacity_20261023.md','docs/validation/gui1080-20261023/cache-capacity-review.json'])
        run('freeze-add-sd-tools',['git','add','--sparse','--force','scripts/test_sd_argument_reuse.py','scripts/check_sd_argument_native.py','scripts/test_sd_argument_native.py','sim/reference/sd_native_mmio_p5.v.gz','sim/reference/sd_native_mmio_p5.json','scripts/program_with_project_audit.py'])
        if a.mul_cpu_contract:
            run('freeze-add-mul-tools',['git','add','--sparse','scripts/verify_gui1080_cpu.py','scripts/check_gui1080_mul_native.py','scripts/test_gui1080_mul_native.py','scripts/prepare_gui1080_project_audit.py','scripts/gui1080_mul'])
            contract=read(a.mul_cpu_contract);relative=a.mul_cpu_contract.resolve().parent.relative_to(root).as_posix()
            identity=read(root/'scripts/gui1080_mul/solver-identity.json')
            forced=[relative+'/'+a.mul_cpu_contract.name]+[relative+'/'+n for n in contract['files_sha256']]+['scripts/gui1080_mul/'+n for n in identity['files_sha256']]
            run('freeze-add-mul-proof',['git','add','--sparse','--force']+forced)
        run('freeze-commit',['git','commit','-m','Freeze CPU80 repaired SD boot and light1080p GUI after integrated correctness and resource gates'])
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
        for n,h in snapshot['inputs'].items():assert sha(root/n)==h,n
        r['soc_implementation_commit']=commit
        (work/'soc-freeze.json').write_text(json.dumps(dict(soc_implementation_commit=commit,inputs=snapshot['inputs'],resources=syn['resources'],board_tested=False),indent=2)+'\n')
        run('native-stage',ps+[root/'scripts/stage_cpu_timing_candidate.ps1','-SourceRoot',root,'-OutputRoot',native,
            '-Divisor','27','-CpuClockSource','dedicated1080frac','-DtcPath','G:/fpga/performance_soc_voice_hw/build/dtc_proxy.cmd'])
        for n,h in snapshot['inputs'].items():assert sha(native/n)==h,n
        r.update(status='COMBINED_NATIVE_BUILD_RUNNING',native_root=str(native),pnr_started=True);save()
        run('native-build',ps+[native/'scripts/build_fpga.ps1','-UseExistingFirmware','-PythonPath','G:/py/ana/python.exe',
            '-PdsTimeoutSeconds','14400','-CampaignLog',work/'pnr-history.json','-AttemptPurpose','final'],cwd=native,timeout=15000)
        actual=read(native/'pds/build_snapshot.json');evidence=read(native/'artifacts/build_evidence.json')
        assert actual['inputs']==snapshot['inputs']
        assert evidence['timing']=='All Constraints Met' and evidence['max_skew_verified'] and evidence['timing_scope_verified']
        (work/'native-map-audit').mkdir()
        run('native-map',py+[root/'scripts/check_conv_fold_native.py','--baseline','G:/fpga/c80cvr2','--candidate',native,'--output',work/'native-map-audit/result.json'])
        run('native-map-faults',py+[root/'scripts/test_conv_fold_ads.py','--native',native,'--output',work/'native-map-faults'])
        run('native-metadata',py+[root/'scripts/check_weight_metadata_native.py','--baseline','G:/fpga/c80f1080p1','--candidate',native,'--output',work/'native-metadata.json'])
        if a.mul_cpu_contract:
            run('native-mul-map',py+[root/'scripts/check_gui1080_mul_native.py','--root',native,'--baseline','G:/fpga/c80f1080p3','--cpu-contract',a.mul_cpu_contract]+(['--physical-review',a.physical_review] if a.physical_review else [])+['--output',work/'native-mul.json'])
            run('native-mul-faults',py+[root/'scripts/test_gui1080_mul_native.py','--source',native/'pds/synthesize/soc_top_syn.vm','--output',work/'native-mul-faults.json'])
            run('native-mul-vendor',py+[root/'scripts/gui1080_mul/run_mul_vendor_waveform.py','--root',native,'--output',work/'native-mul-vendor'])
        if a.physical_review and has_sd_argument_reuse(review):
            run('native-sd-argument',py+[root/'scripts/check_sd_argument_native.py','--baseline',review.get('sd_argument_parent_root',review['parent_root']),'--candidate',native,'--output',work/'native-sd-argument.json'])
        if a.physical_review and is_p8(review):
            run('native-stream-cycle',py+[root/'scripts/test_conv_stream_fold.py','--source',native/'rtl/mac_accel/mac_conv_weight_dma.v','--output',work/'native-stream-cycle','--faults'])
        r.update(status='COMBINED_ROM_GUI1080_NATIVE_ALL_GATES_PASS_BOARD_PENDING',run_id=actual['run_id'],bitstream_sha256=sha(native/'artifacts/soc_top.sbit'))
except Exception:
    r.update(status='FAILED_PRESERVED_NO_PROMOTION',error=traceback.format_exc())
    raise
finally:
    save();print(r['status'],flush=True)
