"""Assemble a software-only SD candidate and execute all18 real-loader tests."""
from pathlib import Path
import os,sys
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,shutil,struct,subprocess,zlib,tarfile,uuid,re

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
from workspace_paths import WORKSPACE,workspace_path,wsl_path
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source-root',type=Path,help='Explicit frozen hardware/software source, without changing its files')
ap.add_argument('--main-frequency',action='store_true',help='Source-verified merged-main frequency kit; real board acceptance remains separate')
ap.add_argument('--base-kit',type=Path,required=True)
ap.add_argument('--kernel',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--distro',default='pikafish-verify')
ap.add_argument('--gui1080',action='store_true',help='Use explicitly unbound1080p inputs; no inherited hardware pass')
ap.add_argument('--voice-nnue',action='store_true',help='Frozen CPU75/70 direct NNUE and voice inputs; no inherited hardware pass')
ap.add_argument('--local-oracle',action='store_true',help='Hash-verified WSL-local copy for identical loader test I/O')
ap.add_argument('--integrated60',action='store_true',help='Matched CPU60 voice2/Picture_new/Pikafish benchmark candidate')
ap.add_argument('--gui-driver',action='store_true',help='Integrated60 software-only GUI/driver kernel receipt; no inherited board pass')
ap.add_argument('--accum-resident',action='store_true',help='Integrated60 paired accumulator-resident kernel; board acceptance remains separate')
a=ap.parse_args();kit=a.base_kit.resolve();kernel=a.kernel.resolve();out=workspace_path(a.output)
if a.source_root:root=workspace_path(a.source_root)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
oracle_root=None
def linux(p):
    if oracle_root:
        try:return oracle_root+'/'+p.resolve().relative_to(out).as_posix()
        except ValueError:pass
    s=p.resolve().as_posix();assert s[1:3]==':/';return '/mnt/'+s[0].lower()+s[2:]
base=read(kit/'manifest.json');kb=read(kernel/'build.json')
if a.main_frequency:
    assert not any([a.accum_resident,a.gui_driver,a.gui1080,a.voice_nnue,a.integrated60])
    assert kb['status']=='RUNTIME_THREE_MODE_PROFILE_KERNEL_BUILD_PASS_NOT_BOARD'
    assert base['kernel_reuse']['status']=='DIAGNOSTIC_VISION_DRIVER_SOFTWARE_REPLACEMENT_SAME_CONFIG'
    assert base['kernel_reuse']['original_build_receipt_sha256']==sha(kernel/'build.json')
    for rel,h in base['kernel_reuse']['source_sha256'].items():assert sha(root/rel)==h,rel
elif a.accum_resident:
    assert a.integrated60 and not a.gui_driver and not a.gui1080 and not a.voice_nnue
    assert kb['status']=='ACCUM_RESIDENT_KERNEL_BUILD_PASS_NOT_BOARD'
    for name,h in kb['inputs_sha256'].items():assert sha(Path(name))==h,name
elif a.gui_driver:
    assert a.integrated60 and not a.gui1080 and not a.voice_nnue
    assert kb['status']=='GUI_DRIVER_KERNEL_BUILD_PASS_NOT_BOARD'
    for name,h in kb['inputs_sha256'].items():assert sha(Path(name))==h,name
else:
    assert kb['status']==('VOICE_NNUE_FROZEN_KERNEL_BUILD_PASS_NOT_BOARD' if a.voice_nnue or a.integrated60 else 'AUDIO_SERVICE_KERNEL_CONFIG_IDENTICAL_BUILD_PASS_BOARD_PENDING')
assert sha(kernel/'Image')==kb['outputs_sha256']['Image']
if a.main_frequency:
    clock=read(root/'config/clocks.json')
    assert base['status']=='MAIN_FREQUENCY_PREPARED_BOOT_INPUTS_UNTESTED'
    assert base['cpu_hz']==clock['cpu_hz']==75000000 and base['sys_hz']==clock['sys_hz']==49500000
    assert base['sbi_ratio']==[33,50] and base['clock_sha256']==sha(root/'config/clocks.json')
    assert base['candidate_run_id'] and base['candidate_bitstream_sha256']
elif a.integrated60:
    assert not a.voice_nnue and not a.gui1080
    assert base['status']=='INTEGRATED60_PREPARED_BOOT_INPUTS_UNTESTED'
    assert base['cpu_hz']==60000000 and base['sys_hz']==49500000
    assert base['clock_sha256']==sha(root/'config/clocks.json')
    assert base['display']=={'width':1920,'height':1080,'pixel_hz':74250000,'refresh_hz':30,'theme':'light'}
elif a.voice_nnue:
    assert not a.gui1080
    assert base['status']=='VOICE_NNUE_PREPARED_BOOT_INPUTS_UNTESTED'
    assert base['cpu_hz'] in [75000000,70000000] and base['sys_hz']==49500000
    assert base['clock_sha256']==sha(root/'config/clocks.json')
    assert base['candidate_run_id'] is None and base['candidate_bitstream_sha256'] is None
    assert base['display']=={'width':1920,'height':1080,'pixel_hz':74250000,'refresh_hz':30,'theme':'light'}
elif a.gui1080:
    assert base['status']=='GUI1080_PREPARED_BOOT_INPUTS_UNTESTED'
    assert base['candidate_run_id'] is None and base['candidate_bitstream_sha256'] is None
    assert base['display']=={'width':1920,'height':1080,'pixel_hz':148500000,'theme':'light'}
else:
    assert base['candidate_run_id']=='44aa982f752c4b7d91accea60292735f'
    assert base['candidate_bitstream_sha256']=='30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1'
assert len(base['sd_root_files'])==8
for n,item in base['sd_root_files'].items():assert sha(kit/'sd-root'/n)==item['sha256'],n
assert not out.exists();out.mkdir(parents=True)
sd=out/'sd-root';support=out/'support';evidence=out/'evidence'
for p in [sd,support,evidence]:p.mkdir()
temporary=out/'tmp';temporary.mkdir()
for n in base['sd_root_files']:shutil.copyfile(kit/'sd-root'/n,sd/n)
shutil.copyfile(kernel/'Image',sd/'Image')
assert (sd/'Image').stat().st_size<0x01000000-0x00400000,'Kernel overlaps reserved low OpenSBI range'
support_hashes={}
for p in (kit/'support').rglob('*'):
    if p.is_file() and p.suffix in ['.c','.h','.S','.ld']:
        name=p.relative_to(kit/'support');target=support/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,target);support_hashes[name.as_posix()]=sha(target)
