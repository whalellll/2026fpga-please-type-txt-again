"""Build/test/package a private PN03 loader without touching any board or SD.

Uses exact CPU60 ROM sources from the integrated60 Git object and GCC16.2.
The input kit can be any validated prepare_xinyi_cpu60_kit output of this ABI.
No shared selector/configuration or installer is produced.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib
import zipfile

from build_cpu80_conv_sd import make_fat32, wsl_path
from prepare_xinyi_cpu60_kit import identity, require, SBI_SHA, PFF_SHA, ATK_SHA, cpio_read, coach_binding

ROOT=Path(__file__).resolve().parents[1]
REF='127ff9a5b517f0f298ab91492d07ef2a1cf44f5b'
TARGET='9ba02f105d6168e9445e9a15e2f7a1093d885229deae9e268994acdbe29f5ea1'
P3_REF='e7288be9e49f348b37832a65415b6989c444384c'
P3_TARGET='6565ad378524f3e2a34f6cdba6fcc46b2f928eb3677c0fe80971e05e8ec2ebdd'
ROM_SHA='a67f5c77e45160cfe2b397fb19a071939771a1f2dc17dfd2b23a6cb5e2fa2a6d'
BOOT_SHA='6e2728d6698acb9f201883f4b01ce446515baca967f9a0a905a4d95e9c62383f'
BUILD_SHA='e900b7dcada5e35226f7cbf94562e514ed9155b29c5aceb5e8212eaa67244428'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def build(args):
    p3=args.target_profile=='MainP3'
    target=P3_TARGET if p3 else TARGET
    ref=P3_REF if p3 else REF
    prefix='PN04' if p3 else 'PN03'
    out=args.output.resolve()
    require(out.is_relative_to((ROOT/'build').resolve()) and out!=(ROOT/'build').resolve() and not out.exists(),
            'Choose a fresh output directory strictly under build/')
    require(not out.with_suffix('.zip').exists(),'Do not overwrite an archive')
    source_inputs={}
    git_inputs={}
    def read(path):
        path=Path(path).resolve();data=path.read_bytes();source_inputs[str(path)]=identity(data);return data
    def git(path):
        data=subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT,timeout=30)
        git_inputs[path]=identity(data);return data
    read(__file__)
    read(ROOT/'scripts/build_xinyi_cpu60_loader.ps1')
    read(ROOT/'scripts/riscv_toolchain.ps1')
    read(ROOT/'scripts/build_cpu80_conv_sd.py')
    read(ROOT/'scripts/prepare_xinyi_cpu60_kit.py')
    kit=args.kit.resolve();manifest=json.loads(read(kit/'manifest.json'))
    require(manifest['status']=='XINYI_CPU60_RAM_INPUTS_VERIFIED_NOT_BOOTABLE_SD_KIT_NOT_BOARD' and
            manifest['cpu_hz']==60000000 and manifest['sys_hz']==49500000 and manifest['sbi_ratio']==[33,40] and
            manifest['prefix']==prefix and manifest['target_bitstream_sha256']==target and
            not any(manifest[k] for k in ['hardware_used','sd_written','flash_written','installed','loader_ready']),
            'Expected a valid CPU60/33:40 PN03 RAM-material kit, without installation claims')
    contract=manifest.get('coach_contract')
    require(isinstance(contract,dict) and contract.get('release_ack_status')==9 and
            contract.get('idle_required') is True and contract.get('unknown_drain_rejected') is True and
            contract.get('geometry_native_statuses')==[2,5,6] and contract.get('geometry_wire_status')==5 and
            contract.get('source_verified') is True,'Old or unproved coach material is forbidden')
    expected={
        'PN03SBI.BIN':('sbi',0x18000000,SBI_SHA),
        'PN03K.BIN':('kernel',0x00400000,None),'PN03FS.BIN':('rootfs',0x03000000,None),
        'PN03.DTB':('dtb',0x1a000000,None),'PN03NN.PFF':('nnue',0x10000000,PFF_SHA),
        'PN03ATK.BIN':('attack',0x15000000,ATK_SHA)}
    expected={name.replace('PN03',prefix):value for name,value in expected.items()}
    require(set(manifest['files'])==set(expected),'Expected exactly six private payloads')
    payload_data={}
    for name,(role,address,frozen) in expected.items():
        data=read(kit/'ram-payloads'/name);record=manifest['files'][name]
        require(identity(data)=={key:record[key] for key in ['bytes','sha256','crc32']} and
                record['role']==role and int(record['address'],16)==address and
                (frozen is None or sha(kit/'ram-payloads'/name)==frozen),'Kit payload identity mismatch: '+name)
        payload_data[name]=data
    require(len(payload_data[prefix+'FS.BIN'])<=0x1000000,'Rootfs exceeds frozen 16MiB aperture')
    rootfs=cpio_read(payload_data[prefix+'FS.BIN'])
    worker=rootfs['usr/bin/xq-coach-worker'][1]
    worker_sha=hashlib.sha256(worker).hexdigest()
    require(worker_sha==contract['worker_sha256']==
            manifest['selected_rootfs_payloads']['usr/bin/xq-coach-worker']['sha256'],
            'Actual rootfs coach bytes do not match the proof')
    proof_paths=[Path(path) for path,value in manifest['input_files'].items()
                 if value['sha256']==contract.get('proof_sha256')]
    require(len(proof_paths)==1,'Missing/ambiguous coach proof source')
    proof_bytes=read(proof_paths[0]);proof=json.loads(proof_bytes)
    rebound=coach_binding(worker,proof);rebound['proof_sha256']=hashlib.sha256(proof_bytes).hexdigest()
    require(rebound==contract,'Coach proof/current sources no longer match the kit')
    for path,value in proof['sources_sha256'].items():
        candidate=Path(path);candidate=candidate if candidate.is_absolute() else ROOT/candidate
        require(sha(candidate)==value,'Coach proof source mismatch: '+str(candidate));read(candidate)
    header=read(kit/'xinyi_payloads.h')
    for name,(role,address,_) in expected.items():
        macro='XINYI_'+role.upper();v=manifest['files'][name]
        for line in [f'#define {macro}_NAME "{name}"',f'#define {macro}_ADDR 0x{address:08x}u',
                     f'#define {macro}_BYTES {v["bytes"]}u',f'#define {macro}_CRC 0x{v["crc32"]}u']:
            require(line.encode() in header,'Kit CRC header mismatch: '+macro)
    # Validate DT binding without modifying the material kit.
    from prepare_picture_candidate import tokens
    read(ROOT/'scripts/prepare_picture_candidate.py')
    _,props,_=tokens(payload_data[prefix+'.DTB'])
    require(props['/cpus/timebase-frequency'][0]==struct.pack('>I',60000000) and
            props['/cpus/cpu@0/clock-frequency'][0]==struct.pack('>I',60000000) and
            props['/chosen/linux,initrd-end'][0]==struct.pack('>I',0x03000000+len(payload_data[prefix+'FS.BIN'])),
            'DT CPU/initrd mismatch')
    if p3:
        from verify_integrated_opt60_main import verify
        require(verify()['bitstream_sha256']==target,'Current P3 hardware differs from main publication')
        snapshot=json.loads(git('artifacts/build_snapshot.json'))
        publication=json.loads(git('artifacts/INTEGRATED_OPT60_MAIN.json'))
        target_manifest=dict(bitstream=dict(sha256=publication['bitstream_sha256']),cpu_hz=publication['cpu_hz'],
            sys_hz=publication['sys_hz'],sta_pass=publication['hardware_final_sta_pass'])
    else:
        snapshot=json.loads(git('docs/validation/integrated60-linefix-functional-trial-20261024-02/build_snapshot.json'))
        target_manifest=json.loads(git('artifacts/integrated60_linefix_trial_20261024/manifest.json'))
    require(target_manifest['bitstream']['sha256']==target and target_manifest['cpu_hz']==60000000 and
            target_manifest['sys_hz']==49500000,'Unexpected CPU60 target')
    rom_hex=git('artifacts/bootrom.hex');boot=git('artifacts/bootloader.bin');build_record=git('artifacts/bootloader.build.json')
    require(hashlib.sha256(rom_hex).hexdigest()==snapshot['inputs']['artifacts/bootrom.hex']==ROM_SHA and
            hashlib.sha256(boot).hexdigest()==snapshot['inputs']['artifacts/bootloader.bin']==BOOT_SHA and
            hashlib.sha256(build_record).hexdigest()==BUILD_SHA,'Frozen target ROM identity mismatch')
    rom=b''.join(int(word,16).to_bytes(4,'little') for word in rom_hex.split())
    require(len(rom)==0x20000 and rom[:len(boot)]==boot,'ROM hex/binary byte mapping mismatch')
    meta=json.loads(build_record);code=meta['code_validation']
    start=int(code['CodeStart'],16);end=int(code['CodeEndExclusive'],16)
    require(start==0x1c000000 and end==0x1c013cd4 and end-start==code['BytesChecked'] and not (end-start)&3,
            'Unexpected immutable target ROM code interval')
    code_crc=zlib.crc32(rom[:end-start])
    target_sources={}
    for name in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h','camera.h']:
        path='sw/bootloader/'+name;data=git(path)
        require(hashlib.sha256(data).hexdigest()==snapshot['inputs'][path],'Frozen target source mismatch: '+path)
        target_sources[name]=data
    require(b'#define CPU_CLOCK_HZ 60000000u' in target_sources['soc.h'],'CPU80 soc.h is forbidden')
    # All mutations start only after identities and the source kit have passed.
    out.mkdir(parents=True);support=out/'support';support.mkdir();bootdir=support/'boot';bootdir.mkdir()
    stage=out/'payloads';stage.mkdir();ev=out/'evidence';ev.mkdir();testdir=out/'tests';testdir.mkdir()
    for name,data in target_sources.items():(bootdir/name).write_bytes(data)
    for name in ['loader.c','host_test.c','link.ld','start.S']:(support/name).write_bytes(read(ROOT/'linux/xinyi_board/boot'/name))
    git('linux/boot/v2_1_sd/source/start.S') # Origin; private startup spells fence.i as an instruction, not .word data.
    for name in ['xq_camera.c','xq_camera.h','xq_vision.h']:
        (support/name).write_bytes(read(ROOT/'linux/vision'/name))
    (support/'xiangqi_search.h').write_bytes(read(ROOT/'sw/xiangqi/xiangqi_search.h'))
    (support/'xinyi_payloads.h').write_bytes(header+f'\n#define XINYI_BOOT_PREFIX "{prefix}"\n'.encode())
    (support/'target.h').write_text(f'/* Exact CPU60 immutable ROM code, not mutable BRAM data. */\n'
        f'#define XINYI_ROM_CODE_START 0x{start:08x}u\n#define XINYI_ROM_CODE_BYTES {end-start}u\n'
        f'#define XINYI_ROM_CODE_CRC 0x{code_crc:08x}u\n',encoding='ascii')
    table='#ifndef XINYI_PAYLOADS_H\n#define XINYI_PAYLOADS_H\n#include "fat_ro.h"\n#include "xinyi_payloads.h"\n'
    table+='typedef struct { const char *name; uint32_t address,bytes,crc32; fat_ro_file_t file; } payload_t;\nstatic payload_t payloads[]={\n'
    for name,(role,_,_) in expected.items():
        m='XINYI_'+role.upper();table+=f' {{{m}_NAME,{m}_ADDR,{m}_BYTES,{m}_CRC,{{0}}}},\n'
        (stage/name).write_bytes(payload_data[name])
    table+='};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n#endif\n'
    (support/'payloads.h').write_text(table,encoding='ascii')
    (support/'target-rom.bin').write_bytes(rom)
    (support/'target-rom.hex').write_bytes(rom_hex)
    (support/'target-bootloader.bin').write_bytes(boot)
    (support/'target-bootloader.build.json').write_bytes(build_record)
    commands=[]
    def run(command,name,timeout=180):
        p=subprocess.run([str(v) for v in command],cwd=ROOT,capture_output=True,timeout=timeout)
        log=p.stdout+p.stderr;(ev/(name+'.log')).write_bytes(log)
        commands.append(dict(name=name,argv=[str(v) for v in command],exit=p.returncode,log_sha256=hashlib.sha256(log).hexdigest()))
        require(p.returncode==0,name+' failed: '+log.decode(errors='replace')[-1800:]);return log
    run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/build_xinyi_cpu60_loader.ps1',
         '-CandidateDirectory',out,'-ToolchainRoot',args.toolchain_root,'-Prefix',prefix],'gcc16-build',300)
    binary=(out/(prefix+'BOOT.BIN')).read_bytes();elf=(out/(prefix+'BOOT.ELF')).read_bytes()
    require(elf[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<H',elf,18)[0]==243 and
            struct.unpack_from('<I',elf,24)[0]==0x01000000 and struct.unpack_from('<I',elf,36)[0]==0,
            'Expected RV32 ELF32 entry01000000 flags0')
    require(0<len(binary)<=0x100000-16384 and len(binary)%4==0,'Loader must fit 1MiB with 16KiB stack and menu word publication')
    descriptors={}
    for name,(_,address,_) in expected.items():
        r=manifest['files'][name];needle=struct.pack('<III',address,r['bytes'],int(r['crc32'],16))
        require(binary.count(needle)==1,'Compiled descriptor missing/ambiguous: '+name)
        offset=binary.index(needle);pointer=struct.unpack_from('<I',binary,offset-4)[0]-0x01000000
        require(0<=pointer<len(binary) and binary[pointer:pointer+len(name)+1]==name.encode()+b'\0','Compiled loader filename mismatch')
        descriptors[name]=dict(address=hex(address),**identity(payload_data[name]))
    shutil.copyfile(out/(prefix+'BOOT.BIN'),stage/(prefix+'BOOT.BIN'))
    def wsl(command,name,timeout=180):return run(['wsl.exe','-d',args.distro,'--',*command],name,timeout)
    inc=['-I',wsl_path(bootdir),'-I',wsl_path(support)]
    hflags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',*inc]
    wsl(['gcc',*hflags,'-Dmain=xinyi_boot_main','-c',wsl_path(support/'loader.c'),'-o',wsl_path(support/'host-loader.o')],'host-loader')
    common=[wsl_path(support/'host_test.c'),wsl_path(bootdir/'fat_ro.c'),wsl_path(bootdir/'crc32_fast.c'),wsl_path(support/'xq_camera.c')]
    wsl(['gcc',*hflags,*common,wsl_path(support/'host-loader.o'),'-Wl,--gc-sections','-o',wsl_path(support/'host-test')],'host-test-link')
    cc='/opt/toolchain/bin/riscv32-linux-musl-gcc'
    wsl([cc,'-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static',*hflags,*common,
         wsl_path(out/'rv32-loader-test.o'),'-Wl,--gc-sections','-o',wsl_path(support/'rv32-test')],'rv32-same-object-link')
    fixture=testdir/'synthetic-only-fat32.img';locations=make_fat32(fixture,sorted(stage.iterdir()))
    tests=[]
    def test(scenario,label=None,rv32=False):
        prefix=['qemu-riscv32'] if rv32 else []
        label=('rv32-' if rv32 else 'host-')+(label or scenario)
        result=wsl([*prefix,wsl_path(support/('rv32-test' if rv32 else 'host-test')),scenario,wsl_path(fixture),
                    wsl_path(stage),wsl_path(support/'target-rom.bin')],label,180)
        require(('HOST_TEST_PASS '+scenario).encode() in result,'Missing test completion: '+label)
        tests.append(dict(name=label,scenario=scenario,rv32_same_gcc16_object=rv32,status='PASS'))
    for scenario in ['pass','clock','sys','timebase','capability','rom','init','io','abort','camera-busy','camera-stuck','rom-data']:
        test(scenario)
    for scenario in ['pass','clock','rom','camera-busy','camera-stuck']:
        test(scenario,rv32=True)
    def mutation(offset,replacement,label,scenario='reject'):
        with fixture.open('r+b') as f:f.seek(offset);old=f.read(len(replacement));f.seek(offset);f.write(replacement)
        try:test(scenario,label)
        finally:
            with fixture.open('r+b') as f:f.seek(offset);f.write(old)
    offset=locations[prefix+'K.BIN']['data']+100
    with fixture.open('rb') as f:f.seek(offset);old=f.read(1)
    mutation(offset,bytes([old[0]^1]),'corrupt-kernel')
    mutation(locations[prefix+'NN.PFF']['directory'],b'\xe5','missing-model','metadata')
    mutation(locations[prefix+'SBI.BIN']['directory']+28,struct.pack('<I',1),'wrong-sbi-size','metadata')
    mutation(510,b'\0\0','bad-fat-signature')
    # Verify copied originals again after the synthetic mutation campaign.
    for name,data in payload_data.items():require((stage/name).read_bytes()==data,'Original payload changed')
    for path,value in source_inputs.items():require(identity(Path(path).read_bytes())==value,'Build source changed: '+path)
    menu_line=f'Xinyi_CPU60_{prefix} {prefix}BOOT.BIN {len(binary)} {zlib.crc32(binary):08x}\n'
    (out/'menu-entry.proposed.txt').write_text(menu_line,encoding='ascii')
    record=dict(status='CPU60_PN03_LOADER_AND_SIX_PAYLOADS_OFFLINE_VERIFIED_NOT_INSTALLED_NOT_BOARD',
        target_ref=ref,target_profile=args.target_profile,prefix=prefix,target_bitstream_sha256=target,target_sta_pass=target_manifest['sta_pass'],
        hardware_used=False,sd_written=False,flash_written=False,selector_modified=False,installed=False,
        native_preflight_complete=False,
        missing_native_gate_names=[] if p3 else ['preflight_gate.json','cpu_ads_controls.json','gui1080_placement.json','cpu-sys-cdc-post-route.json'],
        production_ready=False,board_validated=False,rom_rebuilt=False,loader_entry='0x01000000',
        kit_manifest_path=str(kit/'manifest.json'),kit_manifest_sha256=sha(kit/'manifest.json'),
        coach_contract=contract,
        cpu_hz=60000000,sys_hz=49500000,sbi_ratio=[33,40],source_inputs=source_inputs,git_inputs=git_inputs,
        target_rom_hex_sha256=ROM_SHA,target_bootloader_sha256=BOOT_SHA,
        runtime_rom_code=dict(start=hex(start),bytes=end-start,crc32=f'{code_crc:08x}',
             scope='Immutable executable interval only; mutable BRAM data/BSS/stack excluded. Not bitstream authentication.'),
        camera_handoff=dict(enable=0,writer_busy=0,stopping=0,idle=1,method='xqc_stop native DDR drain; no sensor start; final idle recheck'),
        loader=identity(binary),elf=identity(elf),compiled_descriptors=descriptors,
        files={p.name:identity(p.read_bytes()) for p in sorted(stage.iterdir())},
        compiler=json.loads((out/'compile.json').read_text(encoding='utf-8-sig')),commands=commands,tests=tests,
        synthetic_fat=dict(path=str(fixture),bytes=fixture.stat().st_size,sha256=sha(fixture),deployable=False,cid='0'*32),
        remaining=['Native CRAM programming gates and fresh device audit remain separate.',
                   'Actual SD media/CID write authorization and unchanged-selector entry integration are not performed.',
                   'Board boot, physical Space/Esc, GUI, voice, recognition, accuracy and latency acceptance remain unmeasured.'])
    write(out/'manifest.json',record)
    (out/'README.txt').write_text('Private CPU60 PN03 candidate; NOT installed or board accepted.\n'
        'Functional candidate only. At preparation time the four original native gate files are missing: preflight_gate.json, cpu_ads_controls.json, gui1080_placement.json, cpu-sys-cdc-post-route.json. Their exact hashes and the original native preflight must pass before a board run; none is claimed here.\n'
        'payloads contains the seven new private files only. No shared selector/config or installation helper.\n'
        'The target ROM accepts loadx 0x01000000 then boot 0x01000000; this is a protocol contract, not an executed action.\n'
        'Any future selector entry must preserve existing entries and verify the PN03BOOT size/CRC shown in menu-entry.proposed.txt.\n'
        'Only volatile CRAM may be considered after the original programming gates; the trial target has failed STA and is not a release.\n'
        'Synthetic FAT fixture is host-only, all-zero CID, never a card or deployment receipt.\n',encoding='utf-8')
    if p3:
        record['status']='CPU60_PN04_MAIN_P3_LOADER_AND_SIX_PAYLOADS_OFFLINE_VERIFIED_NOT_INSTALLED_NOT_BOARD'
        write(out/'manifest.json',record)
        (out/'README.txt').write_text('Private PN04 product for main P3 CPU60/1080p30, bit6565ad37. Not installed or board accepted.\n'
            'Seven private payloads only. Preserve PN03, every existing file and XQBOOT.CFG. No installer/media write has run.\n'
            'Upstream main STA/publication identity checks passed; programming requires a fresh gated CRAM assignment and device audit.\n'
            'Do not use PN03 on P3 or PN04 on9ba02f10. A proposed menu line is review material only.\n'
            'CoreMark reference demo is labeled; real Linux results remain separate. Full board acceptance is pending.\n'
            'Synthetic FAT fixture is host-only with zero CID and excluded from this archive.\n',encoding='utf-8')
    packaged=[*sorted(stage.iterdir()),out/'manifest.json',out/'README.txt']
    (out/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(out).as_posix()}\n'
        for p in packaged),encoding='ascii')
    archive=out.with_suffix('.zip')
    # Only seven real private payloads and their contracts enter this archive.
    # Build sources/test artifacts remain separately reviewable in output/.
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in [*packaged,out/'SHA256SUMS.txt']:z.write(p,p.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None,'Archive CRC failure')
        for name in z.namelist():require(hashlib.sha256(z.read(name)).hexdigest()==sha(out/name),'Archive read-back SHA mismatch')
    write(out.with_suffix('.package.json'),dict(status='PASS',archive=identity(archive.read_bytes()),
        manifest_sha256=sha(out/'manifest.json'),sd_written=False,board_validated=False,
        excluded_synthetic_fat=identity(fixture.read_bytes())))
    print('XINYI_CPU60_'+prefix+'_OFFLINE_LOADER_PACKAGE_PASS_NOT_INSTALLED_NOT_BOARD',len(binary),len(tests))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--toolchain-root',default='D:/p17-gcc16-lto/native');p.add_argument('--distro',default='Ubuntu-22.04')
    p.add_argument('--target-profile',choices=['CPU60FunctionalTrial','MainP3'],default='CPU60FunctionalTrial')
    build(p.parse_args())
