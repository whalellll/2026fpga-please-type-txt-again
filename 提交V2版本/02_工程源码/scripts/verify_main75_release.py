"""Audit CPU75 implementation and fixed-input/real-runtime evidence before publication.

Sealing, independent extraction regression and final SD/physical application
acceptance remain separate. Research ASR accuracy and unmet goals stay explicit.
"""
from pathlib import Path
import argparse,hashlib,json,re,statistics,struct,tempfile
from audit_main75_candidate import validate as native,RUN,BIT
from verify_board_release import need,sha,read,safe,parse_uart,validate_program_transcript
from verify_main70_release import efficiency
from coremark_crc_reference import CrcReference
from build_cpu80_conv_sd import cpio_entries,fdt_properties
from board_boot_contract import validate as boot_contract

GUI='f50801c5636560a159a91b87b4664f1d9cc5b45bb42e32a71c071bfddd77d23d'
KERNEL='b6fd3e5250b6067c3e77cb1ab319be4077524958847a7317fb437135f352c0ea'
CPU='05c7ef96a8144edf7488efd1359d0855d055f501'
RTL='e8ae28118b91cd52ce4876a36f7d28efdc646979d960d48e87bc36ced35a88db'
LIMITATIONS=['187 baseline external I/O constraint gaps','PN07 worker binary reused with prior authorization',
             'NNUE10ms and image30fps goals unmet','voice_3 r05 research accuracy not promoted',
             'real microphone/endpoint timing and physical mouse/HDMI acceptance remain separate']

def ref(root,item):
    need(set(item)=={'path','sha256'},'Reference must bind path and SHA256')
    p=safe(root,item['path']);need(sha(p)==item['sha256'],'Changed evidence '+item['path']);return p

def group(root,item):
    receipt=read(ref(root,item['result']));uart=ref(root,item['uart'])
    need(receipt['status']=='BOARD_COMMAND_SPEC_PASS' and receipt['uart_sha256']==sha(uart),'Failed/changed board group')
    need(receipt['commands'] and all(x['exit']==0 for x in receipt['commands']),'Board command failed')
    return uart.read_text(errors='replace').replace('\r','')

def runtime(root,item):
    path=ref(root,item);m=read(path);kit=path.parent;sd=kit/'sd-root'
    need((m['cpu_hz'],m['sys_hz'],m['sbi_ratio'])==(75000000,49500000,[33,50]),'SD clocks differ')
    need(m['candidate_run_id']==RUN and m['candidate_bitstream_sha256']==BIT,'SD hardware differs')
    need(set(m['sd_root_files'])=={'Image','Image.mmode','fw_jump.bin','soc.dtb','mmode.dtb','rootfs.cpio','pikafish.pff','pikafish.atk'},'SD8 differs')
    for n,v in m['sd_root_files'].items():
        p=safe(sd,n);need(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'Changed SD file '+n)
    need(sha(sd/'Image')==KERNEL,'Kernel differs')
    need((sd/'soc.dtb').read_bytes()==(sd/'mmode.dtb').read_bytes(),'DTBs differ')
    dtb=(sd/'soc.dtb').read_bytes();props=fdt_properties(dtb)
    for n in ['/cpus/timebase-frequency','/cpus/cpu@0/clock-frequency']:
        at,size=props[n];need(size==4 and struct.unpack_from('>I',dtb,at)[0]==75000000,'DTB frequency differs')
    at,size=props['/chosen/linux,initrd-end'];need(size==4 and struct.unpack_from('>I',dtb,at)[0]==0x03000000+(sd/'rootfs.cpio').stat().st_size,'Rootfs bound differs')
    need((sd/'rootfs.cpio').stat().st_size<0x02000000,'Rootfs exceeds reserved RAM')
    blob=(sd/'rootfs.cpio').read_bytes();entries={}
    for row in cpio_entries(blob):
        n=row['name'].removeprefix('./');need(n not in entries,'Duplicate CPIO path');at=(row['start']+110+row['fields'][11]+3)&~3;entries[n]=blob[at:at+row['bytes']]
    for n,h in m['runtime_sha256'].items():need(hashlib.sha256(entries[n]).hexdigest()==h,'Runtime differs '+n)
    for line in entries['opt/main-xinyi/runtime.sha256'].decode().splitlines():
        h,n=line.split(None,1);need(hashlib.sha256(entries[n.strip().lstrip('/')]).hexdigest()==h,'Internal runtime integrity differs')
    need(hashlib.sha256(entries['usr/bin/xinyi-one']).hexdigest()==GUI,'Mouse GUI differs')
    need(hashlib.sha256(entries['usr/bin/xqvoice-voice3']).hexdigest()=='0f3727790fbca0cbb15aded97aa2c4cf2d93d4380a42c7581c46f35598bafeb4','ASR differs')
    need(hashlib.sha256(entries['opt/voice3/xqvoice_int8.bin']).hexdigest()=='0bd87ebd8911529dfdd01f1147887a43456118958a506ad95522e9bb194508dd','Voice model differs')
    need(hashlib.sha256(entries['usr/bin/xq-coach-worker']).hexdigest()=='1953b37d6511e21fe5eb0675dbee7285a1e06b42b3b43e60cd8edda0c6220de3','PN07 identity differs')
    need(entries['etc/main-current-cram.sha256']==(BIT+'\n').encode(),'Observed assignment stamp differs')
    program=json.loads(entries['etc/main-programming.json']);need(program['status']=='PASS' and program['operation']=='CRAM' and program['bitstream_sha256']==BIT and program['run_id']==RUN,'Observed assignment missing')
    launch=entries['usr/bin/start-main-xinyi']
    for text in [b'export PIKAFISH_EMBEDDED_MODEL=pff1-view:0x10000000:68122688',b'export PIKAFISH_STAGEB_PACK=/opt/pikafish/stageb-mac.bin',b'export XQVOICE_RUNTIME=/usr/bin/xqvoice-voice3']:
        need(text in launch,'Missing runtime launcher binding '+str(text))
    need(sha(sd/'pikafish.pff')=='de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260' and sha(sd/'pikafish.atk')=='2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c','Official model differs')
    for n,h in m['support_sources_sha256'].items():need(sha(safe(kit/'support',n))==h,'Loader support differs')
    tests=read(kit/'software-build.json');need(len(tests['tests'])==18,'Require18 loader tests')
    for n in tests['tests']:need(b'HOST_TEST_PASS' in safe(kit/'evidence',n).read_bytes(),'Loader test failed')
    return m