boot=support/'bootloader'
records=[]
header='#ifndef CPU80_PAYLOADS_H\n#define CPU80_PAYLOADS_H\n#include "fat_ro.h"\n'
header+='typedef struct { const char *name; uint32_t address, bytes, crc32; fat_ro_file_t file; } payload_t;\nstatic payload_t payloads[] = {\n'
for name,address in {'fw_jump.bin':0x18000000,'Image':0x00400000,'rootfs.cpio':0x03000000,'soc.dtb':0x1a000000,'pikafish.pff':0x10000000,'pikafish.atk':0x15000000}.items():
    data=(sd/name).read_bytes();crc=zlib.crc32(data)
    header+=' {"%s",0x%08xu,%du,0x%08xu,{0}},\n'%(name,address,len(data),crc)
    records.append(dict(name=name,address=address,bytes=len(data),crc32=f'{crc:08x}',sha256=sha(sd/name)))
header+='};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n#endif\n'
(support/'payloads.h').write_text(header,encoding='ascii')
support_hashes['payloads.h']=sha(support/'payloads.h')
commands=[];tests=[]
def run(label,args,marker=None,timeout=240):
    command=['wsl.exe','-d',a.distro,'--','env','PATH=/opt/toolchain/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','TMPDIR='+wsl_path(temporary),'TMP='+wsl_path(temporary),'TEMP='+wsl_path(temporary),*map(str,args)]
    try:
        p=subprocess.run(command,capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired as error:
        (evidence/label).write_bytes((error.stdout or b'')+(error.stderr or b''))
        commands.append(dict(command=command,exit='TIMEOUT',log=label,timeout_seconds=timeout))
        raise
    data=p.stdout+p.stderr;(evidence/label).write_bytes(data)
    commands.append(dict(command=command,exit=p.returncode,log=label,log_sha256=hashlib.sha256(data).hexdigest()))
    assert p.returncode==0,(label,data[-2500:])
    if marker:assert marker.encode() in data,(label,'missing marker')
    return data

def run_native(label,args):
    env=dict(os.environ,TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary));env['PATH']=str(WORKSPACE/'workspace/tools/riscv32-gcc16/bin')+os.pathsep+env['PATH']
    p=subprocess.run(list(map(str,args)),capture_output=True,timeout=240,env=env)
    data=p.stdout+p.stderr;(evidence/label).write_bytes(data)
    commands.append(dict(command=list(map(str,args)),exit=p.returncode,log=label,log_sha256=hashlib.sha256(data).hexdigest()))
    assert p.returncode==0,(label,data[-2500:])
    return data
