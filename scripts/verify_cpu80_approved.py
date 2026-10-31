"""Verify this approved80MHz release without changing legacy run-specific gates."""
from pathlib import Path
import argparse,hashlib,json,math,statistics,re,sys,tarfile
from verify_sdboot_native import validate as native,need,sha,read,CPU,RTL
from verify_cpu80_conv_candidate import validate as content
from verify_cpu80_delivery import safe,ARCHIVE
from coremark_crc_reference import CrcReference
from verify_board_release import parse_uart

RUN='44aa982f752c4b7d91accea60292735f'
BIT='30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1'
IMAGE='3ed55853869ff00401b112d28c61687d1b22161e0518afe6d26351d03859d770'
LOADER='f08e039eab5f4970b5ee8e4f92f0aa6bc2ec41b489935efbbdc8572184ebca79'
BASE=Path('docs/validation/cpu80-audio-service-20261022')

def release_file(root,path):
    n=path.relative_to(root).as_posix()
    return (path.is_file() and '__pycache__' not in path.parts and
            not n.startswith(('build/','log/','artifacts/selftest/','artifacts/bootloader_obj/','review-extras/','.git/')) and
            path.suffix not in ['.pyc','.o','.obj','.vvp','.img'] and
            not (n.startswith('artifacts/') and (path.suffix=='.map' or path.name.endswith(('.disasm.txt','.size.txt')))) and
            path.name!='CPU80_APPROVED_DELIVERY.json')

def approved_contract(approval,candidate,control):
    need(all(math.isfinite(x) and x>0 for x in [candidate,control]),'Invalid CoreMark/MHz values')
    need(approval['exact_user_text']=='总分没关系，只要保持coremark/mhz在门限内，这个版本批准提交','Missing explicit version approval')
    need(approval['run_id']==RUN and approval['bitstream_sha256']==BIT,'Approval bound to another image')
    need(approval['kernel_sha256']==IMAGE and approval['loader_sha256']==LOADER,'Approval bound to another software runtime')
    need(approval['coremark_total_required'] is False,'Wrong approved CoreMark contract')
    need(control-candidate<=.05,'CoreMark/MHz exceeds0.05 absolute decrease')
    stored=approval['coremark_per_mhz']
    need(stored['limit']==.05 and stored['passed'] is True and math.isclose(stored['absolute_decrease'],control-candidate,abs_tol=1e-12) and math.isclose(stored['candidate'],candidate,rel_tol=1e-12) and
         math.isclose(stored['control'],control,rel_tol=1e-12),'Approved CoreMark arithmetic differs')

