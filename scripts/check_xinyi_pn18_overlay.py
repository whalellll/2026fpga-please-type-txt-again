"""PN18 eight-payload loader/DTB checks, using regular-file SD/MMIO mocks.

The RV32 success run links the exact production GCC16 loader object. A sparse
512MiB FAT fixture holds the actual immutable payloads; no device is opened.
"""
from pathlib import Path
import argparse
import json
import shutil
import struct
import subprocess
import time

from picture_workspace import ROOT, workspace_path
from prepare_xinyi_cpu60_kit import require
from prepare_picture_candidate import tokens
from prepare_picture_pn18 import file_identity, reserve_voice_dtb, BANK_NODE, BANK_BASE
from build_cpu80_conv_sd import wsl_path


def make_fat32(path, files):
    """Streaming, contiguous FAT32 fixture; the image is a private regular file."""
    sectors, reserved, spc, fatsize = 1048576, 32, 8, 1
    while True:
        clusters = (sectors - reserved - 2*fatsize) // spc
        needed = ((clusters + 2)*4 + 511) // 512
        if needed <= fatsize: break
        fatsize = needed
    require(65525 <= clusters < 0x0ffffff5, 'Genuine FAT32 cluster count')
    data_sector = reserved + 2*fatsize
    boot = bytearray(512)
    boot[:11] = b'\xeb\x58\x90MSDOS5.0'
    struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, spc, reserved, 2, 0, 0, 0xf8, 0, 63, 255, 0, sectors)
    struct.pack_into('<IHHIHH', boot, 36, fatsize, 0, 0, 2, 1, 6)
    boot[64], boot[66] = 0x80, 0x29
    struct.pack_into('<I', boot, 67, 0x18321600)
    boot[71:82], boot[82:90], boot[510:512] = b'PN18MOCK   ', b'FAT32   ', b'\x55\xaa'
    fat, root, cluster, locations = bytearray(fatsize*512), bytearray(spc*512), 3, {}
    struct.pack_into('<3I', fat, 0, 0x0ffffff8, 0xffffffff, 0x0fffffff)
    with path.open('xb') as out:
        out.truncate(sectors*512)
        for off in [0, 6*512]: out.seek(off); out.write(boot)
        for i, file in enumerate(files):
            parts = file.name.split('.')
            require(len(parts) == 2 and 1 <= len(parts[0]) <= 8 and 1 <= len(parts[1]) <= 3, '8.3 names required')
            size = file.stat().st_size
            entry = memoryview(root)[i*32:(i+1)*32]
            entry[:11] = (parts[0].upper().ljust(8)+parts[1].upper().ljust(3)).encode()
            entry[11] = 0x20
            struct.pack_into('<H', entry, 20, cluster >> 16)
            struct.pack_into('<H', entry, 26, cluster & 65535)
            struct.pack_into('<I', entry, 28, size)
            start = (data_sector+(cluster-2)*spc)*512
            locations[file.name] = dict(directory=data_sector*512+i*32, data=start, bytes=size)
            count = (size+spc*512-1)//(spc*512)
            require(cluster+count <= clusters+2, 'Fixture capacity')
            for item in range(cluster, cluster+count):
                struct.pack_into('<I', fat, item*4, item+1 if item+1 < cluster+count else 0x0fffffff)
            out.seek(start)
            with file.open('rb') as source: shutil.copyfileobj(source, out, 1024*1024)
            cluster += count
        for location in [reserved, reserved+fatsize]: out.seek(location*512); out.write(fat)
        out.seek(data_sector*512); out.write(root)
    return locations


