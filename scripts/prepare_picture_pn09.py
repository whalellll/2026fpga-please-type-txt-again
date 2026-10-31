"""Create separate PN09 SD files from the immutable PN08 payloads and r13/r14.

No media access or selector/Flash write. Original source bindings stay tied to
their original bytes; new GUI/worker inputs get separate source identities.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import re
import struct
import subprocess
import zipfile
import zlib

from picture_workspace import ROOT, workspace_path
from prepare_xinyi_cpu60_kit import identity, require, cpio_read, cpio_write, elf32
from prepare_picture_candidate import tokens

E42='e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b'
PN08='8e407d66c5973d9c8df0f74b5106859bc27e4a3171d87012cfb3da75ef2a937a'
GUI_ZIP='18a5b198e2bd70215030b2a4f78c24fc8058f521af3d178fc346e056ef559f17'
GUI='6c1483df37ff2633eb2eeb967a04d04eaa6173a8e4eb57998f75b1dc77ae1c69'
WORKER='efa12b64e4350373dac3620eb071cb6ed528a821772cb406ea690159d6ffb821'
SPEECH='b0f27d0679a36c07944575add15cf8b33872dbc45a5304a27827d2a0415b3211'
SHA=lambda b:hashlib.sha256(b).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['output','pn08','pn08-source-bindings','gui-package','worker-directory',
                 'speech-payload','speech-identity','program-receipt']:
        ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args();logical=a.output.absolute()
    require(logical.is_relative_to(ROOT/'build'),'Use the private build junction')
    out=workspace_path(logical)
    require(out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()),'Use the explicit E build junction')
    require(not out.exists(),'Preserve every prior candidate');out.mkdir(parents=True)
    inputs={};commands=[]
    def read(path):
        p=Path(path).resolve();data=p.read_bytes();v=identity(data)
        require(str(p) not in inputs or inputs[str(p)]==v,'Conflicting source identity')
        inputs[str(p)]=v;return data
    def save(path,data):
        require(not path.exists(),'Never replace an existing output: '+str(path))
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def record(path,value):save(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    read(__file__)
    for s in ['scripts/prepare_xinyi_cpu60_kit.py','scripts/prepare_picture_candidate.py',
              'scripts/picture_workspace.py','scripts/build_xinyi_cpu60_loader.ps1','scripts/riscv_toolchain.ps1',
              'scripts/check_xinyi_pn05_overlay.py']:read(ROOT/s)
    mdata=read(a.pn08/'manifest.json');require(SHA(mdata)==PN08,'Exact PN08 base manifest required')
    base=json.loads(mdata)
    require(base['prefix']=='PN08' and base['target_bitstream_sha256']==E42,'Wrong inherited target')
    receipt=json.loads(read(a.program_receipt))
    require(receipt['status']=='PASS' and receipt['operation']=='CRAM' and receipt['audit_profile']=='PublishedE42'
        and receipt['bitstream_sha256']==E42 and receipt['device_id']=='0x00602899'
        and receipt['device_count']==1 and receipt['native_input_hashes']==498,'Exact assignment evidence required')
    original=json.loads(read(a.pn08_source_bindings));lookup={r['original_path']:r for r in original['rows']}
    require(len(lookup)==len(base['source_inputs'])==295,'Complete original source coverage required')
    for name,v in base['source_inputs'].items():
        row=lookup[name];data=read(row['verified_path'])
        require(identity(data)==v and row['sha256']==v['sha256'],'Original compiled source drift: '+name)
    reused={}
    for name,v in base['reused_sd_files'].items():
        reused[name]=read(a.pn08/'payloads'/name);require(identity(reused[name])==v,'Inherited payload drift')
    old_files={}
    for name,v in base['new_sd_files'].items():
        old_files[name]=read(a.pn08/'sd-update'/name);require(identity(old_files[name])==v,'PN08 update drift')
    # The old .JSN/.SHA are additional integrity entries, not boot descriptors.
    pn04=cpio_read(reused['PN04FS.BIN']);merged=dict(pn04)
    merged.update(cpio_read(gzip.decompress(old_files['PN08UPD.GZ'])))
    for name,h in base['selected_rootfs_sha256'].items():require(SHA(merged[name][1])==h,'PN08 overlay mismatch')
    inherited=dict(merged)
    package=read(a.gui_package);require(SHA(package)==GUI_ZIP,'Selected r13 GUI package required')
    with zipfile.ZipFile(a.gui_package) as z:
        require(z.testzip() is None,'GUI ZIP CRC failure')
        gm=json.loads(z.read('manifest.json'));gui=z.read('software/cpu60/gui.rv32.elf')
        for s,h in gm['sources_sha256'].items():require(SHA(read(ROOT/s))==h,'GUI source drift: '+s)
    require(SHA(gui)==GUI,'Wrong CPU60 GUI');elf32(gui,'PN09 r13 GUI')
    worker=read(a.worker_directory/'xq-coach-worker-stripped');elf32(worker,'PN09 r14 worker')
    require(SHA(worker)==WORKER,'Selected r14 worker required')
    before=read(a.worker_directory/'source-before.sha256')
    require(before==read(a.worker_directory/'source-after.sha256'),'Worker build inputs were unstable')
    for line in before.decode().splitlines():
        h,s=line.split(maxsplit=1);require(re.match(r'^/mnt/[a-z]/',s),'Expected bound WSL input')
        require(SHA(read(Path(s[5].upper()+':'+s[6:])))==h,'Worker source drift: '+s)
    options=dict(s.split('=',1) for s in read(a.worker_directory/'runtime-config.txt').decode().splitlines())
    require(options.get('geometry_min_bits')=='1' and options.get('grid_dot_cache')=='1'
        and options.get('graph_profile')=='0' and options.get('geometry_fused')=='1','Wrong worker feature selection')
    speech_manifest=json.loads(read(a.speech_identity));speech=read(a.speech_payload/'speech-worker')
    require(SHA(speech)==SPEECH==speech_manifest['files']['speech-worker']['sha256'],'Matching r11 speech helper required')
    elf32(speech,'PN09 move speech')
    replacements={'usr/bin/xinyi-one':gui,'usr/bin/xq-coach-worker':worker,'usr/bin/xinyi-speech-worker':speech}
    for name,v in speech_manifest['files'].items():
        if not name.startswith('pcm/move/'):continue
        data=read(a.speech_payload/name);require(identity(data)['sha256']==v['sha256'],'Move PCM drift: '+name)
        replacements['opt/xq-picture/'+name]=data
    require(len(replacements)>20,'Complete move asset set required')
    inode=max(v[0][0] for v in merged.values())+1
    def replace(name,data,mode=0o100644):
        nonlocal inode
        if name in merged:
            fields=merged[name][0].copy();require(fields[4]==1,'Do not replace hard links')
        else:
            fields=[inode,mode,0,0,1,0,0,0,0,0,0,0,0];inode+=1
        merged[name]=(fields,data)
    for name,data in replacements.items():
        for parent in reversed(Path(name).parents):
            key=parent.as_posix()
            if key!='.' and key not in merged:
                merged[key]=([inode,0o40755,0,0,2,0,0,0,0,0,0,0,0],b'');inode+=1
        replace(name,data,0o100755 if name.startswith('usr/bin/') else 0o100644)
    sums={}
    for line in inherited['opt/xinyi/runtime.sha256'][1].decode().splitlines():
        h,path=line.split('  ',1);sums[path]=h
    for name,data in replacements.items():sums['/'+name]=SHA(data)
    replace('opt/xinyi/runtime.sha256',''.join(h+'  '+s+'\n' for s,h in sorted(sums.items())).encode('ascii'))
    for path,h in sums.items():require(SHA(merged[path.lstrip('/')][1])==h,'Runtime hash closure failure')
    require(merged['opt/xinyi/models.sha256']==inherited['opt/xinyi/models.sha256'],'Frozen model list changed')
    changed=[n for n in merged if n not in inherited or merged[n]!=inherited[n]]
    permitted=set(replacements)|{'opt/xinyi/runtime.sha256','opt/xq-picture/pcm/move'}
    require(set(changed)<=permitted,'Unexpected effective rootfs change')
    for n in inherited:
        if n not in permitted:require(merged[n]==inherited[n],'Unselected inherited content drift: '+n)
    delta={n:v for n,v in merged.items() if n not in pn04 or v!=pn04[n]}
    for n in list(delta):
        for parent in Path(n).parents:
            key=parent.as_posix()
            if key!='.' and key in merged:delta.setdefault(key,merged[key])
    overlay=gzip.compress(cpio_write(delta),compresslevel=9,mtime=0)
    final=dict(pn04);final.update(cpio_read(gzip.decompress(overlay)))
    require(final==merged,'Overlay reconstruction mismatch')
    offset=base['overlay_offset'];require(offset+len(overlay)<=base['rootfs_aperture_bytes']==0x1000000,'Rootfs aperture exceeded')
    dtb=bytearray(old_files['PN08.DTB']);head,props,_=tokens(dtb);original_props={k:v[0] for k,v in props.items()}
    end=struct.pack('>I',0x03000000+offset+len(overlay));at=head[2]+props['/chosen/linux,initrd-end'][1]
    dtb[at:at+4]=end;_,props,_=tokens(dtb);original_props['/chosen/linux,initrd-end']=end
    require({k:v[0] for k,v in props.items()}==original_props,'Unexpected DT change')
    support=out/'support'
    for f in sorted((a.pn08/'support').rglob('*')):
        if f.is_file() and f.name!='payloads.h':save(support/f.relative_to(a.pn08/'support'),read(f))
    entries=[(n,addr,reused[n]) for n,addr in [('PN04SBI.BIN',0x18000000),('PN04FS.BIN',0x03000000),
        ('PN04NN.PFF',0x10000000),('PN04ATK.BIN',0x15000000)]]
    entries += [('PN09K.BIN',0x00400000,old_files['PN08K.BIN']),('PN09.DTB',0x1a000000,bytes(dtb)),
                ('PN09UPD.GZ',0x03000000+offset,overlay)]
    header=('#include "fat_ro.h"\n#define XINYI_BOOT_PREFIX "PN09"\n#define XINYI_ROOTFS_OVERLAY 1\n'
        f'#define XINYI_ROOTFS_BASE_BYTES {base["rootfs_base_bytes"]}u\n#define XINYI_ROOTFS_OVERLAY_OFFSET {offset}u\n'
        'typedef struct {const char *name;uint32_t address,bytes,crc32;fat_ro_file_t file;} payload_t;\nstatic payload_t payloads[]={\n')
    for name,addr,data in entries:
        save(out/'payloads'/name,data);header+=f'{{"{name}",0x{addr:08x}u,{len(data)}u,0x{zlib.crc32(data):08x}u,{{0}}}},\n'
    header+='};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n';save(support/'payloads.h',header.encode())
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/build_xinyi_cpu60_loader.ps1'),
        '-CandidateDirectory',str(logical),'-Prefix','PN04']
    proc=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=180)
    save(out/'evidence/loader-build.log',proc.stdout+proc.stderr);require(proc.returncode==0,'Loader build failed')
    commands.append(dict(name='loader-gcc16',exit=0,log=identity(proc.stdout+proc.stderr)))
    binary=read(out/'PN04BOOT.BIN')
    for name,addr,data in entries:
        descriptor=struct.pack('<III',addr,len(data),zlib.crc32(data));require(binary.count(descriptor)==1,'Descriptor mismatch')
        at=binary.index(descriptor);ptr=struct.unpack_from('<I',binary,at-4)[0]-0x01000000
        require(binary[ptr:ptr+len(name)+1]==name.encode()+b'\0','Descriptor filename mismatch')
    for name,addr,data in entries:
        if name.startswith('PN09'):save(out/'sd-update'/name,data)
    save(out/'sd-update/PN09BOOT.BIN',binary);save(out/'payloads/PN09BOOT.BIN',binary)
    public=dict(schema='picture-pn09/1',status='PN09_CPU60_R13_R14_CANDIDATE_NOT_INSTALLED_SD_BOOT_NOT_TESTED',prefix='PN09',
        target_bitstream_sha256=E42,cpu_hz=60000000,sys_hz=49500000,base_pn08_manifest_sha256=PN08,
        kernel_sha256=base['kernel_sha256'],models_sha256_unchanged=True,geometry_thresholds_unchanged=True,
        estimated_board_recommendations_preserved=True,rootfs_base_bytes=base['rootfs_base_bytes'],overlay_offset=offset,
        overlay_bytes=len(overlay),rootfs_bound_bytes=offset+len(overlay),rootfs_aperture_bytes=0x1000000,
        changed_rootfs_paths=changed,selected_rootfs_sha256={n:SHA(merged[n][1]) for n in replacements},
        reused_sd_files=base['reused_sd_files'],new_sd_files={f.name:identity(f.read_bytes()) for f in (out/'sd-update').iterdir()},
        software_options=options,actual_board_latency_pass=False,recognition_300s_new_candidate_pass=False,
        hardware_used=False,sd_written=False,flash_written=False,selector_modified=False,production_ready=False,
        original_pn08_source_count=295,new_gui_source_count=len(gm['sources_sha256']))
    record(out/'sd-update/PN09.JSN',public)
    save(out/'sd-update/PN09.SHA',''.join(SHA(f.read_bytes())+'  '+f.name+'\n' for f in sorted((out/'sd-update').iterdir())).encode())
    for f in sorted(support.rglob('*')):
        if f.is_file():read(f)
    require(all(identity(Path(s).read_bytes())==v for s,v in inputs.items()),'Inputs changed during preparation')
    public.update(source_inputs=inputs,commands=commands)
    record(out/'manifest.json',public)
    save(out/'README.txt',('PN09 / E42 CPU60 软件候选，原 PN08 和全部旧文件保留。\n'
        'sd-update/ 内六个 PN09 文件为新增 SD 根目录文件；不要覆盖 PN08*、PN04* 或 XQBOOT.CFG。\n'
        '沿用卡上原 PN04SBI.BIN、PN04FS.BIN、PN04NN.PFF、PN04ATK.BIN，SHA/CRC 见 PN09.JSN。\n'
        'PN09BOOT.BIN 为只读 loader；经核验的 E42/CPU60 ROM 可将它加载至 0x01000000 后启动。\n'
        '本包不改变自动启动选择器，不含写卡器。复制新文件不等于已切换自动启动版本。\n'
        '包含 r13 新 GUI、r14 识别候选及匹配 r11 短走法语音资源。模型、比例、几何门槛和估计荐着不变。\n'
        'r13 首页已有本次 RAM 实板确认；新 worker 实板性能和整个 PN09 SD 冷启动仍待验证。\n'
        '不是正式发布，不将旧 r09 单轮 <300 秒证据继承给新软件。\n').encode('utf8'))
    print(public['status'],len(overlay))


if __name__=='__main__':main()
