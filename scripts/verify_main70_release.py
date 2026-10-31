"""Verify the CPU70 implementation before main publication and formal packaging.

Legacy CPU80 receipts and frozen gates keep their original contracts. This
gate applies the current0.05 CoreMark/MHz policy, without a total-score gate.
Final ZIP-bound extraction/SD boot/application acceptance is a separate gate.
"""
import argparse,hashlib,json,math,os,re,statistics,struct,tarfile,tempfile
from pathlib import Path
from audit_main70_candidate import validate as native, RUN, BIT
from verify_board_release import parse_uart,safe,need,sha,read,validate_program_transcript
from coremark_crc_reference import CrcReference
from compare_main70_models import compare,group
from build_cpu80_conv_sd import cpio_entries,fdt_properties
from board_boot_contract import validate as boot_contract

CPU='05c7ef96a8144edf7488efd1359d0855d055f501'
RTL='e8ae28118b91cd52ce4876a36f7d28efdc646979d960d48e87bc36ced35a88db'
CONTROL_BIT='30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1'
GUI='a0de66f686d26608065fe9680ea028d6003a5ce279b8945fe87dd2dc8ca17b98'

def efficiency(control,candidate):
    need(all(math.isfinite(x) and x>0 for x in (control,candidate)),'Invalid efficiency')
    need(control-candidate<=.05,'CoreMark/MHz decrease exceeds0.05')
    return control-candidate

def ref(root,record):
    need(set(record)=={'path','sha256'},'Reference requires path+sha256')
    p=safe(root,record['path']);need(sha(p)==record['sha256'],'Changed evidence '+str(p));return p

def command_group(root,record):
    result=read(ref(root,record['result']));uart=ref(root,record['uart'])
    need(result['status']=='BOARD_COMMAND_SPEC_PASS' and sha(uart)==result['uart_sha256'],'Failed/changed board group')
    need(result['commands'] and all(x['exit'] in (0,2) for x in result['commands']),'Board command failure')
    return uart.read_text(errors='replace').replace('\r',''),result

def runtime(root,record):
    path=ref(root,record);kit=path.parent;m=read(path);sd=kit/'sd-root'
    need(m['cpu_hz']==70000000 and m['sys_hz']==49500000 and m['sbi_ratio']==[99,140],'Wrong SD clocks')
    need(m['candidate_run_id']==RUN and m['candidate_bitstream_sha256']==BIT,'SD/hardware mismatch')
    need(set(m['sd_root_files'])=={'Image.mmode','mmode.dtb','fw_jump.bin','Image','rootfs.cpio','soc.dtb','pikafish.pff','pikafish.atk'},'SD8 missing')
    for name,item in m['sd_root_files'].items():
        p=safe(sd,name);need(sha(p)==item['sha256'] and p.stat().st_size==item['bytes'],'SD file changed '+name)
    need((sd/'soc.dtb').read_bytes()==(sd/'mmode.dtb').read_bytes(),'Two DTBs differ')
    dtb=(sd/'soc.dtb').read_bytes();props=fdt_properties(dtb)
    for name in ('/cpus/timebase-frequency','/cpus/cpu@0/clock-frequency'):
        offset,size=props[name];need(size==4 and struct.unpack_from('>I',dtb,offset)[0]==70000000,'DTB clock mismatch')
    offset,size=props['/chosen/linux,initrd-end']
    need(size==4 and struct.unpack_from('>I',dtb,offset)[0]==0x03000000+(sd/'rootfs.cpio').stat().st_size,'DTB rootfs bound differs')
    blob=(sd/'rootfs.cpio').read_bytes();rows=cpio_entries(blob);entries={}
    for row in rows:
        name=row['name'].removeprefix('./');need(name not in entries,'Duplicate CPIO path');entries[name]=row
    for name,h in m['runtime_sha256'].items():need(entries[name]['sha256']==h,'Runtime file differs '+name)
    need(entries['usr/bin/xinyi-one']['sha256']==GUI,'Unfixed GUI')
    launcher=entries['usr/bin/start-main-xinyi']
    at=(launcher['start']+110+launcher['fields'][11]+3)&~3
    launch=blob[at:at+launcher['bytes']]
    need(b'export PIKAFISH_EMBEDDED_MODEL=pff1-view:0x10000000:68122688\n' in launch and
         b'export PIKAFISH_STAGEB_PACK=/opt/pikafish/stageb-mac.bin\n' in launch,
         'Engine model/StageB binding omitted')
    need('opt/pikafish/stageb-mac.bin' in entries,'Engine StageB pack missing')
    need(entries['usr/bin/xq-coach-worker']['sha256']=='1953b37d6511e21fe5eb0675dbee7285a1e06b42b3b43e60cd8edda0c6220de3','PN07 reuse identity differs')
    need(sha(sd/'pikafish.pff')=='de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260' and sha(sd/'pikafish.atk')=='2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c','Official model identity differs')
    for name,h in m['support_sources_sha256'].items():need(sha(safe(kit/'support',name))==h,'Loader support source changed')
    tests=read(kit/'software-build.json')
    need(len(tests['tests'])==18,'Require18 offline loader tests')
    for name in tests['tests']:need(b'HOST_TEST_PASS' in (kit/'evidence'/name).read_bytes(),'Loader test failed '+name)
    return m

