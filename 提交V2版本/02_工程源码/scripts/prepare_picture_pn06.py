"""Bind a private e42 kernel/HWC/NNUE startup to four unchanged PN04 files.

Creates six PN06 files plus a create-only installer. Never accesses media,
JTAG, Flash, selectors, photos or datasets. PN05/P3 remains a separate rollback.
"""
from pathlib import Path
import argparse
import gzip
import json
import struct
import subprocess
import zlib
from picture_workspace import ROOT, workspace_path
from prepare_xinyi_cpu60_kit import identity, require, cpio_read, cpio_write, elf32, coach_binding, P3_TARGET
from prepare_xinyi_pn05_overlay import BASE_MANIFEST
from prepare_picture_candidate import tokens
from verify_xinyi_elf import inspect
from check_published_e42 import check, IMAGE, PUB

MAIN = 'e7288be9e49f348b37832a65415b6989c444384c'
XQI = 'd72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prefix',choices=['PN06','PN07','PN08'],default='PN06')
    ap.add_argument('--geometry-proof',type=Path)
    ap.add_argument('--numeric-proof',type=Path)
    for name in ['output', 'coach-proof', 'product-stack', 'kernel', 'xqi']:
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--base', type=Path, default=ROOT/'build/xinyi-offline-20261025/boot-p3-pn04-r02')
    a = ap.parse_args()
    sd_prefix=a.prefix
    def card(suffix):return sd_prefix+suffix
    logical = a.output.absolute()
    require(logical.is_relative_to(ROOT/'build'), 'Use an owned build directory')
    out = workspace_path(logical)
    require(not out.exists(), 'Fresh candidate required')
    out.mkdir(parents=True)
    inputs, commands = {}, []

    def read(path):
        path = Path(path).resolve();data = path.read_bytes();inputs[str(path)] = identity(data)
        return data

    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)

    def record(path, value):
        save(path, (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode())

    def run(name, argv):
        r = subprocess.run(list(map(str, argv)), cwd=ROOT, capture_output=True, timeout=240)
        save(out/'evidence'/(name+'.log'), r.stdout+r.stderr)
        commands.append({'name': name, 'exit': r.returncode, 'log': identity(r.stdout+r.stderr)})
        require(r.returncode==0, name+': '+(r.stdout+r.stderr).decode(errors='replace')[-2200:])

    for path in [__file__, ROOT/'scripts/prepare_xinyi_cpu60_kit.py',
                 ROOT/'scripts/prepare_xinyi_pn05_overlay.py', ROOT/'scripts/prepare_picture_candidate.py',
                 ROOT/'scripts/picture_workspace.py', ROOT/'scripts/check_published_e42.py',
                 ROOT/'scripts/build_xinyi_cpu60_loader.ps1', ROOT/'scripts/build_xinyi_sd_install.ps1',
                 ROOT/'scripts/riscv_toolchain.ps1', ROOT/'scripts/verify_xinyi_elf.py']:
        read(path)
    hardware = check(ROOT, ROOT/PUB/'soc_top.sbit', out/'hardware-audit')
    record(out/'hardware-audit.json', hardware)
    base = json.loads(read(a.base/'manifest.json'))
    require(identity((a.base/'manifest.json').read_bytes())['sha256']==BASE_MANIFEST and
            base['target_bitstream_sha256']==P3_TARGET, 'Exact PN04 base required')
    originals = {name: read(a.base/'payloads'/name) for name in base['files']}
    require(all(identity(data)==base['files'][name] for name,data in originals.items()), 'Base identity mismatch')
    kernel_proof = json.loads(read(a.kernel/'result.json'))
    if sd_prefix=='PN08':
        require(kernel_proof['status']=='E42_BULK_IO32_INCREMENTAL_KERNEL_BUILD_PASS_NOT_BOARD' and
            all(kernel_proof.get(k) is True for k in ['source_stable','word_only_aperture','bounded_copy_barriers',
                'unaligned_normal_ram_preserved','old_tree_unchanged']) and not kernel_proof['hardware_used'] and
            kernel_proof['base_kernel_sha256']=='63f653feae8323a1512a3f9fb38fb485c75d4b81e45c6f786675861da94618db',
            'PN08 requires the separately tested bulk word-I/O kernel')
        kernel_inputs=kernel_proof['source_inputs_sha256']
        require(a.geometry_proof and a.numeric_proof,'PN08 geometry and arithmetic proofs required')
        geometry=json.loads(read(a.geometry_proof));numeric=json.loads(read(a.numeric_proof))
        require(geometry['status']=='GEOMETRY_ARITH_BIT_EQUAL_HOST_RV32_PASS_NOT_BOARD' and
            geometry['source_stable'] and geometry['all_guards_qr_ransac_unchanged_source'] and
            all(t['synthetic_integral_refinement_statistics_bit_equal'] for t in geometry['targets'].values()) and
            set(geometry['targets'])=={'host','qemu'},'PN08 exact geometry comparison required')
        require(numeric['status']=='GEOMETRY_EXACT_DIV_ADD_MASK_HOST_RV32_ASAN_UBSAN_PASS_NOT_BOARD' and
            {t['target'] for t in numeric['checks']}=={'host','rv32','sanitizer'},'PN08 exact arithmetic checks required')
        for evidence in [geometry,numeric]:
            for path,digest in evidence['source_sha256'].items():
                require(identity(read(ROOT/path))['sha256']==digest,'Geometry evidence source changed: '+path)
    else:
        require(kernel_proof['status']=='E42_PRIVATE_KERNEL_BUILD_PASS_NOT_BOARD' and
                kernel_proof['current_driver_word_io32_preserved'] and not kernel_proof['hardware_used'], 'Kernel binding required')
        kernel_inputs=kernel_proof['inputs_sha256']
    for path, digest in kernel_inputs.items():
        require(identity(read(path))['sha256']==digest, 'Kernel input changed: '+path)
    kernel = read(a.kernel/'Image')
    require(identity(kernel)['sha256']==kernel_proof['outputs_sha256']['Image'] and
            len(kernel)<=0x800000, 'Kernel binding/staging bound failed')
    config = read(a.kernel/'kernel.config')
    require(all((name+'=y\n').encode() in config for name in
                ['CONFIG_PANGO_MAC_ACCEL','CONFIG_PANGO_AUDIO_CAPTURE','CONFIG_PANGO_VOICE_ACCEL',
                 'CONFIG_BLK_DEV_INITRD','CONFIG_RD_GZIP']), 'Matching kernel/initramfs config required')
    stack = json.loads(read(a.product_stack/'result.json'))
    require(stack['status']=='E42_GUI_STRICT_NNUE_FULL_REBUILD_PASS_NOT_BOARD' and stack['source_stable'], 'Rebuilt stack proof required')
    for name,digest in stack['source_sha256'].items():
        require(identity(read(ROOT/name))['sha256']==digest, 'Stack source changed: '+name)
    gui_dir = a.product_stack/'product'
    before,after = read(gui_dir/'source-before.sha256'),read(gui_dir/'source-after.sha256')
    require(before==after, 'GUI source instability')
    source_prefix = '/mnt/'+ROOT.drive[0].lower()+ROOT.as_posix()[2:]+'/'
    for line in before.decode().splitlines():
        digest,path = line.split(maxsplit=1)
        require(path.startswith(source_prefix) and identity(read(ROOT/path[len(source_prefix):]))['sha256']==digest, 'Stale GUI source')
    product = read(gui_dir/'xinyi-one-stripped');elf32(product,'PN06 GUI')
    require(inspect(gui_dir/'xinyi-one-stripped')['allocated']==inspect(gui_dir/'xinyi-one')['allocated'], 'Invalid GUI strip')
    engine = read(a.product_stack/'engine/xinyi-engine');elf32(engine,'PN06 engine')
    for name,data in [('product/xinyi-one-stripped',product),('engine/xinyi-engine',engine)]:
        require(identity(data)['sha256']==stack['outputs_sha256'][name], 'Stack binary changed')
    engine_dir = a.product_stack/'engine'
    require(read(engine_dir/'source-before.sha256')==read(engine_dir/'source-after.sha256'), 'Engine source instability')
    # Bind Linux-native private compile inputs as well as local ports.
    run('engine-input-recheck', ['wsl.exe','-d','Ubuntu-22.04','--','sha256sum','-c',
         '/mnt/'+engine_dir.resolve().drive[0].lower()+engine_dir.resolve().as_posix()[2:]+'/source-before.sha256'])
    proof = json.loads(read(a.coach_proof))
    require(proof.get('detector_hwc_candidate') is True and
            proof.get('hwc_cpu_reference_rejected_before_output') is True, 'Explicit HWC/lifecycle proof required')
    worker = read(a.coach_proof.parent/'worker-coach-qemu/xq-coach-worker');elf32(worker,'PN06 coach')
    contract = coach_binding(worker,proof)
    configuration=dict(line.split('=',1) for line in read(a.coach_proof.parent/'worker-coach-qemu/runtime-config.txt').decode().splitlines())
    if sd_prefix in ('PN07','PN08'):
        require(proof.get('grid_recovery_candidate') is True and proof.get('exact_fp32_bilinear_candidate') is True,
                'PN07 requires validated grid and exact FP32 bilinear selection')
        for key,value in {'detector_hwc_candidate':'1','exact_epilogue':'1','geometry_gray_table':'1',
                'geometry_row_local':'0','grid_recovery_candidate':'1','exact_fp32_bilinear_candidate':'1',
                'hwc_rgb_quant_candidate':'0','graph_profile':'0'}.items():
            require(configuration.get(key)==value,'Unexpected '+sd_prefix+' software option: '+key)
    if sd_prefix=='PN08':
        require(proof.get('geometry_fast_candidate') is True and proof.get('geometry_arith_candidate') is True,
                'PN08 exact geometry selection/lifecycle proof required')
        for key,value in {'geometry_fast':'1','geometry_arith':'1','geometry_add':'0'}.items():
            require(configuration.get(key)==value,'Unexpected PN08 geometry option: '+key)
    for name in proof['sources_sha256']:read(ROOT/name)
    xqi = read(a.xqi);require(identity(xqi)['sha256']==XQI, 'Frozen derived XQI required')
    rows = cpio_read(originals['PN04FS.BIN'])
    changes = {}

    def replace(name,data):
        if name in rows:
            fields = rows[name][0].copy();require(fields[4]==1, 'No hard-link replacement: '+name)
        else:
            fields = [max(r[0][0] for r in rows.values())+1,0o100644,0,0,1,0,0,0,0,0,0,0,0]
        changes[name] = fields,data

    replace('usr/bin/xinyi-one',product)
    replace('usr/bin/xq-coach-worker',worker)
    replace('usr/bin/xinyi-engine',engine)
    replace('opt/xinyi/detector.xqi.gz',gzip.compress(xqi,compresslevel=9,mtime=0))
    model_sums = rows['opt/xinyi/models.sha256'][1]
    require(b'detector.xqi' not in model_sums, 'Unexpected preexisting XQI')
    replace('opt/xinyi/models.sha256', model_sums+(XQI+'  /run/xinyi-models/detector.xqi\n').encode())
    launcher = rows['usr/bin/start-xinyi'][1]
    require(launcher.count(P3_TARGET.encode())==1, 'Unexpected startup identity')
    launcher = launcher.replace(P3_TARGET.encode(),IMAGE.encode())
    marker = b'sha256sum -c /opt/xinyi/models.sha256'
    require(launcher.count(marker)==1, 'Unexpected model verification entry')
    extract = (b'if test ! -f /run/xinyi-models/detector.xqi; then\n'
               b' gzip -dc /opt/xinyi/detector.xqi.gz >/run/xinyi-models/detector.xqi.part\n'
               b' mv /run/xinyi-models/detector.xqi.part /run/xinyi-models/detector.xqi\nfi\n')
    replace('usr/bin/start-xinyi',launcher.replace(marker,extract+marker))
    sums = []
    for line in rows['opt/xinyi/runtime.sha256'][1].decode().splitlines():
        digest,path = line.split('  ',1);name = path.lstrip('/')
        if name in changes:digest = identity(changes[name][1])['sha256']
        sums.append(digest+'  '+path)
    sums.append(identity(changes['opt/xinyi/detector.xqi.gz'][1])['sha256']+'  /opt/xinyi/detector.xqi.gz')
    replace('opt/xinyi/runtime.sha256',('\n'.join(sums)+'\n').encode())
    expected_changes = set(changes)
    for name in list(changes):
        for parent in Path(name).parents:
            key = parent.as_posix()
            if key!='.' and key in rows:changes.setdefault(key,(rows[key][0].copy(),rows[key][1]))
    overlay = gzip.compress(cpio_write(changes),compresslevel=9,mtime=0)
    merged = dict(rows);merged.update(cpio_read(gzip.decompress(overlay)))
    changed = [name for name in merged if name not in rows or merged[name][1]!=rows[name][1]]
    require(set(changed)<=expected_changes and
            {'usr/bin/xq-coach-worker','usr/bin/xinyi-engine','usr/bin/start-xinyi','opt/xinyi/detector.xqi.gz'}<=set(changed),
            'Unexpected overlay content')
    for name in rows:
        if name not in expected_changes:require(merged[name]==rows[name], 'Unselected base content changed: '+name)
    for line in merged['opt/xinyi/runtime.sha256'][1].decode().splitlines():
        digest,path = line.split('  ',1)
        require(identity(merged[path.lstrip('/')][1])['sha256']==digest, 'Runtime hash mismatch: '+path)
    offset = (len(originals['PN04FS.BIN'])+4095)&~4095
    require(offset+len(overlay)<=0x1000000, 'Overlay exceeds 16MiB rootfs aperture')
    dtb = bytearray(originals['PN04.DTB']);head,props,_ = tokens(dtb)
    old = {name:value[0] for name,value in props.items()}
    end = struct.pack('>I',0x03000000+offset+len(overlay))
    struct.pack_into('>I',dtb,head[2]+props['/chosen/linux,initrd-end'][1],struct.unpack('>I',end)[0])
    _,props,_ = tokens(dtb);old['/chosen/linux,initrd-end'] = end
    require({name:value[0] for name,value in props.items()}==old, 'Unexpected DT mutation')
    support, stage, updates = out/'support', out/'payloads', out/'sd-update'
    for name in ['runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h','camera.h']:
        data = read(ROOT/'sw/bootloader'/name)
        require(data==subprocess.check_output(['git','show',MAIN+':sw/bootloader/'+name],cwd=ROOT,timeout=30), 'Frozen boot helper changed')
        save(support/'boot'/name,data)
    for name in ['loader.c','host_test.c','link.ld','start.S']:save(support/name,read(ROOT/'linux/xinyi_board/boot'/name))
    for name in ['xq_camera.c','xq_camera.h','xq_vision.h']:save(support/name,read(ROOT/'linux/vision'/name))
    save(support/'xiangqi_search.h',read(ROOT/'sw/xiangqi/xiangqi_search.h'))
    target = read(a.base/'support/target.h')+b'\n#define XINYI_REQUIRE_EXACT_VERSION 0x00010001u\n'
    if sd_prefix in ('PN07','PN08'):target+=b'#define XINYI_TEST_KEEP_PN06 1\n'
    if sd_prefix=='PN08':target+=b'#define XINYI_TEST_KEEP_PN07 1\n'
    save(support/'target.h',target)
    publication = json.loads(read(ROOT/PUB/'manifest.json'))
    require(identity(read(a.base/'support/target-rom.hex'))['sha256']==publication['hardware_source_sha256']['pds/bootrom.hex'], 'ROM differs from e42')
    save(support/'target-rom.bin',read(a.base/'support/target-rom.bin'))
    entries = [(name,int(base['compiled_descriptors'][name]['address'],16),originals[name])
               for name in ['PN04SBI.BIN','PN04FS.BIN','PN04NN.PFF','PN04ATK.BIN']]
    entries += [(card('K.BIN'),0x00400000,kernel),(card('.DTB'),0x1a000000,bytes(dtb)),
                (card('UPD.GZ'),0x03000000+offset,overlay)]
    table = (f'#include "fat_ro.h"\n#define XINYI_BOOT_PREFIX "{sd_prefix}"\n#define XINYI_ROOTFS_OVERLAY 1\n'
             f'#define XINYI_ROOTFS_BASE_BYTES {len(originals["PN04FS.BIN"])}u\n#define XINYI_ROOTFS_OVERLAY_OFFSET {offset}u\n'
             'typedef struct {const char *name;uint32_t address,bytes,crc32;fat_ro_file_t file;} payload_t;\nstatic payload_t payloads[]={\n')
    for name,address,data in entries:
        save(stage/name,data);table += f'{{"{name}",0x{address:08x}u,{len(data)}u,0x{zlib.crc32(data):08x}u,{{0}}}},\n'
    table += '};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n'
    save(support/'payloads.h',table.encode())
    run('loader-gcc16',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/build_xinyi_cpu60_loader.ps1',
                       '-CandidateDirectory',logical,'-Prefix','PN04'])
    binary = read(out/'PN04BOOT.BIN')
    for name,address,data in entries:
        descriptor = struct.pack('<III',address,len(data),zlib.crc32(data))
        require(binary.count(descriptor)==1, 'Missing descriptor: '+name)
        at = binary.index(descriptor);ptr = struct.unpack_from('<I',binary,at-4)[0]-0x01000000
        require(binary[ptr:ptr+len(name)+1]==name.encode()+b'\0', 'Wrong descriptor filename')
    for name,data in [(card('BOOT.BIN'),binary),(card('K.BIN'),kernel),(card('.DTB'),bytes(dtb)),(card('UPD.GZ'),overlay)]:
        save(updates/name,data);save(stage/name,data)
    public = dict(status=sd_prefix+'_E42_HWC_KERNEL_ENGINE_PREPARED_NOT_INSTALLED_NOT_BOARD',prefix=sd_prefix,
        target_bitstream_sha256=IMAGE,base_manifest_sha256=BASE_MANIFEST,kernel_sha256=identity(kernel)['sha256'],
        derived_detector_sha256=XQI,rootfs_base_bytes=len(originals['PN04FS.BIN']),overlay_offset=offset,
        overlay_bytes=len(overlay),rootfs_bound_bytes=offset+len(overlay),rootfs_aperture_bytes=0x1000000,
        changed_rootfs_paths=changed,selected_rootfs_sha256={n:identity(merged[n][1])['sha256'] for n in changed},
        reused_sd_files={n:identity(d) for n,_,d in entries if n.startswith('PN04')},
        new_sd_files={p.name:identity(p.read_bytes()) for p in updates.iterdir()},coach_contract=contract,software_options=configuration,
        engineering_geometry_status_preserved=True,actual_board_latency_pass=False,recognition_60s_pass=False,
        recognition_300s_pass=False,
        training_hwc_178_accepted=False,production_ready=False,hardware_used=False,sd_written=False,
        flash_written=False,selector_modified=False)
    record(updates/card('.JSN'),public)
    # The audited FAT writer commits root entries in pairs. Bind the five
    # startup files in a sixth checksum file rather than create an odd tail.
    checksums = ''.join(identity(p.read_bytes())['sha256']+'  '+p.name+'\n' for p in sorted(updates.iterdir()))
    save(updates/card('.SHA'),checksums.encode())
    inst = out/'install';ist = inst/'support'
    for name in ['soc.h','sd.h','fat_ro.h','fat_ro.c','runtime.c','sd_native.c','crc32_fast.h','crc32_fast.c','console_line.h','console_line.c','camera.h']:
        save(ist/name,read(ROOT/'sw/bootloader'/name))
    for name in ['fat_camera.h','fat_camera.c']:save(ist/name,read(ROOT/'linux/boot/v2_1_sd/source/picture_fat_write'/name))
    ns = read(ROOT/'artifacts/vision-model-20261020-adapter/runtime/xq_sd_namespace_fat.c')
    include = b'#include "../../../linux/boot/v2_1_sd/source/picture_fat_write/fat_camera.c"'
    require(ns.count(include)==1,'Unknown namespace adapter');save(ist/'install_fat.c',ns.replace(include,b'#include "fat_camera.c"'))
    for name in ['install.c','install_xmodem.c','start.S','link.ld']:
        data = read(ROOT/'linux/xinyi_board/boot'/name)
        if name=='link.ld':data=data.replace(b'ORIGIN = 0x01000000',b'ORIGIN = 0x01800000')
        save(ist/name,data)
    save(ist/'target.h',target)
    install_files,header = [],'#include <stdint.h>\n'
    for i,(name,address) in enumerate([(card('K.BIN'),0x06000000),(card('.DTB'),0x06800000),(card('UPD.GZ'),0x07000000),
                                      (card('BOOT.BIN'),0x01400000),(card('.JSN'),0x01600000),(card('.SHA'),0x01610000)]):
        data = read(updates/name);save(inst/'payloads'/name,data)
        install_files.append(dict(name=name,address=address,aliases=[],**identity(data)))
        header += f'static const uint32_t slice_crc_{i}[]={{'+','.join(f'0x{zlib.crc32(data[j:j+65536]):08x}u' for j in range(0,len(data),65536))+'};\n'
    header += 'typedef struct {const char *name,*short_name;uint32_t address,bytes,crc;const char *aliases[4];int ready,exists;const uint32_t *slice_crc;uint32_t offset;} item_t;\nstatic item_t items[]={\n'
    for i,r in enumerate(install_files):
        stem,ext = r['name'].split('.');short = stem.ljust(8)+ext.ljust(3)
        header += f'{{"{r["name"]}","{short}",0x{r["address"]:08x}u,{r["bytes"]}u,0x{r["crc32"]}u,{{0}},0,0,slice_crc_{i},0}},\n'
    require(len(install_files)%2==0,'Installer payloads must form complete root pairs')
    header += '};\n#define INSTALL_COUNT 6u\n#define INSTALL_BOOT_INDEX 3u\n#define INSTALL_SECTORS 62333952u\n#define INSTALL_PARTITION 32u\n'
    save(ist/'install_payloads.h',header.encode())
    run('installer-gcc16',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'scripts/build_xinyi_sd_install.ps1','-CandidateDirectory',logical/'install'])
    record(inst/'install_contract.json',dict(status=sd_prefix+'_E42_CREATE_ONLY_INSTALLER_NOT_INSTALLED',prefix=sd_prefix,
        bitstream_sha256=IMAGE,media_sectors=62333952,partition_lba=32,cluster_bytes=32768,files=install_files,
        source_inputs=inputs,existing_files_preserved=True,selector_modified=False,sd_written=False,flash_written=False))
    require(all(identity(Path(p).read_bytes())==v for p,v in inputs.items()),'Input changed during preparation')
    public.update(source_inputs=inputs,commands=commands,installer_sha256=identity((inst/'PN03INST.BIN').read_bytes())['sha256'])
    record(out/'manifest.json',public)
    save(out/'README.txt',(f'Candidate only, not installed. When board testing resumes, copy only sd-update/{card("BOOT.BIN")}, {card("K.BIN")}, {card(".DTB")}, {card("UPD.GZ")}, {card(".JSN")}, {card(".SHA")} to SD root.\n'
         'Requires exact PN04SBI.BIN, PN04FS.BIN, PN04NN.PFF, PN04ATK.BIN. Preserve every old file and XQBOOT.CFG.\n'
         'Use only the audited published e42 CRAM image. No Flash or selector change. Not board/accuracy/latency acceptance.\n').encode())
    print(public['status'],sum(r['bytes'] for r in install_files))


if __name__=='__main__':
    main()
