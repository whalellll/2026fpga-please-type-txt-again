"""Prepare the existing merged-main runtime for its exact CPU70 hardware."""
from pathlib import Path
import argparse,hashlib,json,shutil,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from workspace_paths import workspace_path,wsl_path
from build_cpu80_conv_sd import cpio_entries,fdt_properties
from prepare_voice_nnue_boot import entry
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def records(blob):
    rows={}
    for row in cpio_entries(blob):
        name=row['name'].removeprefix('./');assert name not in rows
        at=(row['start']+110+row['fields'][11]+3)&~3
        rows[name]=(row,blob[at:at+row['bytes']])
    return rows

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['native-result','base-kit','kernel','firmware','product','output']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--program-receipt',type=Path,help='Optional real PASS CRAM assignment evidence; never fabricate a current-image hash')
    ap.add_argument('--software-source',type=Path,help='Source freeze containing exactly the compiled GUI inputs')
    a=ap.parse_args();native=read(a.native_result);source=Path(native['bitstream']).parent.parent
    assert native['status']=='MERGED_MAIN_CPU70_SYNTHESIS_ROUTE_FINAL_ALL_CORNER_STA_AND_HASH_READBACK_PASS_NOT_BOARD'
    assert sha(Path(native['bitstream']))==native['bitstream_sha256']
    snap=read(source/'pds/build_snapshot.json')
    assert all(sha(source/n)==h for n,h in snap['inputs'].items())
    cfg=read(source/'config/clocks.json');assert cfg['cpu_hz']==70000000 and cfg['sys_hz']==49500000
    base=read(a.base_kit/'manifest.json');kernel=read(a.kernel/'build.json');firmware=read(a.firmware/'result.json')
    assert base['cpu_hz']==60000000 and base['sbi_ratio']==[33,40]
    names={'Image','Image.mmode','fw_jump.bin','rootfs.cpio','soc.dtb','mmode.dtb','pikafish.pff','pikafish.atk'}
    assert set(base['sd_root_files'])==names
    for n,v in base['sd_root_files'].items():assert sha(a.base_kit/'sd-root'/n)==v['sha256'],n
    assert kernel['status']=='ACCUM_RESIDENT_KERNEL_BUILD_PASS_NOT_BOARD' and not kernel['bulk_word_io']
    assert sha(a.kernel/'Image')==kernel['outputs_sha256']['Image']==base['sd_root_files']['Image']['sha256']
    integration={}
    for name,h in kernel['inputs_sha256'].items():
        p=Path(name);assert sha(p)==h,name
        if p.is_relative_to(ROOT) and p.suffix in ['.c','.h','.patch']:
            rel=p.relative_to(ROOT).as_posix();assert sha(source/rel)==h,rel;integration[rel]=h
    assert len(integration)>=8
    assert firmware['status']=='CPU70_SD_OPENSBI_99_140_BUILD_PASS_NOT_BOARD' and firmware['ratio']==[99,140]
    for n,h in firmware['outputs_sha256'].items():assert sha(a.firmware/n)==h,n
    product=a.product/'xinyi-one-stripped'
    assert (a.product/'cpu-hz.txt').read_text().strip()=='70000000'
    assert (a.product/'source-before.sha256').read_bytes()==(a.product/'source-after.sha256').read_bytes()
    for line in (a.product/'source-before.sha256').read_text().splitlines():
        h,p=line.split(None,1);p=p.strip();assert p.startswith('/mnt/g/fpga/');p=Path('G:/fpga')/Path(p).relative_to('/mnt/g/fpga');assert sha(p)==h,str(p)
        if a.software_source:assert p.is_relative_to(a.software_source.resolve()),'GUI compiled from another source freeze'
    assert product.read_bytes()[:6]==b'\x7fELF\x01\x01'
    proof=None
    if a.program_receipt:
        proof=read(a.program_receipt)
        assert proof['status']=='PASS' and proof['evidence_kind']=='volatile_cram_program' and proof['operation']=='CRAM'
        assert proof['bitstream_sha256']==native['bitstream_sha256'] and proof['device_id']=='0x00602899' and proof['device_count']==1
        assert proof['run_id']==native['native_run'] and proof['source_ref']==native['source_commit']
        assert proof['program_log_sha256'] and proof['preflight_log_sha256']
    out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    sd=out/'sd-root';support=out/'support';sd.mkdir();support.mkdir()
    for n in names:shutil.copyfile(a.base_kit/'sd-root'/n,sd/n)
    for p in (a.base_kit/'support').rglob('*'):
        if p.is_file() and p.suffix in ['.c','.h','.S','.ld']:
            target=support/p.relative_to(a.base_kit/'support');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    for n in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h']:
        shutil.copyfile(source/'sw/bootloader'/n,support/'bootloader'/n)
    loader=(support/'loader.c').read_text()
    assert loader.count('!= 60000000u')==1 and 'ratio=33/40' in loader
    loader=loader.replace('!= 60000000u','!= 70000000u').replace('VOICE_NNUE_SD_','MAIN70_SD_').replace('cpu=60000000 sys=49500000 ratio=33/40','cpu=70000000 sys=49500000 ratio=99/140')
    (support/'loader.c').write_text(loader,newline='\n')
    host=(support/'host_test.c').read_text();assert '?59000000u:60000000u' in host
    (support/'host_test.c').write_text(host.replace('?59000000u:60000000u','?69000000u:70000000u'),newline='\n')
    blob=(sd/'rootfs.cpio').read_bytes();before=records(blob);changed={};added={}
    assert hashlib.sha256(before['usr/bin/xq-coach-worker'][1]).hexdigest()=='1953b37d6511e21fe5eb0675dbee7285a1e06b42b3b43e60cd8edda0c6220de3'
    changed['usr/bin/xinyi-one']=product.read_bytes()
    launch=before['usr/bin/start-main-xinyi'][1].decode()
    old='test -f /run/main-current-cram.sha256 || { echo MAIN_CURRENT_CRAM_RECEIPT_REQUIRED; exit 1; }\ntest "$(cat /run/main-current-cram.sha256)" = 5e95b98fe743c139afdf3e45f95335a0c0cc3c5414b647ea0843d0360ddaaf5e'
    assert old in launch
    replacement='''receipt=/etc/main-current-cram.sha256
test -f "$receipt" || receipt=/run/main-current-cram.sha256
if test -f "$receipt"; then
 test "$(cat "$receipt")" = '''+native['bitstream_sha256']+'''
 export XINYI_CURRENT_CRAM_SHA256=$(cat "$receipt")
else
 unset XINYI_CURRENT_CRAM_SHA256
 echo MAIN70_GUI_COREMARK_UNAVAILABLE_WITHOUT_OBSERVED_CRAM_ASSIGNMENT
fi'''
    launch=launch.replace(old,replacement).replace('export XINYI_CURRENT_CRAM_SHA256=$(cat /run/main-current-cram.sha256)\n','')
    assert launch.count('. /etc/pikafish-batch.env\n')==1
    launch=launch.replace('. /etc/pikafish-batch.env\n',
        '. /etc/pikafish-batch.env\n'
        'export PIKAFISH_EMBEDDED_MODEL=pff1-view:0x10000000:68122688\n'
        'export PIKAFISH_STAGEB_PACK=/opt/pikafish/stageb-mac.bin\n'
        'test -r "$PIKAFISH_STAGEB_PACK"\n')
    changed['usr/bin/start-main-xinyi']=launch.encode()
    changed['etc/init.d/S95pikafish']=b'''#!/bin/sh
set -eu
[ "${1:-}" = start ] || exit 0
mkdir -p /run
/usr/bin/start-main-xinyi </dev/null >/run/main-xinyi.log 2>&1 &
echo $! >/run/main-xinyi.pid
echo MAIN70_GUI_START_REQUESTED cpu=70000000 sys=49500000 >/dev/console
'''
    build=json.loads(before['etc/pikafish-sw-build.json'][1])
    build.update(cpu_hz=70000000,sys_hz=49500000,tested_head=native['source_commit'],hardware_bitstream_sha256=native['bitstream_sha256'],hardware_run=native['native_run'],board_tested=False,scope='CPU70 source-matched SD candidate; PN07 worker reused with prior explicit authorization; no inherited CPU60 acceptance')
    if a.software_source:
        build['software_source_commit']=subprocess.check_output(['git','-C',str(a.software_source),'rev-parse','HEAD'],text=True).strip()
        build['hardware_implementation_commit']=native['source_commit']
        build['gui_source_inventory_sha256']=sha(a.product/'source-before.sha256')
    changed['etc/pikafish-sw-build.json']=(json.dumps(build,indent=2)+'\n').encode()
    if proof:
        added['etc/main-programming.json']=(a.program_receipt.read_bytes(),0o100644)
        added['etc/main-current-cram.sha256']=((native['bitstream_sha256']+'\n').encode(),0o100644)
    runtime={}
    for line in before['opt/main-xinyi/runtime.sha256'][1].decode().splitlines():
        h,n=line.split(None,1);runtime[n.strip().lstrip('/')]=h
    for n,data in changed.items():
        if n in runtime:runtime[n]=hashlib.sha256(data).hexdigest()
    changed['opt/main-xinyi/runtime.sha256']=(''.join(h+'  /'+n+'\n' for n,h in runtime.items())).encode()
    result=bytearray()
    for n,(row,data) in before.items():
        if n=='TRAILER!!!':continue
        if n in changed:
            f=list(row['fields']);f[6]=len(changed[n]);name=row['name'].encode()+b'\0'
            raw=b'070701'+b''.join(f'{v:08x}'.encode() for v in f)+name
            raw+=b'\0'*(-len(raw)%4);raw+=changed[n];raw+=b'\0'*(-len(raw)%4);result+=raw
        else:result+=blob[row['start']:row['end']]
    for n,(data,mode) in added.items():assert n not in before;result+=entry(n,data,mode)
    result+=entry('TRAILER!!!',b'',0);result+=b'\0'*(-len(result)%512)
    assert len(result)<0x02000000
    final=records(result)
    for n,(row,data) in before.items():
        if n not in changed and n!='TRAILER!!!':assert final[n][1]==data,n
    for n,data in changed.items():assert final[n][1]==data,n
    (sd/'rootfs.cpio').write_bytes(result)
    for n in ['soc.dtb','mmode.dtb']:
        dtb=bytearray((sd/n).read_bytes());props=fdt_properties(dtb)
        for key in ['/cpus/timebase-frequency','/cpus/cpu@0/clock-frequency']:
            at,size=props[key];assert size==4;struct.pack_into('>I',dtb,at,70000000)
        at,size=props['/chosen/linux,initrd-end'];assert size==4;struct.pack_into('>I',dtb,at,0x03000000+len(result));(sd/n).write_bytes(dtb)
    assert (sd/'soc.dtb').read_bytes()==(sd/'mmode.dtb').read_bytes()
    shutil.copyfile(a.firmware/'fw_jump.bin',sd/'fw_jump.bin')
    base.update(status='MAIN_FREQUENCY_PREPARED_BOOT_INPUTS_UNTESTED',cpu_hz=70000000,sys_hz=49500000,sbi_ratio=[99,140],clock_sha256=sha(source/'config/clocks.json'),candidate_run_id=native['native_run'],candidate_bitstream_sha256=native['bitstream_sha256'],loader_prefix='MAIN70',rootfs_bytes=len(result),board_tested=False,physical_media_written=False,formal_delivery=False,
                kernel_reuse=dict(status='IDENTICAL_KERNEL_INTEGRATION_SOURCES_FREQUENCY_FROM_DTB',original_build_receipt_sha256=sha(a.kernel/'build.json'),source_sha256=integration),
                gui_coremark_has_observed_program_receipt=bool(proof),changed_archive_paths=sorted(changed),unchanged_archive_payloads_verified=True,
                integrated_main=build,parent_kit_manifest_sha256=sha(a.base_kit/'manifest.json'),
                program_assignment_receipt_sha256=sha(a.program_receipt) if proof else None,
                runtime_sha256={n:hashlib.sha256(final[n][1]).hexdigest() for n in base['runtime_sha256']},
                sd_root_files={n:dict(bytes=(sd/n).stat().st_size,sha256=sha(sd/n)) for n in names})
    (out/'manifest.json').write_text(json.dumps(base,indent=2)+'\n')
    print('MAIN70_SD_INPUTS_PREPARED_NOT_WRITTEN_NOT_BOARD')

if __name__=='__main__':main()
