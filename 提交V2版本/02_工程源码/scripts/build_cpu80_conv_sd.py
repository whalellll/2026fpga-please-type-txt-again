"""Build an isolated CPU80 SD boot kit from the accepted f79443a2 delivery.

No device access. Never changes accepted files, FPGA inputs, or physical media.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zlib


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wsl_path(path):
    value = Path(path).resolve().as_posix()
    return '/mnt/' + value[0].lower() + value[2:]


def cpio_entries(data):
    """Read newc without extracting paths; preserve duplicates and metadata."""
    records, offset = [], 0
    while offset + 110 <= len(data):
        start = offset
        require(data[offset:offset+6] == b'070701', 'Invalid newc header')
        fields = [int(data[offset+6+8*i:offset+14+8*i], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        offset += 110
        require(namesize > 0 and offset + namesize <= len(data), 'Invalid cpio name')
        name = data[offset:offset+namesize-1].decode('utf-8')
        require(data[offset+namesize-1] == 0, 'Unterminated cpio name')
        offset = (offset + namesize + 3) & ~3
        require(offset + size <= len(data), 'Truncated cpio body')
        content = data[offset:offset+size]
        offset = (offset + size + 3) & ~3
        record = dict(name=name, start=start, end=offset, fields=fields,
                      bytes=size, sha256=hashlib.sha256(content).hexdigest())
        records.append(record)
        if name == 'TRAILER!!!':
            require(not any(data[offset:]), 'Nonzero data after cpio trailer')
            return records
    raise ValueError('Missing cpio trailer')


def fdt_properties(data):
    require(data[:4] == b'\xd0\x0d\xfe\xed', 'Invalid DTB magic')
    _, total, off, strings = struct.unpack_from('>4I', data)
    require(total == len(data), 'Invalid DTB size')
    stack, result = [], {}
    while off + 4 <= len(data):
        token = struct.unpack_from('>I', data, off)[0]
        off += 4
        if token == 1:
            end = data.index(0, off)
            stack.append(data[off:end].decode())
            off = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>2I', data, off)
            off += 8
            end = data.index(0, strings + nameoff)
            name = data[strings+nameoff:end].decode()
            result['/' + '/'.join(stack[1:]) + '/' + name] = (off, size)
            off = (off + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            return result
        else:
            raise ValueError('Invalid DTB token')
    raise ValueError('Missing DTB end')


def make_fat32(path, files):
    """Deterministic superfloppy with contiguous chains and validated VFAT names.

    Test fixture only: this image is never used as a physical-disk write command.
    """
    sectors, reserved, fatsize = 327680, 32, 1
    while True:
        needed = (((sectors-reserved-2*fatsize) + 2)*4 + 511)//512
        if needed <= fatsize:
            break
        fatsize = needed
    data_sector = reserved + 2*fatsize
    boot = bytearray(512)
    boot[:11] = b'\xeb\x58\x90MSDOS5.0'
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, 1, reserved, 2, 0, 0, 0xf8, 0, 63, 255, 0, sectors)
    struct.pack_into('<IHHIHH', boot, 36, fatsize, 0, 0, 2, 1, 6)
    boot[64] = 0x80
    boot[66] = 0x29
    struct.pack_into('<I', boot, 67, 0x80321600)
    boot[71:82], boot[82:90], boot[510:512] = b'CPU80TEST  ', b'FAT32   ', b'\x55\xaa'
    fat = bytearray(fatsize*512)
    struct.pack_into('<3I', fat, 0, 0x0ffffff8, 0xffffffff, 0x0fffffff)
    root, cluster, info = bytearray(512), 3, {}
    index = 0
    with path.open('wb') as output:
        output.truncate(sectors*512)
        output.seek(0); output.write(boot)
        output.seek(6*512); output.write(boot)
        for number, file in enumerate(files):
            name, data = file.name, file.read_bytes()
            parts = name.split('.')
            short_ok = len(parts) <= 2 and 1 <= len(parts[0]) <= 8 and (len(parts) == 1 or len(parts[1]) <= 3)
            short = (parts[0].upper().ljust(8) + (parts[1].upper() if len(parts)>1 else '').ljust(3)).encode() if short_ok else ('FILE%04dBIN' % number).encode()
            require(len(short) == 11, 'Invalid FAT short name')
            if not short_ok:
                require(len(name) < 13, 'Fixture LFN exceeds one slot')
                checksum = 0
                for byte in short:
                    checksum = (((checksum & 1) << 7) + (checksum >> 1) + byte) & 255
                lfn = bytearray(b'\xff'*32)
                lfn[0], lfn[11], lfn[12], lfn[13] = 0x41, 0x0f, 0, checksum
                lfn[26:28] = b'\x00\x00'
                text = name.encode('utf-16le') + b'\x00\x00'
                text += b'\xff'*(26-len(text))
                lfn[1:11], lfn[14:26], lfn[28:32] = text[:10], text[10:22], text[22:26]
                root[index:index+32] = lfn
                index += 32
            entry = bytearray(32)
            entry[:11], entry[11] = short, 0x20
            struct.pack_into('<H', entry, 20, cluster >> 16)
            struct.pack_into('<H', entry, 26, cluster & 65535)
            struct.pack_into('<I', entry, 28, len(data))
            require(index+32 <= 512, 'Fixture root overflow')
            root[index:index+32] = entry
            start = (data_sector+cluster-2)*512
            info[name] = dict(directory=data_sector*512+index, data=start, bytes=len(data))
            index += 32
            count = (len(data)+511)//512
            for item in range(cluster, cluster+count):
                struct.pack_into('<I', fat, item*4, item+1 if item+1<cluster+count else 0x0fffffff)
            output.seek(start); output.write(data)
            cluster += count
        require(data_sector+cluster-2 < sectors, 'FAT fixture overflow')
        for location in (reserved, reserved+fatsize):
            output.seek(location*512); output.write(fat)
        output.seek(data_sector*512); output.write(root)
    return info


def build(source, output, distro, extras=None):
    require(not output.exists(), 'Output already exists; choose a new candidate directory')
    script_dir = Path(__file__).resolve().parent
    receipt = json.loads((source/'CPU80_DELIVERY.json').read_text(encoding='utf-8'))
    require(receipt['run_id'] == 'f79443a2e020498c853ce868cde9b187' and receipt['cpu_hz'] == 80000000, 'Wrong accepted source')
    ram = source/'artifacts/cpu80_candidate_20261019/ram-boot80'
    require(sha(ram/'overlay-manifest.json') == receipt['files_sha256']['artifacts/cpu80_candidate_20261019/ram-boot80/overlay-manifest.json'], 'RAM manifest differs from accepted delivery')
    old = json.loads((ram/'overlay-manifest.json').read_text())
    inputs = {}

    def verified(relative, expected=None):
        file = source/relative
        digest = sha(file)
        expected = expected or receipt['files_sha256'][relative]
        require(digest == expected, 'Accepted source mismatch: '+relative)
        inputs[relative] = digest
        return file

    for name, digest in old['outputs_sha256'].items():
        if (ram/name).is_file():
            verified((ram/name).relative_to(source).as_posix(), digest)
    verified('artifacts/soc_top.sbit', receipt['bitstream_sha256'])
    verified('artifacts/bootrom.hex')
    verified('sw/bootloader/sd_boot.c')
    verified('sw/bootloader/main.c')
    base_path = verified('artifacts/voice_hw_candidate_20261016/boot/vafs.bin')
    base, overlay = base_path.read_bytes(), (ram/'gui-overlay.cpio').read_bytes()
    base_records, overlay_records = cpio_entries(base), cpio_entries(overlay)
    # Reproduce install_gui_overlay() exactly: remove the first trailer and
    # overwrite its location with the accepted GUI archive, preserving bytes.
    trailer = base_records[-1]['start']
    require(trailer == 8445624 and len(overlay) == 3104768, 'Unexpected accepted overlay layout')
    rootfs = base[:trailer] + overlay
    merged = cpio_entries(rootfs)
    require([(r['name'], r['fields'], r['sha256']) for r in merged] ==
            [(r['name'], r['fields'], r['sha256']) for r in base_records[:-1]+overlay_records], 'CPIO metadata/content mismatch')
    extra_records = []
    if extras is not None:
        # Add only new executable tools; keep all accepted entries and their
        # order intact. The final trailer is replaced by additive newc entries.
        from pathlib import PurePosixPath
        extra_manifest=json.loads((extras/'manifest.json').read_text(encoding='utf-8'))
        existing={row['name'].removeprefix('./') for row in merged}
        added=bytearray()
        def entry(name,data,mode):
            nb=name.encode('utf-8')+b'\0'
            fields=[0,mode,0,0,1,0,len(data),0,0,0,0,len(nb),0]
            raw=b'070701'+b''.join(f'{x:08x}'.encode('ascii') for x in fields)+nb
            raw+=b'\0'*((-len(raw))%4)
            raw+=data
            raw+=b'\0'*((-len(raw))%4)
            return raw
        for name,digest in sorted(extra_manifest['files_sha256'].items()):
            require(name.startswith('usr/bin/') and '..' not in PurePosixPath(name).parts and name not in existing and '\\' not in name,'Unsafe/duplicate additive tool')
            file=extras/name
            require(file.is_file() and not file.is_symlink() and sha(file)==digest,'Additive executable identity mismatch')
            data=file.read_bytes()
            require(data[:5]==b'\x7fELF\x01' and struct.unpack_from('<H',data,18)[0]==243 and not struct.unpack_from('<I',data,36)[0]&1,'Tool must be RV32 ELF without compressed instructions')
            added+=entry(name,data,0o100755)
            extra_records.append(dict(name=name,bytes=len(data),sha256=digest))
        added+=entry('TRAILER!!!',b'',0)
        rootfs=rootfs[:merged[-1]['start']]+bytes(added)
        # Independently reparse and compare every old entry and appended file.
        all_records=cpio_entries(rootfs)
        require([(x['name'],x['fields'],x['sha256']) for x in all_records[:len(merged)-1]]==[(x['name'],x['fields'],x['sha256']) for x in merged[:-1]],'Accepted rootfs entry changed')
        require([(x['name'],x['bytes'],x['sha256']) for x in all_records[len(merged)-1:-1]]==[(x['name'],x['bytes'],x['sha256']) for x in extra_records],'Additive CPIO mismatch')
        merged=all_records
    dtb = bytearray((ram/'soc.dtb').read_bytes())
    props = fdt_properties(dtb)
    for name in ('/cpus/timebase-frequency','/cpus/cpu@0/clock-frequency'):
        off, size = props[name]
        require(size == 4 and struct.unpack_from('>I',dtb,off)[0] == 80000000, 'Wrong CPU DTB frequency')
    off, size = props['/chosen/linux,initrd-end']
    require(size == 4, 'Wrong initrd cells')
    struct.pack_into('>I',dtb,off,0x03000000+len(rootfs))
    require((0x03000000+len(rootfs)==0x03b03eb8) if extras is None else (0x03000000+len(rootfs)<0x04000000), 'SD rootfs range mismatch')
    output.mkdir(parents=True)
    sd, support, evidence = output/'sd-root', output/'support', output/'evidence'
    for directory in (sd,support,evidence): directory.mkdir()
    (sd/'rootfs.cpio').write_bytes(rootfs)
    (sd/'soc.dtb').write_bytes(dtb)
    (sd/'mmode.dtb').write_bytes(dtb)
    shutil.copyfile(ram/'fw_jump.bin',sd/'fw_jump.bin')
    payload_sources = {'Image':'artifacts/voice_hw_candidate_20261016/boot/vaimage.bin',
                       'pikafish.pff':'linux/boot/pikafish.pff','pikafish.atk':'linux/boot/pikafish.atk'}
    for name, relative in payload_sources.items(): shutil.copyfile(verified(relative),sd/name)
    boot = support/'bootloader'
    boot.mkdir()
    for name in ('runtime.c','sd_native.c','fat_ro.c','crc32_fast.c','soc.h','sd.h','fat_ro.h','crc32_fast.h'):
        shutil.copyfile(verified('sw/bootloader/'+name),boot/name)
    for name in ('loader.c','host_test.c'):
        shutil.copyfile(script_dir/'cpu80_sd'/name,support/name)
    (support/'cpu80_sd').mkdir()
    for name in ('loader.c','host_test.c'):
        shutil.copyfile(script_dir/'cpu80_sd'/name,support/'cpu80_sd'/name)
    shutil.copyfile(Path(__file__),support/'build_cpu80_sd_boot.py')
    shutil.copyfile(ram/'start.S', support/'start.S')
    link = (ram/'link.ld').read_text().replace('ORIGIN = 0x01000000','ORIGIN = 0x00000000')
    (support/'link.ld').write_text(link, encoding='utf-8')
    addresses = {'fw_jump.bin':0x18000000,'Image':0x00400000,'rootfs.cpio':0x03000000,
                 'soc.dtb':0x1a000000,'pikafish.pff':0x10000000,'pikafish.atk':0x15000000}
    records = []
    header = '#ifndef CPU80_PAYLOADS_H\n#define CPU80_PAYLOADS_H\n#include "fat_ro.h"\n'
    header += 'typedef struct { const char *name; uint32_t address, bytes, crc32; fat_ro_file_t file; } payload_t;\nstatic payload_t payloads[] = {\n'
    for name, address in addresses.items():
        data = (sd/name).read_bytes()
        crc = zlib.crc32(data)
        header += ' {"%s",0x%08xu,%du,0x%08xu,{0}},\n' % (name,address,len(data),crc)
        records.append(dict(name=name,address=address,bytes=len(data),crc32=f'{crc:08x}',sha256=sha(sd/name)))
    header += '};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n#endif\n'
    (support/'payloads.h').write_text(header,encoding='ascii')
    commands = []

    def run(argv, logname, timeout=180):
        command = ['wsl.exe','-d',distro,'--',*argv]
        try:
            result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        except subprocess.TimeoutExpired as error:
            (evidence/logname).write_bytes(error.stdout or b'')
            write_json(evidence/'failure.json',dict(status='OFFLINE_COMMAND_TIMEOUT_NOT_BOARD',argv=argv,timeout_seconds=timeout,log=logname))
            raise
        (evidence/logname).write_bytes(result.stdout)
        commands.append(dict(argv=argv,exit=result.returncode,log=logname))
        require(result.returncode == 0, f'Command failed: {logname}: '+result.stdout.decode(errors='replace')[-1800:])
        return result.stdout

    cc, tools = '/opt/toolchain/bin/riscv32-linux-musl-gcc','/opt/toolchain/bin/riscv32-linux-musl-'
    flags = ['-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-mstrict-align','-ffreestanding','-fno-builtin','-fno-common','-ffunction-sections','-fdata-sections','-Os','-Wall','-Wextra','-Werror','-I',wsl_path(boot),'-I',wsl_path(support)]
    objects = []
    for name in ('start.S','loader.c','runtime.c','sd_native.c','fat_ro.c','crc32_fast.c'):
        path = support/name if name in ('start.S','loader.c') else boot/name
        obj = support/(path.stem+'.o')
        run([cc,*flags,'-c',wsl_path(path),'-o',wsl_path(obj)],'build-'+path.stem+'.log')
        objects.append(wsl_path(obj))
    run([cc,'-march=rv32ima','-mabi=ilp32','-nostdlib','-static','-Wl,--gc-sections,--no-relax,--build-id=none','-T',wsl_path(support/'link.ld'),'-Wl,-Map,'+wsl_path(support/'loader.map'),*objects,'-lgcc','-o',wsl_path(support/'loader.elf')],'link.log')
    run([tools+'objcopy','-O','binary',wsl_path(support/'loader.elf'),wsl_path(sd/'Image.mmode')],'objcopy.log')
    elf = (support/'loader.elf').read_bytes()
    require(elf[:5] == b'\x7fELF\x01' and struct.unpack_from('<I',elf,24)[0] == 0 and not struct.unpack_from('<I',elf,36)[0]&1,'Loader must be ELF32, entry=0, no RVC')
    require((sd/'Image.mmode').stat().st_size < 1024*1024, 'Loader overlaps its stack')
    run([tools+'objdump','-d',wsl_path(support/'loader.elf')],'loader-disassembly.txt')
    run([tools+'readelf','-h','-A','-l',wsl_path(support/'loader.elf')],'loader-elf.txt')
    host_flags = ['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-missing-braces','-I',wsl_path(boot),'-I',wsl_path(support)]
    run(['gcc',*host_flags,'-Dmain=sd80_main','-c',wsl_path(support/'loader.c'),'-o',wsl_path(support/'host-loader.o')],'host-compile.log')
    run(['gcc',*host_flags,wsl_path(support/'host_test.c'),wsl_path(support/'host-loader.o'),wsl_path(boot/'fat_ro.c'),wsl_path(boot/'crc32_fast.c'),'-o',wsl_path(support/'host-test')],'host-link.log')
    disk = evidence/'test-fat32.img'
    locations = make_fat32(disk, sorted(sd.iterdir()))
    tests = []

    runners = [([], support/'host-test', '')]
    # Execute the very same RV32 loader object under QEMU user mode as well.
    # The target object is only renamed to let the test harness own main().
    run([tools+'objcopy','--redefine-sym','main=sd80_main',wsl_path(support/'loader.o'),wsl_path(support/'rv32-loader-test.o')],'rv32-object.log')
    run([cc,'-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static','-O2','-Wall','-Wextra','-Werror','-I',wsl_path(boot),'-I',wsl_path(support),wsl_path(support/'host_test.c'),wsl_path(support/'rv32-loader-test.o'),wsl_path(boot/'fat_ro.c'),wsl_path(boot/'crc32_fast.c'),'-o',wsl_path(support/'rv32-test')],'rv32-link.log')
    runners.append((['qemu-riscv32'],support/'rv32-test','rv32-'))

    def test(scenario, logname=None):
        for prefix, binary, label in runners:
            log = label + (logname or 'test-'+scenario+'.log')
            data = run([*prefix,wsl_path(binary),scenario,wsl_path(disk),wsl_path(sd)],log)
            require(('HOST_TEST_PASS '+scenario).encode() in data,'Missing test completion')
            tests.append(log)

    for scenario in ('pass','clock','init','io','abort'): test(scenario)

    def mutation(offset, value, name):
        with disk.open('r+b') as f:
            f.seek(offset); oldbyte=f.read(len(value)); f.seek(offset); f.write(value)
        try: test('reject','test-'+name+'.log')
        finally:
            with disk.open('r+b') as f: f.seek(offset); f.write(oldbyte)

    mutation(locations['Image']['data']+100,b'\xff','corrupt-kernel')
    mutation(locations['pikafish.pff']['directory'],b'\xe5','missing-model')
    mutation(locations['fw_jump.bin']['directory']+28,struct.pack('<I',1),'bad-firmware-size')
    mutation(510,b'\x00\x00','bad-fat-signature')
    run(['dtc','-I','dtb','-O','dts','-o',wsl_path(evidence/'soc80.dts'),wsl_path(sd/'soc.dtb')],'dtb-decode.log')
    # GNU cpio independently lists the complete combined archive.
    run(['python3','-c','import subprocess,sys; f=open(sys.argv[1],"rb"); r=subprocess.run(["cpio","-it","--quiet"],stdin=f); sys.exit(r.returncode)',wsl_path(sd/'rootfs.cpio')],'rootfs-cpio-list.txt')
    write_json(evidence/'cpio-equivalence.json',dict(status='EXACT_ACCEPTED_RAM_ROOTFS_AND_DTB_EQUIVALENCE_PASS' if extras is None else 'ACCEPTED_ROOTFS_PRESERVED_PLUS_VERIFIED_CONV_TOOLS',extra_records=extra_records,base_trailer_offset=trailer,overlay_bytes=len(overlay),merged_bytes=len(rootfs),entries=len(merged)-1,initrd_end=hex(0x03000000+len(rootfs)),base_sha256=sha(base_path),overlay_sha256=sha(ram/'gui-overlay.cpio'),rootfs_sha256=sha(sd/'rootfs.cpio'),dtb_sha256=sha(sd/'soc.dtb')))
    manifest = dict(schema=1,status='CPU80_SD_OFFLINE_VERIFIED_BOARD_PENDING' if extras is None else 'CPU80_CONV_SD_OFFLINE_VERIFIED_BOARD_PENDING',extra_records=extra_records,created_utc=datetime.now(timezone.utc).isoformat(),source=str(source),source_delivery_sha256=sha(source/'CPU80_DELIVERY.json'),accepted_run_id=receipt['run_id'],cpu_implementation_commit=receipt['cpu_implementation_commit'],soc_implementation_commit=receipt['soc_implementation_commit'],bitstream_sha256=receipt['bitstream_sha256'],cpu_hz=80000000,sys_hz=49500000,sbi_ratio=[99,160],boot_command='sdboot',bootrom_entry=0,inputs_sha256=inputs,payloads=records,sd_root_files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(sd.iterdir())},tests=tests,commands=commands,board_tested=False,physical_media_written=False,flash_written=False,remote_pushed=False,limitations=['New SD loader and SD path require board acceptance.','No power-on SD auto-boot: accepted ROM requires sdboot.','Original CPU80 acceptance does not certify this new SD package.'])
    write_json(output/'manifest.json',manifest)
    (sd/'SHA256SUMS.txt').write_text(''.join(f"{v['sha256']}  {name}\n" for name,v in manifest['sd_root_files'].items()),encoding='ascii')
    write_json(evidence/'offline-tests.json',dict(status='CPU80_SD_OFFLINE_TESTS_PASS_NOT_BOARD',tests=tests,loader_bytes=(sd/'Image.mmode').stat().st_size,host_test_scope='Production loader + accepted FAT reader/CRC; mocked SD transport/MMIO/DDR aliases; every loaded byte compared before the final jump.',hardware_equivalence=False))
    print(json.dumps(dict(status=manifest['status'],output=str(output),sd_files=len(manifest['sd_root_files']),tests=len(tests)),ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,default=Path('G:/fpga/c80unpack_f79443a2_20261020_r2/SOC'))
    ap.add_argument('--output',type=Path,default=Path('G:/fpga/performance_soc_voice_hw/artifacts/cpu80_sd_20261021'))
    ap.add_argument('--distro',default='pikafish-verify')
    ap.add_argument('--extras',type=Path,required=True)
    args = ap.parse_args()
    build(args.source.resolve(),args.output.resolve(),args.distro,args.extras.resolve())