def harness(source):
    """Keep actual loader callsite; bound comparison memory and mock file mapping."""
    old = '''    int image=open(argv[2],O_RDONLY);check(image>=0 && !fstat(image,&st),"FAT image");
    image_data=malloc((size_t)st.st_size);check(image_data!=NULL,"image allocation");
    check(pread(image,image_data,(size_t)st.st_size,0)==st.st_size,"image read");close(image);
    card.sector_count=(uint32_t)(st.st_size/512);
'''
    require(source.count(old) == 1, 'Known mock image setup')
    source = source.replace(old, '')
    at = '''#ifdef XINYI_ROOTFS_OVERLAY
    memset((void *)(uintptr_t)(0x03000000u+XINYI_ROOTFS_BASE_BYTES)'''
    require(source.count(at) == 1, 'Known mock payload maps')
    replacement = '''    int image=open(argv[2],O_RDONLY);
    check(image>=0 && !fstat(image,&st) && S_ISREG(st.st_mode),"regular FAT image");
    image_data=mmap(NULL,(size_t)st.st_size,PROT_READ,MAP_PRIVATE,image,0);
    check(image_data!=MAP_FAILED,"image mapping");close(image);
    card.sector_count=(uint32_t)(st.st_size/512);
    memset((void *)(uintptr_t)(XINYI_WHOLE_BANK_BASE+XINYI_WHOLE_BANK_BYTES),0xa5,
           XINYI_WHOLE_BANK_SPAN-XINYI_WHOLE_BANK_BYTES);
    memset((void *)(uintptr_t)((XINYI_WHOLE_BANK_BASE+XINYI_WHOLE_BANK_BYTES)|0x80000000u),0xa5,
           XINYI_WHOLE_BANK_SPAN-XINYI_WHOLE_BANK_BYTES);
'''+at
    source = source.replace(at, replacement)
    old = '''        uint8_t *data=malloc(p->bytes);check(data!=NULL,"allocation");
        check(fread(data,1,p->bytes,f)==p->bytes,"source read");fclose(f);
        check(!memcmp(data,(const void *)(uintptr_t)p->address,p->bytes),"cached payload bytes");
        check(!memcmp(data,(const void *)(uintptr_t)(p->address|0x80000000u),p->bytes),"uncached word publication bytes");
        free(data);'''
    require(source.count(old) == 1, 'Known mock source comparison')
    source = source.replace(old, '''        uint8_t data[32768];
        for(uint32_t at=0;at<p->bytes;){
            uint32_t n=p->bytes-at;if(n>sizeof(data))n=sizeof(data);
            check(fread(data,1,n,f)==n,"source read");
            check(!memcmp(data,(const void *)(uintptr_t)(p->address+at),n),"cached payload bytes");
            check(!memcmp(data,(const void *)(uintptr_t)((p->address+at)|0x80000000u),n),"uncached word publication bytes");
            at+=n;
        }
        check(fgetc(f)==EOF,"exact source length");fclose(f);''')
    at = '    jumped=1;longjmp(finish,1);'
    require(source.count(at) == 1, 'Known mock jump')
    source = source.replace(at, '''    for(unsigned i=XINYI_WHOLE_BANK_BYTES;i<XINYI_WHOLE_BANK_SPAN;i++)
        check(!*(const uint8_t *)(uintptr_t)(XINYI_WHOLE_BANK_BASE+i) &&
              !*(const uint8_t *)(uintptr_t)((XINYI_WHOLE_BANK_BASE+i)|0x80000000u),
              "bank reserved tail zeros");
'''+at)
    source = source.replace('!strcmp(scenario,"camera-stuck"))\n        check(!initialized',
                            '!strcmp(scenario,"camera-stuck") || !strcmp(scenario,"bank-layout"))\n        check(!initialized')
    source = source.replace('complete six-file load', 'complete eight-file load')
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); c = workspace_path(a.candidate); out = workspace_path(a.output)
    require(out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()) and not out.exists(), 'Fresh private E output required')
    out.mkdir(parents=True)
    result = dict(status='PN18_OFFLINE_CHECK_RUNNING', hardware_used=False, sd_written=False, flash_written=False,
                  tests=[], commands=[], negative_controls=[], dtb_checks=[])
    try:
        m = json.loads((c/'manifest.json').read_text(encoding='utf-8'))
        require(m['prefix'] == 'PN18' and m['payload_count'] == 8, 'PN18 manifest required')
        source_hash = {str(Path(__file__).resolve()):file_identity(Path(__file__))}
        for name, value in m['source_inputs'].items():
            require(file_identity(Path(name)) == value, 'Prepared source drift: '+name)
        for row in m['payloads']:
            require(file_identity(c/'payloads'/row['name']) == {k:row[k] for k in ['bytes','sha256','crc32']}, 'Payload drift')
        support, stage = c/'support', c/'payloads'
        compiled = [support/'loader.c', support/'payloads.h', support/'host_test.c', support/'target.h',
                    support/'xq_camera.c', support/'xq_camera.h', c/'rv32-loader-test.o']
        compiled.extend(p for p in (support/'boot').iterdir() if p.is_file())
        source_hash.update({str(p):file_identity(p) for p in compiled})
        # The new DT node and only initrd-end differ; exact old props are an oracle.
        old = (c/'sd-full/PN15.DTB').read_bytes(); new = (stage/'PN18.DTB').read_bytes()
        op = {n:v[0] for n,v in tokens(old)[1].items()}; np = {n:v[0] for n,v in tokens(new)[1].items()}
        expected = dict(op)
        expected['/chosen/linux,initrd-end'] = struct.pack('>I', 0x03000000+m['rootfs_bound_bytes'])
        expected[BANK_NODE+'/reg'] = struct.pack('>II', BANK_BASE, m['whole_voice']['span'])
        expected[BANK_NODE+'/no-map'] = b''
        require(np == expected, 'Exact reservation/old property equality')
        result['dtb_checks'].append('exact_old_properties_plus_bank_reg_no_map_and_initrd_end')
        def reject_dtb(name, blob=old, size=None, span=None):
            try: reserve_voice_dtb(blob, size if size is not None else m['rootfs_bound_bytes'], m['whole_voice']['bytes'],
                                   span if span is not None else m['whole_voice']['span'])
            except (ValueError, KeyError): result['dtb_checks'].append(name); return
            raise ValueError('DTB negative not rejected: '+name)
        reject_dtb('wrong_page_span', span=m['whole_voice']['span']+4096)
        reject_dtb('oversized_initrd', size=0x01000001)
        reject_dtb('duplicate_voice_node', blob=new)
        overlap = bytearray(old); h, props, _ = tokens(overlap)
        struct.pack_into('>II', overlap, h[2]+props['/reserved-memory/opensbi-low@1000000/reg'][1], BANK_BASE, 4096)
        reject_dtb('existing_reservation_overlap', blob=bytes(overlap))
        (out/'host-pn18.c').write_text(harness((support/'host_test.c').read_text()), encoding='utf-8', newline='\n')
        fixture = out/'synthetic-fat32.img'
        locations = make_fat32(fixture, [stage/r['name'] for r in m['payloads']])
        (out/'fixture.json').write_text(json.dumps(dict(bytes=fixture.stat().st_size, locations=locations),indent=2)+'\n')
        def run(name, argv, expect=None):
            start = time.monotonic()
            try: r = subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--',*map(str,argv)], capture_output=True, timeout=180)
            except subprocess.TimeoutExpired as e:
                (out/(name+'.log')).write_bytes((e.stdout or b'')+(e.stderr or b'')); raise
            data = r.stdout+r.stderr; (out/(name+'.log')).write_bytes(data)
            result['commands'].append(dict(name=name,seconds=round(time.monotonic()-start,3),exit=r.returncode))
            if expect is None: require(r.returncode == 0, name+': '+data.decode(errors='replace')[-1800:])
            else: require(r.returncode != 0 and expect in data, 'Negative control did not fail correctly: '+name)
            return data
        inc = ['-I', wsl_path(support/'boot'), '-I', wsl_path(support)]
        flags = ['-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',*inc]
        common = [wsl_path(out/'host-pn18.c'), wsl_path(support/'boot/fat_ro.c'),
                  wsl_path(support/'boot/crc32_fast.c'), wsl_path(support/'xq_camera.c')]
        def host_link(name, source, extra_inc=None):
            opts = [*(extra_inc or []), *flags]
            run(name+'-object',['gcc',*opts,'-Dmain=xinyi_boot_main','-c',wsl_path(source),'-o',wsl_path(out/(name+'.o'))])
            run(name+'-link',['gcc',*flags,*common,wsl_path(out/(name+'.o')),'-Wl,--gc-sections','-o',wsl_path(out/(name+'-test'))])
        host_link('host', support/'loader.c')
        run('rv32-same-production-object-link',['/opt/toolchain/bin/riscv32-linux-musl-gcc','-march=rv32ima',
            '-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-static',*flags,*common,wsl_path(c/'rv32-loader-test.o'),
            '-Wl,--gc-sections','-o',wsl_path(out/'rv32-test')])
        def test(scenario, label=None, rv=False, binary=None, expect=None):
            name = ('rv32-' if rv else 'host-')+(label or scenario)
            binary = binary or out/('rv32-test' if rv else 'host-test')
            data = run(name,[*(['qemu-riscv32'] if rv else []), wsl_path(binary), scenario,
                wsl_path(fixture), wsl_path(stage), wsl_path(support/'target-rom.bin')], expect)
            if expect is None:
                require(('HOST_TEST_PASS '+scenario).encode() in data, 'Missing completion: '+name)
                result['tests'].append(dict(name=name, same_production_object=rv))
        for s in ['pass','clock','wrong-exact','engine-busy-0','engine-busy-1','engine-busy-2',
                  'engine-busy-3','engine-busy-4','camera-stuck','init','io','abort']:
            test(s)
        test('pass', rv=True)
        def mutation(offset, data, label, scenario='reject', rv=False):
            with fixture.open('r+b') as f: f.seek(offset); saved=f.read(len(data)); f.seek(offset); f.write(data)
            try: test(scenario,label,rv)
            finally:
                with fixture.open('r+b') as f: f.seek(offset); f.write(saved)
        bank = locations['P18VOICE.BIN']
        mutation(bank['directory'], b'\xe5', 'missing-bank', 'metadata')
        mutation(bank['directory']+28, struct.pack('<I',bank['bytes']-1), 'wrong-bank-size', 'metadata')
        mutation(bank['directory']+28, struct.pack('<I',bank['bytes']-1), 'wrong-bank-size', 'metadata',rv=True)
        for at, label in [(bank['data']+100,'bank-header-crc'),(bank['data']+bank['bytes']-1,'bank-last-byte-crc')]:
            with fixture.open('rb') as f: f.seek(at); value=f.read(1)
            mutation(at, bytes([value[0]^1]), label)
        with fixture.open('rb') as f: f.seek(bank['data']+bank['bytes']-1); value=f.read(1)
        mutation(bank['data']+bank['bytes']-1,bytes([value[0]^1]),'bank-last-byte-crc',rv=True)
        # A deliberately wrong reserved span must fail before SD initialization.
        negative = out/'wrong-layout'; negative.mkdir()
        loader = (support/'loader.c').read_text()
        (negative/'loader.c').write_text(loader, newline='\n')
        header = (support/'payloads.h').read_text()
        wanted = f'#define XINYI_WHOLE_BANK_SPAN {m["whole_voice"]["span"]}u'
        require(header.count(wanted) == 1, 'Known reservation macro')
        (negative/'payloads.h').write_text(header.replace(wanted, f'#define XINYI_WHOLE_BANK_SPAN {m["whole_voice"]["span"]+4096}u'),newline='\n')
        host_link('layout-negative', negative/'loader.c', ['-I', wsl_path(negative)])
        test('bank-layout', binary=out/'layout-negative-test')
        result['negative_controls'].append('wrong_span_rejects_before_sd_read_or_init')
        needle = 'REG32(XINYI_WHOLE_BANK_BASE+i)=0;\n        REG32((XINYI_WHOLE_BANK_BASE+i)|0x80000000u)=0;'
        require(loader.count(needle) == 1, 'Known bank page-tail clear')
        (out/'negative-tail.c').write_text(loader.replace(needle,'(void)i;'),newline='\n')
        host_link('tail-negative', out/'negative-tail.c')
        test('pass', 'tail-negative', binary=out/'tail-negative-test', expect=b'bank reserved tail zeros')
        result['negative_controls'].append('omitted_tail_zeroing_detected_at_real_jump')
        require(all(file_identity(Path(n)) == v for n,v in source_hash.items()), 'Compiled source drift during tests')
        require(all(file_identity(Path(n)) == v for n,v in m['source_inputs'].items()), 'Prepared source drift during tests')
        result.update(status='PN18_EIGHT_PAYLOAD_HOST_SAME_GCC16_RV32_DTB_PASS_NOT_BOARD',
            candidate_manifest=file_identity(c/'manifest.json'), compiled_source_inputs=source_hash,
            bank=m['whole_voice'], fixture_bytes=fixture.stat().st_size,
            limitations=['Regular-file FAT, synthetic MMIO and separate mapped cached/uncached aliases only.',
                'Linux boot, allocation headroom, new xqboot entry and audio latency require board validation.'])
    except Exception as e:
        result.update(status='PN18_OFFLINE_CHECK_FAILED_PRESERVED', error=repr(e)); raise
    finally:
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'], 'tests='+str(len(result['tests'])))


if __name__ == '__main__': main()