status='AUDIO_SERVICE_SD_BUILD_RUNNING_NOT_BOARD'
try:
    if a.local_oracle:
        oracle_root=wsl_path(out/'compile-source')
        stage=subprocess.Popen(['wsl.exe','-d',a.distro,'--','sh','-c','set -eu; mkdir '+oracle_root+'; tar -xf - -C '+oracle_root],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        compile_inputs=[p for p in support.rglob('*') if p.is_file()]
        expected_compile={p.relative_to(out).as_posix():sha(p) for p in compile_inputs}
        with tarfile.open(fileobj=stage.stdin,mode='w|') as archive:
            for p in compile_inputs:archive.add(p,arcname=p.relative_to(out).as_posix(),recursive=False)
        stage.stdin.close();stage.stdin=None
        so,se=stage.communicate(timeout=120);assert stage.returncode==0,(so+se).decode(errors='replace')
        run('local-compile-mkdir.log',['mkdir',oracle_root+'/sd-root'])
        actual=run('local-compile-hashes.log',['sha256sum',*[oracle_root+'/'+n for n in expected_compile]]).decode(errors='replace')
        actual={m[2][len(oracle_root)+1:]:m[1] for m in re.finditer(r'^([0-9a-f]{64})  (/[^\r\n]+)$',actual,re.M)}
        assert actual==expected_compile,'Local compile source differs'
        write(evidence/'local-compile-inputs.json',dict(path=oracle_root,files_sha256=expected_compile))
    def pull(p):
        if oracle_root:
            with p.open('wb') as target:
                copied=subprocess.run(['wsl.exe','-d',a.distro,'--','cat',linux(p)],stdout=target,stderr=subprocess.PIPE,timeout=60)
            assert copied.returncode==0,copied.stderr
    cc='/opt/toolchain/bin/riscv32-linux-musl-gcc';tools='/opt/toolchain/bin/riscv32-linux-musl-'
    flags=['-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-Os','-Wall','-Wextra','-Werror','-I',linux(boot),'-I',linux(support)]
    objects=[]
    for name in ['start.S','loader.c','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c']:
        p=support/name if name in ['start.S','loader.c'] else boot/name;obj=support/(p.stem+'.o')
        run('build-'+p.stem+'.log',[cc,*flags,'-c',linux(p),'-o',linux(obj)]);objects.append(linux(obj))
    elf=support/'loader.elf'
    run('link.log',[cc,'-march=rv32ima','-mabi=ilp32','-nostdlib','-static','-Wl,--gc-sections,--no-relax,--build-id=none','-T',linux(support/'link.ld'),'-Wl,-Map,'+linux(support/'loader.map'),*objects,'-lgcc','-o',linux(elf)])
    run('objcopy.log',[tools+'objcopy','-O','binary',linux(elf),linux(sd/'Image.mmode')])
    pull(elf)
    if not (a.main_frequency or a.voice_nnue or a.integrated60):pull(sd/'Image.mmode')
    if a.main_frequency or a.voice_nnue or a.integrated60:
        # The production loader uses the reviewed bare-metal GCC16 toolchain.
        # The musl objects above remain separate logic-test inputs for QEMU.
        native_tools=WORKSPACE/'workspace/tools/riscv32-gcc16/bin'
        native_cc=native_tools/'riscv32-unknown-elf-gcc.exe'
        native_objcopy=native_tools/'riscv32-unknown-elf-objcopy.exe'
        native_readelf=native_tools/'riscv32-unknown-elf-readelf.exe'
        target=run_native('native-target.log',[native_cc,'-dumpmachine']).decode().strip()
        version=run_native('native-version.log',[native_cc,'-dumpfullversion']).decode().strip()
        assert target=='riscv32-unknown-elf' and version=='16.2.0'
        assert native_cc.read_bytes()[:2]==b'MZ','Expected native Windows compiler executable'
        libgcc=Path(run_native('native-libgcc-path.log',[native_cc,'-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-print-libgcc-file-name']).decode().strip())
        native_dir=support/'native-production';native_dir.mkdir();native_objects=[]
        native_flags=['-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-Os','-Wall','-Wextra','-Werror','-I',str(boot),'-I',str(support)]
        for name in ['start.S','loader.c','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c']:
            source=support/name if name in ['start.S','loader.c'] else boot/name
            obj=native_dir/(source.stem+'.o');run_native('native-build-'+source.stem+'.log',[native_cc,*native_flags,'-c',source,'-o',obj]);native_objects.append(obj)
        native_elf=native_dir/'loader.elf'
        run_native('native-link.log',[native_cc,*native_flags[:2],'-nostdlib','-static','-Wl,--gc-sections,--no-relax,--build-id=none','-T',support/'link.ld',*native_objects,'-lgcc','-o',native_elf])
        metadata=run_native('native-elf-attributes.log',[native_readelf,'-h','-A',native_elf,libgcc]).decode(errors='replace')
        native_binary=native_elf.read_bytes()
        assert native_binary[:6]==b'\x7fELF\x01\x01' and struct.unpack_from('<I',native_binary,24)[0]==0 and struct.unpack_from('<I',native_binary,36)[0]==0
        import re
        assert all(v=='ELF32' for v in re.findall(r'Class:\s*(\S+)',metadata))
        assert all(v.strip()=='RISC-V' for v in re.findall(r'Machine:\s*([^\n]+)',metadata))
        assert all(int(v,16)==0 for v in re.findall(r'Flags:\s*(0x[0-9a-fA-F]+)',metadata))
        architectures=re.findall(r'Tag_RISCV_arch:\s*"([^"]+)"',metadata)
        assert architectures
        for arch in architectures:
            assert arch.startswith('rv32i')
            for segment in arch[4:].split('_'):
                extension=re.match('[a-z]+',segment).group()
                assert extension in ['i','m','a','zicsr','zifencei','zmmul','zaamo','zalrsc'],arch
        run_native('native-objcopy.log',[native_objcopy,'-O','binary',native_elf,sd/'Image.mmode'])
        write(support/'native-toolchain.json',dict(target=target,version=version,compiler_sha256=sha(native_cc),libgcc_sha256=sha(libgcc),elf_sha256=sha(native_elf),image_sha256=sha(sd/'Image.mmode'),scope='Production loader GCC16; musl9 separate C logic oracle, not a substituted production compiler'))
    binary=elf.read_bytes();assert binary[:5]==b'\x7fELF\x01' and struct.unpack_from('<I',binary,24)[0]==0 and not struct.unpack_from('<I',binary,36)[0]&1
    assert (sd/'Image.mmode').stat().st_size<1024*1024
    hf=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-missing-braces','-I',linux(boot),'-I',linux(support)]
    run('host-compile.log',['gcc',*hf,'-Dmain=sd80_main','-c',linux(support/'loader.c'),'-o',linux(support/'host-loader.o')])
    run('host-link.log',['gcc',*hf,linux(support/'host_test.c'),linux(support/'host-loader.o'),linux(boot/'fat_ro.c'),linux(boot/'crc32_fast.c'),'-o',linux(support/'host-test')])
    run('rv32-object.log',[tools+'objcopy','--redefine-sym','main=sd80_main',linux(support/'loader.o'),linux(support/'rv32-loader-test.o')])
    run('rv32-link.log',[cc,'-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static','-O2','-Wall','-Wextra','-Werror','-I',linux(boot),'-I',linux(support),linux(support/'host_test.c'),linux(support/'rv32-loader-test.o'),linux(boot/'fat_ro.c'),linux(boot/'crc32_fast.c'),'-o',linux(support/'rv32-test')])
    pull(support/'host-test');pull(support/'rv32-test')
    spec=importlib.util.spec_from_file_location('sd_fixture',root/'scripts/build_cpu80_conv_sd.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    disk=evidence/'test-fat32.img';locations=mod.make_fat32(disk,sorted(sd.iterdir()))
    if a.local_oracle:
        local=wsl_path(out/'oracle-source')
        stage=subprocess.Popen(['wsl.exe','-d',a.distro,'--','sh','-c','set -eu; mkdir '+local+'; tar -xf - -C '+local],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        # Copy only immutable inputs used by the two compiled loader oracles.
        inputs=[*sorted(sd.iterdir()),disk,support/'host-test',support/'rv32-test']
        expected={p.relative_to(out).as_posix():sha(p) for p in inputs}
        with tarfile.open(fileobj=stage.stdin,mode='w|') as archive:
            for p in inputs:archive.add(p,arcname=p.relative_to(out).as_posix(),recursive=False)
        stage.stdin.close();stage.stdin=None
        so,se=stage.communicate(timeout=120);assert stage.returncode==0,(so+se).decode(errors='replace')
        oracle_root=local
        actual=run('local-oracle-hashes.log',['sha256sum',*[local+'/'+n for n in expected]]).decode(errors='replace')
        actual={m[2][len(local)+1:]:m[1] for m in re.finditer(r'^([0-9a-f]{64})  (/[^\r\n]+)$',actual,re.M)}
        assert actual==expected,'Local loader oracle input differs'
        run('local-oracle-executable.log',['chmod','755',linux(support/'host-test'),linux(support/'rv32-test')])
        write(evidence/'local-oracle-inputs.json',dict(path=local,files_sha256=expected))
    def test(scenario,label=None):
        for prefix,runner,tag in [([],support/'host-test',''),(['qemu-riscv32'],support/'rv32-test','rv32-')]:
            name=tag+(label or 'test-'+scenario+'.log')
            run(name,[*prefix,linux(runner),scenario,linux(disk),linux(sd)],'HOST_TEST_PASS '+scenario);tests.append(name)
    for scenario in ['pass','clock','init','io','abort']:test(scenario)
    def mutate(offset,value,label):
        with disk.open('r+b') as f:f.seek(offset);old=f.read(len(value));f.seek(offset);f.write(value)
        def local_write(data,suffix):
            if oracle_root:
                run('local-'+label+'-'+suffix+'.log',['python3','-c','import sys; f=open(sys.argv[1],"r+b"); f.seek(int(sys.argv[2])); f.write(bytes.fromhex(sys.argv[3])); f.close()',linux(disk),str(offset),data.hex()])
        try:
            local_write(value,'mutate');test('reject','test-'+label+'.log')
        finally:
            with disk.open('r+b') as f:f.seek(offset);f.write(old)
            local_write(old,'restore')
    mutate(locations['Image']['data']+100,b'\xff','corrupt-kernel')
    mutate(locations['pikafish.pff']['directory'],b'\xe5','missing-model')
    mutate(locations['fw_jump.bin']['directory']+28,struct.pack('<I',1),'bad-firmware-size')
    mutate(510,b'\0\0','bad-fat-signature')
    assert len(tests)==18
    for n,item in base['sd_root_files'].items():
        if n not in ['Image','Image.mmode']:assert sha(sd/n)==item['sha256'],n
    assert sha(kernel/'Image')==sha(sd/'Image')
    status='MAIN_FREQUENCY_RUNTIME_18_OFFLINE_TESTS_PASS_BOARD_PENDING' if a.main_frequency else 'INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' if a.integrated60 else 'VOICE_NNUE_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' if a.voice_nnue else 'GUI1080_CPU80_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' if a.gui1080 else 'AUDIO_SERVICE_SD_18_OFFLINE_TESTS_PASS_BOARD_PENDING'
    files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(sd.iterdir())}
    manifest={k:v for k,v in base.items() if k not in ['commands','tests','sd_root_files','payloads','inputs_sha256','created_utc','status']}
    manifest.update(status=status,created_utc=datetime.now(timezone.utc).isoformat(),payloads=records,sd_root_files=files,tests=tests,commands=commands,
                    kernel_build_receipt_sha256=sha(kernel/'build.json'),base_manifest_sha256=sha(kit/'manifest.json'),support_sources_sha256=support_hashes,
                    binding_scope=('Merged-main CPU75/SYS49.5 source-bound offline SD candidate; no inherited real-board acceptance.' if a.main_frequency else 'CPU60/SYS49.5/1080p30, voice2 and original Picture_new model timing candidate. New runtime/SD/board acceptance separate; not formal delivery.' if a.integrated60 else 'New CPU75/70 voice/direct NNUE1080p30 runtime. Native FPGA and real board acceptance remain pending.' if a.voice_nnue else 'New1080p runtime; hardware run and bitstream deliberately unbound until new native STA passes. No inherited720p board pass.' if a.gui1080 else 'Same repaired44aa982f hardware and six unchanged SD files. New kernel and corresponding loader CRC only; all hardware and new software board acceptance remain separate.'),
                    board_tested=False,physical_media_written=False,flash_written=False,remote_pushed=False)
    write(out/'manifest.json',manifest)
    write(out/'software-build.json',dict(status=status,tests=tests,commands=commands,board_tested=False))
    (sd/'SHA256SUMS.txt').write_text(''.join(v['sha256']+'  '+n+'\n' for n,v in files.items()),encoding='ascii')
except Exception:
    status='FAILED_PRESERVED_AUDIO_SERVICE_SD_NOT_PROMOTED'
    raise
finally:
    write(out/'assembly.json',dict(status=status,commands=commands,tests=tests,base_kit=str(kit),kernel=str(kernel),board_tested=False))
    print(status,flush=True)
