"""Build a create-only PN05 update over the exact installed PN04 P3 base.

The Linux initramfs ABI permits raw-newc, zero padding, then gzip-newc. Only
the product ELF, coach ELF and their runtime hash list are replaced. Frozen
models/kernel/voice/engine and every PN04 file remain byte-identical. No media
access, programming or acceptance is performed by this builder.
"""
from pathlib import Path
import argparse,gzip,hashlib,json,shutil,struct,subprocess,zlib
from prepare_xinyi_cpu60_kit import ROOT,identity,require,cpio_read,cpio_write,elf32,coach_binding,P3_TARGET
from prepare_picture_candidate import tokens

BASE_MANIFEST='ea67b26cd0cd118ca102b3c2a00a01319ccd00e21328d38a78baeb44acce9fc5'
REF='e7288be9e49f348b37832a65415b6989c444384c'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['product','coach_proof','output']:
        p.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    p.add_argument('--base',type=Path,default=ROOT/'build/xinyi-offline-20261025/boot-p3-pn04-r02')
    a=p.parse_args();out=a.output.absolute()
    require(out.is_relative_to(ROOT/'build') and not out.exists(),'Fresh private build/ output required')
    resolved=out.resolve()
    require(resolved.is_relative_to(ROOT/'build') or resolved.is_relative_to(Path('E:/xinyi-board-20261025/generated').resolve()),'Output must remain in build/ or its verified generated-output junction')
    source_inputs={};commands=[]
    def read(path):
        path=Path(path).resolve();data=path.read_bytes();source_inputs[str(path)]=identity(data);return data
    def git(name):return subprocess.check_output(['git','show',REF+':'+name],cwd=ROOT,timeout=30)
    def save(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def record(path,value):save(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    def run(name,argv,timeout=300):
        r=subprocess.run(list(map(str,argv)),cwd=ROOT,capture_output=True,timeout=timeout)
        save(out/'evidence'/(name+'.log'),r.stdout+r.stderr)
        commands.append(dict(name=name,exit_code=r.returncode,log_sha256=hashlib.sha256(r.stdout+r.stderr).hexdigest()))
        require(r.returncode==0,name+': '+(r.stdout+r.stderr).decode(errors='replace')[-1800:])
    read(__file__);read(ROOT/'scripts/prepare_xinyi_cpu60_kit.py')
    base=json.loads(read(a.base/'manifest.json'))
    require(identity((a.base/'manifest.json').read_bytes())['sha256']==BASE_MANIFEST and base['target_bitstream_sha256']==P3_TARGET,'Use the exact PN04 P3 base, never PN03')
    originals={name:read(a.base/'payloads'/name) for name in base['files']}
    require(all(identity(data)==base['files'][name] for name,data in originals.items()),'PN04 base payload mismatch')
    product=read(a.product);elf32(product,'PN05 product')
    # Bind the selected stripped GUI to its actual build and current sources.
    product_dir=a.product.parent
    before=read(product_dir/'source-before.sha256');after=read(product_dir/'source-after.sha256')
    require(before==after,'GUI sources changed during compilation')
    wsl_root='/mnt/'+ROOT.drive[0].lower()+ROOT.as_posix()[2:]
    gui_sources=0
    for line in before.decode().splitlines():
        expected,path=line.split(maxsplit=1);path=path.lstrip('*')
        require(path.startswith(wsl_root+'/'),'GUI source proof must come from this checkout')
        data=read(ROOT/path[len(wsl_root)+1:]);require(identity(data)['sha256']==expected,'Stale GUI source proof');gui_sources+=1
    raw_product=read(product_dir/'xinyi-one')
    require(read(product_dir/'SHA256SUMS.txt').decode().split()[0]==identity(raw_product)['sha256'],'GUI build artifact changed')
    read(ROOT/'scripts/verify_xinyi_elf.py')
    from verify_xinyi_elf import inspect
    require(inspect(a.product)['allocated']==inspect(product_dir/'xinyi-one')['allocated'],'GUI strip changed allocated sections')
    proof=json.loads(read(a.coach_proof));worker_path=a.coach_proof.parent/'worker-coach-qemu/xq-coach-worker'
    worker=read(worker_path);elf32(worker,'PN05 coach');contract=coach_binding(worker,proof)
    for name in proof['sources_sha256']:read(ROOT/name)
    config=read(ROOT/'build/xinyi-offline-20261025/kernel-p3-r01/kernel.config')
    require(b'CONFIG_BLK_DEV_INITRD=y\n' in config and b'CONFIG_RD_GZIP=y\n' in config,'Kernel must support gzip initramfs overlays')
    rows=cpio_read(originals['PN04FS.BIN']);changes={}
    for name,data in [('usr/bin/xinyi-one',product),('usr/bin/xq-coach-worker',worker)]:
        require(rows[name][0][4]==1,'Executable must not be a hard link')
        changes[name]=(rows[name][0].copy(),data)
    hashes=rows['opt/xinyi/runtime.sha256'][1].decode();new_lines=[]
    for line in hashes.splitlines():
        digest,path=line.split('  ',1);name=path.lstrip('/')
        if name in changes:digest=identity(changes[name][1])['sha256']
        new_lines.append(digest+'  '+path)
    changes['opt/xinyi/runtime.sha256']=(rows['opt/xinyi/runtime.sha256'][0].copy(),('\n'.join(new_lines)+'\n').encode())
    archive=cpio_write(changes);overlay=gzip.compress(archive,compresslevel=9,mtime=0)
    decoded=cpio_read(gzip.decompress(overlay));merged=dict(rows);merged.update(decoded)
    changed=[name for name in merged if name not in rows or merged[name][1]!=rows[name][1]]
    require(set(changed)=={'usr/bin/xinyi-one','usr/bin/xq-coach-worker','opt/xinyi/runtime.sha256'},'Unexpected rootfs changes')
    for line in merged['opt/xinyi/runtime.sha256'][1].decode().splitlines():
        digest,path=line.split('  ',1);require(identity(merged[path.lstrip('/')][1])['sha256']==digest,'Merged runtime hash mismatch: '+path)
    offset=(len(originals['PN04FS.BIN'])+4095)&~4095
    require(offset+len(overlay)<=0x1000000,'Overlay exceeds the rootfs aperture')
    dtb=bytearray(originals['PN04.DTB']);h,props,_=tokens(dtb)
    before={name:v[0] for name,v in props.items()}
    struct.pack_into('>I',dtb,h[2]+props['/chosen/linux,initrd-end'][1],0x03000000+offset+len(overlay))
    _,after,_=tokens(dtb);expected=dict(before);expected['/chosen/linux,initrd-end']=struct.pack('>I',0x03000000+offset+len(overlay))
    require({name:v[0] for name,v in after.items()}==expected,'Unexpected DT change')
    out.mkdir(parents=True);support=out/'support';stage=out/'payloads';updates=out/'sd-update'
    for name in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h','camera.h']:
        data=git('sw/bootloader/'+name);require(data==(a.base/'support/boot'/name).read_bytes(),'Frozen P3 ROM helper mismatch');save(support/'boot'/name,data)
    for name in ['loader.c','host_test.c','link.ld','start.S']:save(support/name,read(ROOT/'linux/xinyi_board/boot'/name))
    for name in ['xq_camera.c','xq_camera.h','xq_vision.h']:save(support/name,read(ROOT/'linux/vision'/name))
    save(support/'xiangqi_search.h',read(ROOT/'sw/xiangqi/xiangqi_search.h'))
    for name in ['target.h','target-rom.bin','target-rom.hex','target-bootloader.bin','target-bootloader.build.json']:save(support/name,read(a.base/'support'/name))
    entries=[]
    for name in ['PN04SBI.BIN','PN04K.BIN','PN04FS.BIN','PN04NN.PFF','PN04ATK.BIN']:
        entries.append((name,int(base['compiled_descriptors'][name]['address'],16),originals[name]))
    entries.extend([('PN05.DTB',0x1a000000,bytes(dtb)),('PN05UPD.GZ',0x03000000+offset,overlay)])
    table=('#ifndef XINYI_PAYLOADS_H\n#define XINYI_PAYLOADS_H\n#include "fat_ro.h"\n'
        '#define XINYI_BOOT_PREFIX "PN05"\n#define XINYI_ROOTFS_OVERLAY 1\n'
        f'#define XINYI_ROOTFS_BASE_BYTES {len(originals["PN04FS.BIN"])}u\n#define XINYI_ROOTFS_OVERLAY_OFFSET {offset}u\n'
        'typedef struct {const char *name;uint32_t address,bytes,crc32;fat_ro_file_t file;} payload_t;\nstatic payload_t payloads[]={\n')
    for name,address,data in entries:
        save(stage/name,data);table+=f'{{"{name}",0x{address:08x}u,{len(data)}u,0x{zlib.crc32(data):08x}u,{{0}}}},\n'
    table+='};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n#endif\n';save(support/'payloads.h',table.encode())
    for name in ['build_xinyi_cpu60_loader.ps1','riscv_toolchain.ps1']:read(ROOT/'scripts'/name)
    # Reuse the audited compiler; PN04 here is only its local output filename.
    # The compiled descriptors, banner and actual SD filename all select PN05.
    run('loader-gcc16',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/build_xinyi_cpu60_loader.ps1','-CandidateDirectory',out,'-Prefix','PN04'])
    binary=read(out/'PN04BOOT.BIN')
    for name,address,data in entries:
        needle=struct.pack('<III',address,len(data),zlib.crc32(data));require(binary.count(needle)==1,'Missing compiled descriptor: '+name)
        i=binary.index(needle);ptr=struct.unpack_from('<I',binary,i-4)[0]-0x01000000
        require(binary[ptr:ptr+len(name)+1]==name.encode()+b'\0','Compiled filename mismatch')
    for name,data in [('PN05BOOT.BIN',binary),('PN05.DTB',bytes(dtb)),('PN05UPD.GZ',overlay)]:save(updates/name,data);save(stage/name,data)
    public=dict(status='PN05_OVERLAY_PREPARED_NOT_INSTALLED_NOT_BOARD',target_bitstream_sha256=P3_TARGET,
        base_manifest_sha256=BASE_MANIFEST,base_prefix='PN04',prefix='PN05',production_ready=False,
        hardware_used=False,sd_written=False,flash_written=False,selector_modified=False,
        rootfs_base_bytes=len(originals['PN04FS.BIN']),overlay_offset=offset,overlay_bytes=len(overlay),
        rootfs_bound_bytes=offset+len(overlay),rootfs_aperture_bytes=0x1000000,
        changed_rootfs_paths=changed,selected_rootfs_sha256={n:identity(merged[n][1])['sha256'] for n in changed},
        reused_sd_files={n:identity(d) for n,_,d in entries if n.startswith('PN04')},
        new_sd_files={p.name:identity(p.read_bytes()) for p in updates.iterdir()},coach_contract=contract,
        gui_contract=dict(source_stable=True,current_source_files=gui_sources,stripped_allocated_sections_equal=True),
        engineering_geometry_status_preserved=True,product_estimated_legal_recommendation=True,
        actual_board_latency_pass=False)
    record(updates/'PN05.JSN',public)
    # Generic audited root-pair installer; four new files, no PN04 rewrite.
    inst=out/'install';ist=inst/'support'
    for name in ['soc.h','sd.h','fat_ro.h','fat_ro.c','runtime.c','sd_native.c','crc32_fast.h','crc32_fast.c','console_line.h','console_line.c','camera.h']:
        save(ist/name,git('sw/bootloader/'+name))
    for name in ['fat_camera.h','fat_camera.c']:save(ist/name,read(ROOT/'linux/boot/v2_1_sd/source/picture_fat_write'/name))
    ns=read(ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sd_namespace_fat.c')
    original=b'#include "../../../linux/boot/v2_1_sd/source/picture_fat_write/fat_camera.c"'
    require(ns.count(original)==1,'Unknown namespace adapter');save(ist/'install_fat.c',ns.replace(original,b'#include "fat_camera.c"'))
    for name in ['install.c','install_xmodem.c','start.S','link.ld']:
        data=read(ROOT/'linux/xinyi_board/boot'/name)
        if name=='link.ld':data=data.replace(b'ORIGIN = 0x01000000',b'ORIGIN = 0x01800000')
        save(ist/name,data)
    save(ist/'target.h',(support/'target.h').read_bytes())
    install_files=[];header='#include <stdint.h>\n'
    for i,(name,address) in enumerate([('PN05.DTB',0x06000000),('PN05UPD.GZ',0x07000000),('PN05BOOT.BIN',0x01400000),('PN05.JSN',0x01600000)]):
        data=read(updates/name);save(inst/'payloads'/name,data)
        install_files.append(dict(name=name,address=address,aliases=[],**identity(data)))
        header+=f'static const uint32_t slice_crc_{i}[]={{'+','.join(f'0x{zlib.crc32(data[j:j+65536]):08x}u' for j in range(0,len(data),65536))+'};\n'
    header+='typedef struct {const char *name,*short_name;uint32_t address,bytes,crc;const char *aliases[4];int ready,exists;const uint32_t *slice_crc;uint32_t offset;} item_t;\nstatic item_t items[]={\n'
    for i,r in enumerate(install_files):
        stem,ext=r['name'].split('.');short=stem.ljust(8)+ext.ljust(3)
        header+=f'{{"{r["name"]}","{short}",0x{r["address"]:08x}u,{r["bytes"]}u,0x{r["crc32"]}u,{{0}},0,0,slice_crc_{i},0}},\n'
    header+='};\n#define INSTALL_COUNT 4u\n#define INSTALL_BOOT_INDEX 2u\n#define INSTALL_SECTORS 62333952u\n#define INSTALL_PARTITION 32u\n'
    save(ist/'install_payloads.h',header.encode())
    read(ROOT/'scripts/build_xinyi_sd_install.ps1');read(ROOT/'scripts/serial_install_xinyi_cpu60.ps1')
    run('installer-gcc16',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/build_xinyi_sd_install.ps1','-CandidateDirectory',inst])
    install_contract=dict(status='PN05_OVERLAY_CREATE_ONLY_INSTALL_NOT_INSTALLED',bitstream_sha256=P3_TARGET,
        media_sectors=62333952,partition_lba=32,cluster_bytes=32768,files=install_files,source_inputs=source_inputs,
        existing_files_preserved=True,selector_modified=False,sd_written=False,flash_written=False)
    record(inst/'install_contract.json',install_contract)
    require(all(identity(Path(path).read_bytes())==v for path,v in source_inputs.items()),'Source changed during build')
    public.update(source_inputs=source_inputs,commands=commands,installer_sha256=identity((inst/'PN03INST.BIN').read_bytes())['sha256'])
    record(out/'manifest.json',public)
    save(out/'README.txt',('Copy only sd-update/PN05BOOT.BIN, PN05.DTB, PN05UPD.GZ, PN05.JSN to SD root.\n'
        'Requires the exact original PN04SBI.BIN, PN04K.BIN, PN04FS.BIN, PN04NN.PFF, PN04ATK.BIN.\n'
        'Preserve every existing file and XQBOOT.CFG. No installation or board acceptance is claimed.\n').encode())
    print('PN05_OVERLAY_AND_CREATE_ONLY_INSTALLER_BUILT_NOT_INSTALLED',sum(r['bytes'] for r in install_files))

if __name__=='__main__':main()