def validate(root,manifest,host_gcc):
    root=Path(root).resolve();m=read(manifest)
    need(m['schema']==1 and m['kind']=='main70-prepackage-release','Wrong release manifest')
    need(m['run_id']==RUN and m['bitstream_sha256']==BIT,'Wrong hardware')
    need(m['coremark_policy']==dict(per_mhz_absolute_decrease_limit=.05,total_score_gate=False,all_valid_samples=True),'Wrong performance policy')
    native(root,ref(root,m['native_result']),root/'artifacts/soc_top.sbit')
    cpu=read(root/'rtl/cpu/source.json')
    need(cpu['source_reference_commit']==CPU and sha(root/'rtl/cpu/CoreTop.sv')==RTL,'Unpaired CPU')
    values={'control':[],'candidate':[]};labels=[]
    scratch=root/'build/main70-release-oracle';scratch.mkdir(parents=True,exist_ok=True)
    # CrcReference is unchanged; explicitly contain its native temporary build.
    oldtmp=tempfile.tempdir;tempfile.tempdir=str(scratch)
    try:
        with CrcReference(root,host_gcc) as oracle:
            for row in m['coremark_batches']:
                role=row['role'];need(role in values,'Unknown role');labels.append(role+'-'+row['batch'])
                result=read(ref(root,row['result']));uart=ref(root,row['uart']);program=read(ref(root,row['program']))
                hz=70000000 if role=='candidate' else 80000000;bit=BIT if role=='candidate' else CONTROL_BIT
                need(result['status']=='PASS' and sha(uart)==result['log_sha256'] and result['bitstream']['sha256']==bit,'CoreMark failed/changed')
                need(program['status']=='PASS' and program['operation']=='CRAM' and program['device_id']=='0x00602899' and program['device_count']==1 and program['bitstream_sha256']==bit,'Programming identity missing')
                need(sha(ref(root,row['program_log']))==program['program_log_sha256'] and sha(ref(root,row['preflight_log']))==program['preflight_log_sha256'],'Programming log changed')
                validate_program_transcript(ref(root,row['program_log']).read_text(errors='replace'),program['assigned_bitstream_path'])
                parsed=parse_uart(uart.read_text(errors='replace'),hz,oracle)
                need(len(parsed)==4 and [x['mode'] for x in parsed]==['performance']*3+['validation'] and all(x['duration_seconds']>=10 and x['iterations']==6000 for x in parsed),'Incomplete CoreMark samples')
                values[role].extend(x['coremark_per_mhz'] for x in parsed[:3])
    finally:tempfile.tempdir=oldtmp
    need(labels==['control-a','candidate-a','control-b','candidate-b'],'ABAB groups incomplete/out of order')
    means={k:statistics.mean(v) for k,v in values.items()};decrease=efficiency(means['control'],means['candidate'])
    perfpath=ref(root,m['model_performance']);perf=read(perfpath)
    for name,h in perf['files_sha256'].items():need(sha(safe(perfpath.parent,name))==h,'Model comparison evidence changed')
    computed=compare(perfpath.parent/'control',perfpath.parent/'candidate')
    need(computed['metrics']==perf['metrics'],'Model means differ')
    sd=runtime(root,m['sd_kit_manifest'])
    initial=m['initial_sd_boot'];boot=read(ref(root,initial['result']));uart=ref(root,initial['uart'])
    need(boot['status']=='MAIN70_DIRECT_SD6_PAYLOAD_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING' and
         boot['bitstream_sha256']==BIT and sha(uart)==boot['uart_sha256'],'Initial direct SD boot failed/changed')
    boot_contract(uart.read_bytes(),'MAIN70',70000000)
    write=read(ref(root,initial['sd_write']));oldsd=read(ref(root,initial['kit_manifest']))
    need(write['status']=='MAIN70_SD8_AND_HASH_MANIFEST_WRITE_VOLUME_FLUSH_READBACK_PASS' and
         sha(ref(root,initial['sd_write']))==boot['sd_write_receipt_sha256'] and
         sha(ref(root,initial['kit_manifest']))==write['kit_manifest_sha256'],'Initial SD media binding differs')
    for item in write['files']:
        need(item['readback_sha256']==item['sha256'],'SD readback failed')
    for name in ('Image','fw_jump.bin','pikafish.pff','pikafish.atk'):
        need(sd['sd_root_files'][name]['sha256']==oldsd['sd_root_files'][name]['sha256'],'Shared boot/model input changed '+name)
    gui=read(ref(root,m['gui_build']))
    need(gui['elf_sha256']==GUI and gui['cpu_hz']==70000000 and gui['software_source_commit']==m['gui_source_commit'],'GUI build identity differs')
    for name,h in gui['source_files_sha256'].items():need(sha(safe(root,name))==h,'Compiled GUI source differs '+name)
    testpath=ref(root,m['gui_runtime_test']);test=read(testpath)
    need(test['status']=='HOST_RV32_RUNTIME_INTEGRATION_PASS_NOT_BOARD' and test['source_stable'] is True and
         test['hardware_used'] is False,'GUI runtime tests failed/misrepresented')
    need(sha(testpath.parent/'runtime.log')==test['outputs_sha256']['run.log'] and
         'RUNTIME_VOICE_RESTART_AFTER_ENGINE_FAILURE_OR_BUSY_DRAIN_RESETS32_AND_REJECTS_STALE_PASS' in test['tests'],
         'Restart/late result/drain tests missing')
    for name,h in test['source_sha256'].items():need(sha(safe(root,name))==h,'Runtime tested source differs '+name)
    regression=read(ref(root,m['regression']))
    need(regression['status']=='SOC_ALL_TESTS_PASS_NOT_BOARD' and sha(ref(root,m['regression_log']))==regression['log_sha256'],'Complete regression missing/changed')
    need(b'SOC_ALL_TESTS_PASS' in ref(root,m['regression_log']).read_bytes(),'Regression completion missing')
    reginputs=ref(root,m['regression_inputs'])
    need(sha(reginputs)==regression['input_receipt_sha256'],'Regression input inventory changed')
    for name,h in read(reginputs).items():
        if name.startswith(('rtl/','ip/','config/','sim/','sw/')):
            need(sha(safe(root,name))==h,'Hardware/firmware source differs from complete regression '+name)
    physical=read(ref(root,m['physical_feedback']))
    need(physical['status']=='USER_CONFIRMED_GUI_CAMERA_ESC_MIC_SPEAKER_PASS' and physical['bitstream_sha256']==BIT and physical['gui_elf_sha256']==GUI and physical['exact_user_reply'],'Physical acceptance missing')
    checks=m['board_groups'];need(set(checks)=={'clock','nnue','search','vision','voice','mixed','microphone','linux-coremark','gui'},'Board groups incomplete')
    for name,item in checks.items():
        text,r=command_group(root,item)
        if name!='nnue':need(all(x['exit']==0 for x in r['commands']),'Board command failed '+name)
        if name=='clock':need(4.5<=r['commands'][0]['host_response_seconds']<=7,'Linux/host timer differs')
        if name=='mixed':need('MAIN_MIXED_FOUR_MODEL_FUNCTION_PASS' in text,'Four-model concurrency failed')
        if name=='microphone':need('PCM_TRANSPORT_PASS samples=32000' in text and 'overflows=0' in text,'Microphone capture loss')
        if name=='linux-coremark':need('XY_CM_RESULT kind=riscv32-linux valid=1' in text,'Linux CoreMark invalid')
        if name=='gui':need('XINYI_GUI_FIRST_PRESENTED' in text and GUI in text,'Fixed GUI not running')
        if name=='search':need(text.count('PIKAFISH_PIPELINE_SEARCH_PASS mode=1 cases=3 nodes=128')==2,'Both resident search cases required')
    archive=ref(root,m['cpu_source_archive'])
    with tarfile.open(archive,'r:gz') as tar:
        rows=[x for x in tar.getmembers() if x.name.endswith('cpu/generated/core/CoreTop.sv')]
        need(len(rows)==1 and hashlib.sha256(tar.extractfile(rows[0]).read()).hexdigest()==RTL,'CPU source archive not paired')
    return dict(status='MAIN70_IMPLEMENTATION_PREPACKAGE_RELEASE_PASS_FINAL_ZIP_MEDIA_PENDING',run_id=RUN,bitstream_sha256=BIT,
                coremark_per_mhz=means,absolute_decrease=decrease,total_score_gate=False,formal_delivery_complete=False,
                limitations=['187 external I/O constraint gaps','PN07 binary reused; missing PN08 geometry C source','NNUE10ms and image FPS goals not achieved','voice_3 not merged'])

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe')
    ap.add_argument('--output',type=Path);a=ap.parse_args();result=validate(a.root,a.manifest,a.host_gcc)
    if a.output:
        need(not a.output.exists(),'Preserve prior receipt');a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