def validate(root,manifest,host_gcc):
    root=Path(root).resolve();m=read(manifest)
    need(m['schema']==1 and m['kind']=='main75-prepackage-release','Wrong manifest scope')
    need(m['run_id']==RUN and m['bitstream_sha256']==BIT and m['gui_sha256']==GUI,'Wrong implementation')
    need(m['coremark_policy']==dict(per_mhz_absolute_decrease_limit=.05,total_score_gate=False,all_valid_samples=True),'Wrong CoreMark policy')
    native(root,ref(root,m['native_result']),root/'artifacts/soc_top.sbit')
    need(read(root/'rtl/cpu/source.json')['source_reference_commit']==CPU and sha(root/'rtl/cpu/CoreTop.sv')==RTL,'CPU source/RTL differs')
    values={'control':[],'candidate':[]};labels=[];scratch=root/'build/main75-release-oracle';scratch.mkdir(parents=True,exist_ok=True)
    oldtmp=tempfile.tempdir;tempfile.tempdir=str(scratch)
    try:
        with CrcReference(root,host_gcc) as oracle:
            for row in m['coremark_batches']:
                role=row['role'];need(role in values,'Wrong batch role');labels.append(role+'-'+row['batch'])
                result=read(ref(root,row['result']));uart=ref(root,row['uart']);program=read(ref(root,row['program']))
                hz=75000000 if role=='candidate' else 70000000
                bit=BIT if role=='candidate' else '24226a3a2cf41e96554e4f4ea677f133964cbf942993cb1f751c60c5928a8a02'
                need(m['control_bitstream_sha256']=='24226a3a2cf41e96554e4f4ea677f133964cbf942993cb1f751c60c5928a8a02','Control hardware differs')
                need(result['status']=='PASS' and sha(uart)==result['log_sha256'] and result['bitstream']['sha256']==bit,'Failed CoreMark result')
                need(program['status']=='PASS' and program['operation']=='CRAM' and program['device_id']=='0x00602899' and program['device_count']==1 and program['bitstream_sha256']==bit,'Program identity differs')
                need(sha(ref(root,row['program_log']))==program['program_log_sha256'] and sha(ref(root,row['preflight_log']))==program['preflight_log_sha256'],'Program transcript differs')
                validate_program_transcript(ref(root,row['program_log']).read_text(errors='replace'),program['assigned_bitstream_path'])
                runs=parse_uart(uart.read_text(errors='replace'),hz,oracle)
                need(len(runs)==4 and [x['mode'] for x in runs]==['performance']*3+['validation'] and all(x['duration_seconds']>=10 and x['iterations']==6000 for x in runs),'Incomplete CoreMark batch')
                values[role].extend(x['coremark_per_mhz'] for x in runs[:3])
    finally:tempfile.tempdir=oldtmp
    need(labels==['control-a','candidate-a','control-b','candidate-b'],'ABAB order differs')
    means={k:statistics.mean(v) for k,v in values.items()};drop=efficiency(means['control'],means['candidate'])
    board=ref(root,m['board_acceptance']).parent;accepted=read(board/'board-acceptance.json')
    need(accepted['status']=='CPU75_COREMARK_FIXED_INPUT_NUMERICS_TIMING_AND_CONCURRENCY_PASS_GOALS_DISCLOSED_NOT_RELEASE' and accepted['bitstream_sha256']==BIT,'Fixed-workload acceptance differs')
    for name,key in [('summary.json','summary_sha256'),('analysis.json','analysis_sha256')]:need(sha(board/name)==accepted[key],'Board analysis changed')
    summary=read(board/'summary.json');analysis=read(board/'analysis.json')
    for n,v in summary['evidence'].items():
        rel=n.replace('\\','/');rel=rel.removeprefix('board-20261027-01/');need(sha(safe(board,rel))==v['sha256'],'Original board evidence changed '+rel)
    need(summary['worker_results_checked']==297 and summary['microphone_capture_performed'] is False and summary['accuracy_accepted'] is False,'Wrong voice scope')
    need(analysis['compare_status']=='FIXED_INPUT_THREE_IO_MODE_BOARD_COMPARE_PASS' and all(analysis['image_modes'][str(k)]['graph_us']['n']==3 for k in range(3)),'Image trials incomplete')
    need(len(analysis['exclusive']['solo']['samples'])==60 and analysis['concurrent']['nnue']['after_model_ready']['wall_us']['n']==84 and analysis['concurrent']['search']['after_model_ready']['wall_us']['n']==39,'Voice concurrency coverage differs')
    for name in ['exclusive','concurrent']:
        for case,expected in enumerate([(173,'b2e2',121,'673,327,0'),(132,'h9g7',-14,'18,935,47'),(134,'i0h0',216,'983,17,0')]):
            rows=[x for x in analysis[name+'_search'] if x['case']==case];need(len(rows)==3 and all(tuple(x[k] for k in ('nodes','bestmove','score','wdl'))==expected for x in rows),'Official search numerics differ')
    boot_contract(ref(root,m['initial_boot_uart']).read_bytes(),'MAIN75',75000000)
    gui=read(ref(root,m['gui_build']));need(gui['elf_sha256']==GUI and gui['cpu_hz']==75000000,'GUI build differs')
    for n,h in gui['source_files_sha256'].items():need(sha(safe(root,n))==h,'Compiled GUI source changed '+n)
    for key in ['gui_runtime','mainloop']:
        test=read(ref(root,m[key]));need(test['status'] in ['HOST_RV32_RUNTIME_INTEGRATION_PASS_NOT_BOARD','REAL_MAIN_LOOP_HOST_RV32_PASS_NOT_BOARD'],'Software checks failed')
        for n,h in test['source_sha256'].items():need(sha(safe(root,n))==h,'Test source changed '+n)
    smoke=group(root,m['mouse_real_board'])
    need('MOUSE_BOARD_REAL_RUNTIME_LEGAL_MOVE_ASR_DRAIN_PIKAFISH_SPEECH_RESTART_HOME_AUDIO_ACK_NO_UNDERFLOW_PASS_PHYSICAL_TRANSPORT_UNTESTED' in smoke and 'GUI_RESTORE_PASS' in smoke,'Real mouse-command transaction failed')
    need(re.search(r'^State:\s+[RS] \(',smoke,re.M) is not None,'Restored GUI is not running')
    regression=read(ref(root,m['regression']));need(regression['status']=='SOC_ALL_TESTS_PASS_NOT_BOARD' and sha(ref(root,m['regression_log']))==regression['log_sha256'],'Full regression missing')
    need(b'SOC_ALL_TESTS_PASS' in ref(root,m['regression_log']).read_bytes(),'Regression completion missing')
    for n,h in read(ref(root,m['regression_inputs'])).items():need(sha(safe(root,n))==h,'Regression input changed '+n)
    runtime(root,m['sd_kit_manifest'])
    need(m['limitations']==LIMITATIONS and m['asr_accuracy_accepted'] is False,'Scope/limitations changed')
    return dict(status='MAIN75_PREPACKAGE_IMPLEMENTATION_FIXED_INPUT_AND_REAL_MOUSE_TRANSACTION_PASS_FINAL_MEDIA_PENDING',run_id=RUN,bitstream_sha256=BIT,gui_sha256=GUI,coremark_per_mhz=means,absolute_decrease=drop,total_score_gate=False,formal_delivery_complete=False,limitations=LIMITATIONS)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe');ap.add_argument('--output',type=Path)
    a=ap.parse_args();result=validate(a.root,a.manifest,a.host_gcc)
    if a.output:need(not a.output.exists(),'Preserve receipt');a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