def validate(root,host_gcc,inventory=True):
    root=Path(root).resolve()
    if inventory:
        package=read(root/'CPU80_APPROVED_DELIVERY.json')
        need(package['run_id']==RUN and package['bitstream_sha256']==BIT,'Wrong approved package identity')
        recorded=package['files_sha256']
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if release_file(root,p)}
        need(actual==set(recorded),'Approved package file set differs')
        for n,h in recorded.items():need(sha(safe(root,n))==h,'Package file changed: '+n)
    work=root/'docs/validation/cpu80-conv-sdboot-20261022/attempt-03'
    n=native(root,work);need(n['run_id']==RUN and n['bitstream_sha256']==BIT and n['frozen_inputs']==459,'Wrong native implementation')
    content(root)
    board=root/BASE/'board-repair'
    approval=read(board/'release-approval-20261022.json')
    binding=read(board/'audiofix-board-binding.json')
    need(sha(board/'audiofix-board-binding.json')==approval['board_binding_sha256'],'Approved board binding changed')
    need(binding['hardware_run']==RUN and binding['bitstream_sha256']==BIT and binding['kernel_sha256']==IMAGE and binding['loader_sha256']==LOADER,'Runtime/board identity differs')
    need(read(board/'physical-hdmi-01.json')['status']=='USER_CONFIRMED_HDMI_AND_MOUSE_PASS','Physical720p HDMI/mouse confirmation missing')
    for stem in ['audiofix-sdboot-01','audiofix-functional-01','audiofix-nnue-a','audiofix-nnue-b','audiofix-gui-audio-01']:
        r=read(board/(stem+'.result.json'))
        expected='PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING' if 'sdboot' in stem else 'BOARD_COMMAND_SPEC_PASS'
        need(r['status']==expected and sha(board/(stem+'.uart'))==r['uart_sha256'],'Board evidence changed/failed: '+stem)
    text=(board/'audiofix-sdboot-01.uart').read_text(errors='replace')
    need('CPU80_SD_PAYLOADS_CRC_PASS cpu=80000000 sys=49500000 ratio=99/160' in text and
         'Thu Oct 22 14:00:00 UTC 2026' in text and '/ # ' in text,'Wrong direct SD boot/runtime')
    mixed=read(board/'audiofix-mixed-binding.json')
    need(mixed['status']=='TWO_NORMAL_PRIORITY_MIXED_OBSERVATIONS_ZERO_OVERFLOW_PASS' and len(mixed['observations'])==2,'Two valid normal mixed observations required')
    for name,h in mixed['input_sha256'].items():need(sha(safe(board,name))==h,'Mixed evidence changed')
    for row in mixed['observations']:need(row['samples']==96000 and row['overflows']==0,'Mixed audio loss')
    gui=(board/'audiofix-gui-audio-01.uart').read_text(errors='replace')
    need('INJECT MOVE_PASS red=h2e2 black=b9c7' in gui and 'XQVOICE_READY backend=cpu' in gui and
         'CPU80_MODELS_RESTORED' in gui,'GUI/search/voice not restored')
    pcm=re.findall(r'PCM_TRANSPORT_PASS samples=(\d+) elapsed_ms=\d+ fifo_samples=512 mic_count=\d+ overflows=(\d+)',gui)
    need(pcm==[('32000','0'),('96000','0')],'GUI audio failed')
    cms={}
    with CrcReference(root,host_gcc) as oracle:
        for image in ['candidate','control']:
            values=[]
            for batch in ['a','b']:
                path=board/('coremark-'+image+'-'+batch)
                cm=read(path/'result.json')
                need(cm['status']=='PASS' and sha(path/'uart.log')==cm['log_sha256'],'CoreMark evidence failed/changed')
                parsed=parse_uart((path/'uart.log').read_text(errors='replace'),80000000,oracle)
                need(len(parsed)==4 and all(x['duration_seconds']>=10 for x in parsed),'Incomplete CoreMark samples')
                need(cm['bitstream']['sha256']==(BIT if image=='candidate' else '732ec3784b55ee932a80d2c2db76c9202d17a505eae80c2c482e871faf558265'),'CoreMark image differs')
                values.extend(x['coremark_per_mhz'] for x in parsed[:3])
            need(len(values)==6,'All six CoreMark samples required');cms[image]=statistics.mean(values)
    approved_contract(approval,cms['candidate'],cms['control'])
    kit=root/'artifacts/cpu80_audio_service_20261022/sd-kit';sd=read(kit/'manifest.json')
    need(sd['sd_root_files']['Image']['sha256']==IMAGE and sd['sd_root_files']['Image.mmode']['sha256']==LOADER,'Wrong software SD files')
    for name,item in sd['sd_root_files'].items():need(sha(root/'linux/boot'/name)==sha(kit/'sd-root'/name)==item['sha256'],'Root and SD runtime differ: '+name)
    for name,h in sd['support_sources_sha256'].items():need(sha(safe(kit/'support',name))==h,'SD loader source changed')
    kernel=read(root/BASE/'kernel-01/build.json')
    need(kernel['outputs_sha256']['Image']==IMAGE and sha(root/BASE/'kernel-01/build.json')==sd['kernel_build_receipt_sha256'],'Kernel build binding differs')
    for relative in ['linux/mac_accel/kernel/pango_mac.c','linux/mac_accel/kernel/pango_mac_copy_chunks.h','linux/mac_accel/pango_mac_uapi.h',
                     'linux/audio/kernel/pango_audio.c','linux/audio/pango_audio_uapi.h','scripts/linux/rebuild_audio_service_kernel.py']:
        rows=[h for name,h in kernel['inputs_sha256'].items() if name.replace('\\','/').endswith('/'+relative)]
        need(rows==[sha(root/relative)],'Kernel source not paired: '+relative)
    need(len({sha(root/BASE/'kernel-01'/name) for name in ['base.config','kernel.config','embedded.config']})==1,'Kernel configuration changed')
    for phase in ['cold','warm']:
        for batch in ['a','b']:
            text=(board/('audiofix-nnue-'+batch+'.uart')).read_text(errors='replace')
            need('NNUE_LATENCY_CORRECTNESS_PASS' in text and 'fallbacks=0 mismatches=0' in text,'Official NNUE correctness/fallback failure')
        need(binding['latency']['nnue_'+phase]['samples']==80 and binding['performance_gates']['nnue_'+phase] is True,'Official NNUE latency regression')
    archive=root/'artifacts/cpu80_candidate_20261020/cpu-source-fefd9305.tar.gz'
    need(sha(archive)==ARCHIVE,'Paired CPU archive changed')
    with tarfile.open(archive,'r:gz') as tar:
        items=[x for x in tar.getmembers() if x.name.endswith('cpu/generated/core/CoreTop.sv')]
        need(len(items)==1 and hashlib.sha256(tar.extractfile(items[0]).read()).hexdigest()==RTL,'CPU source/RTL pair differs')
    return dict(status='APPROVED_CPU80_NATIVE_RUNTIME_BOARD_CONTENT_PASS_FINAL_MEDIA_SEPARATE',run_id=RUN,
        cpu_implementation_commit=CPU,bitstream_sha256=BIT,kernel_sha256=IMAGE,sd_files=8,frozen_inputs=459,
        coremark_per_mhz=cms,coremark_per_mhz_decrease=cms['control']-cms['candidate'],
        total_score_gate='USER_WAIVED',legacy_dense='DISCLOSED_0.451_PERCENT_REGRESSION_VERSION_COMMIT_APPROVED',
        formal_delivery_complete=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--host-gcc',default='G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe')
    ap.add_argument('--preseal',action='store_true');ap.add_argument('--output',type=Path);a=ap.parse_args()
    result=validate(a.root,a.host_gcc,not a.preseal)
    if a.output:
        need(not a.output.exists(),'Preserve prior verification receipts');a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
