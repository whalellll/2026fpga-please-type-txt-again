"""Prepare paired optimization software and A/B tools offline; no media access."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, struct, subprocess, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from build_cpu80_conv_sd import cpio_entries, fdt_properties, wsl_path
from prepare_voice_nnue_boot import entry
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def verified_binary(folder,name,key='binary_sha256'):
    receipt=read(folder/'result.json');p=folder/name
    expected=receipt[key] if key=='binary_sha256' else receipt[key][name]
    assert sha(p)==expected,(folder,name)
    for rel,h in receipt.get('inputs_sha256',receipt.get('sources_sha256',{})).items():
        root=Path(receipt.get('source_root',ROOT));source=Path(rel);source=source if source.is_absolute() else root/source
        assert sha(source)==h,source
    return p

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['engine','voice','voice-profile','voice-before-profile','bench','output']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sd=out/'sd-root';support=out/'support';sd.mkdir();support.mkdir()
    stored=ROOT/'artifacts/integrated60_linefix_trial_20261024/sd-inputs';base=read(stored/'input-map.json')
    for name,row in base['files'].items():
        source=ROOT/row['source'];assert sha(source)==row['sha256'];shutil.copyfile(source,sd/name)
    original=(sd/'rootfs.cpio').read_bytes();rows=cpio_entries(original)
    effective={r['name'].removeprefix('./'):r for r in rows if r['name']!='TRAILER!!!'}
    assert len(effective)==len(rows)-1
    replacements={}
    for name,target in [('pikafish-rv32','pikafish'),('pikafish-pipeline-search','pikafish-pipeline-search'),
                        ('xiangqi-pikafish-gui-display','xiangqi-pikafish-gui'),('pikafish-nnue-pipeline-latency','pikafish-nnue-latency-clint')]:
        replacements['usr/bin/'+target]=verified_binary(a.engine,name,'artifacts_sha256')
    replacements['usr/bin/xqvoice-small-cnn']=verified_binary(a.voice,'xqvoice-small-cnn')
    replacements['usr/bin/xqvoice-small-cnn-profile']=verified_binary(a.voice_profile,'xqvoice-small-cnn')
    replacements['usr/bin/xqvoice-small-cnn-before-profile']=verified_binary(a.voice_before_profile,'xqvoice-small-cnn')
    replacements['usr/bin/picture-new-bench']=verified_binary(a.bench,'picture-new-bench','outputs_sha256')
    generated={name:entry(name,path.read_bytes(),0o100755) for name,path in replacements.items()}
    runtime_hashes={name:sha(path) for name,path in replacements.items()}
    for path in ['usr/bin/xqvoice-small-cnn','usr/bin/picture-new-bench','usr/bin/pikafish-nnue-latency-clint']:
        row=effective[path];start=row['end']-((row['bytes']+3)&~3);content=original[start:start+row['bytes']]
        assert hashlib.sha256(content).hexdigest()==row['sha256']
        generated[path+'-before']=entry(path+'-before',content,0o100755);runtime_hashes[path+'-before']=row['sha256']
    cap=support/'pikafish-batch-check'
    subprocess.run(['wsl','-d','pikafish-verify','--','/opt/toolchain/bin/riscv32-linux-musl-gcc','-static','-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-Os','-Wall','-Wextra','-Werror','-I',wsl_path(ROOT/'linux/mac_accel'),wsl_path(ROOT/'linux/mac_accel/pango_mac_batch_check.c'),'-o',wsl_path(cap)],check=True,timeout=90)
    generated['usr/bin/pikafish-batch-check']=entry('usr/bin/pikafish-batch-check',cap.read_bytes(),0o100755)
    runtime_hashes['usr/bin/pikafish-batch-check']=sha(cap)
    env=b'export PIKAFISH_MAC_REQUIRE_DRIVER=1 PIKAFISH_STAGEA_ACCEL=1 PIKAFISH_STAGEB_ACCEL=1 PIKAFISH_NNUE_PIPELINE=1\nexport PIKAFISH_NNUE_BATCH=${PIKAFISH_NNUE_BATCH:-1}\n'
    generated['etc/pikafish-batch.env']=entry('etc/pikafish-batch.env',env,0o100644)
    gui=b'#!/bin/sh\nset -eu\n. /etc/pikafish-batch.env\n/usr/bin/pikafish-batch-check\ncd /tmp\nexec /usr/bin/xiangqi-pikafish-gui\n'
    generated['usr/bin/start-integrated60-gui']=entry('usr/bin/start-integrated60-gui',gui,0o100755)
    runtime_hashes['etc/pikafish-batch.env']=hashlib.sha256(env).hexdigest()
    runtime_hashes['usr/bin/start-integrated60-gui']=hashlib.sha256(gui).hexdigest()
    # Preserve startup in benchmark mode, with no unsolicited GUI/device owner.
    assert b'INTEGRATED60_BENCH_READY' in original
    chunks=[]
    for name,row in effective.items():chunks.append(generated.pop(name,original[row['start']:row['end']]))
    chunks+=list(generated.values())+[entry('TRAILER!!!',b'',0)]
    rootfs=b''.join(chunks);rootfs+=b'\0'*((-len(rootfs))%512)
    assert len(rootfs)<0x02000000,'Rootfs exceeds paired CPU60 memory reservation'
    parsed=cpio_entries(rootfs);names={r['name'].removeprefix('./'):r for r in parsed}
    for name,h in runtime_hashes.items():assert names[name]['sha256']==h,name
    (sd/'rootfs.cpio').write_bytes(rootfs)
    dts=(ROOT/'linux/soc.dts').read_text(encoding='utf-8-sig')
    dts,count=re.subn(r'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>',f'linux,initrd-end = <0x{0x03000000+len(rootfs):08x}>',dts);assert count==1
    (support/'soc.dts').write_text(dts,encoding='utf-8',newline='\n')
    subprocess.run(['wsl','-d','pikafish-verify','--','dtc','-I','dts','-O','dtb','-o',wsl_path(sd/'soc.dtb'),wsl_path(support/'soc.dts')],check=True,timeout=60)
    shutil.copyfile(sd/'soc.dtb',sd/'mmode.dtb')
    blob=(sd/'soc.dtb').read_bytes();props=fdt_properties(blob)
    get=lambda key:struct.unpack_from('>I',blob,props[key][0])[0]
    assert get('/cpus/timebase-frequency')==get('/cpus/cpu@0/clock-frequency')==60000000
    assert get('/chosen/linux,initrd-end')==0x03000000+len(rootfs)
    boot=support/'bootloader';boot.mkdir()
    for name in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h']:shutil.copyfile(ROOT/'sw/bootloader'/name,boot/name)
    loader=(ROOT/'scripts/cpu80_sd/loader.c').read_text().replace('!= 80000000u','!= 60000000u').replace('CPU80_SD_','VOICE_NNUE_SD_').replace('cpu=80000000 sys=49500000 ratio=99/160','cpu=60000000 sys=49500000 ratio=33/40')
    (support/'loader.c').write_text(loader,newline='\n')
    (support/'host_test.c').write_text((ROOT/'scripts/cpu80_sd/host_test.c').read_text().replace('?75000000u:80000000u','?59000000u:60000000u'),newline='\n')
    shutil.copyfile(ROOT/'linux/boot/v2_1_sd/source/start.S',support/'start.S')
    (support/'link.ld').write_text((ROOT/'linux/boot/v2_1_sd/source/link.ld').read_text().replace('ORIGIN = 0x01000000','ORIGIN = 0x00000000'),newline='\n')
    record=dict(status='INTEGRATED60_PREPARED_BOOT_INPUTS_UNTESTED',optimization_candidate=True,
                cpu_hz=60000000,sys_hz=49500000,sbi_ratio=[33,40],
                display=dict(width=1920,height=1080,pixel_hz=74250000,refresh_hz=30,theme='light'),
                clock_sha256=sha(ROOT/'config/clocks.json'),candidate_run_id=None,candidate_bitstream_sha256=None,
                original_picture_weights=True,voice_stream_enabled=True,voice_quant_enabled=True,
                runtime_sha256=runtime_hashes,base_rootfs_sha256=base['files']['rootfs.cpio']['sha256'],rootfs_bytes=len(rootfs),
                sd_root_files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sd.iterdir()},
                physical_media_written=False,board_tested=False,formal_delivery=False)
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(status=record['status'],rootfs_bytes=len(rootfs))))
if __name__=='__main__':main()
