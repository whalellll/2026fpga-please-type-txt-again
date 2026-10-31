"""Build a new PN18 full SD directory, DT reservation and eight-payload loader.

Only private regular files are read/written. No card, UART, JTAG, kernel or RTL
is accessed. PN15 and its original13 files remain immutable input evidence.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shutil
import struct
import subprocess
import zlib

from picture_workspace import ROOT, workspace_path
from prepare_xinyi_cpu60_kit import identity, require, cpio_read, cpio_write, elf32
from prepare_picture_candidate import tokens

PN15_MANIFEST = '93aff64baee78448846d5507c7bc5906df9a906f4933b5fe7447c6e929304c72'
E42 = 'e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b'
BANK_BASE, BANK_LIMIT, PAGE = 0x04000000, 0x0f000000, 4096
BANK_NODE = '/reserved-memory/xinyi-whole-voice@4000000'
CONFIG_PATH = 'opt/xq-picture/pcm/whole-bank.cfg'
ALLOWED = {'usr/bin/xinyi-one', 'usr/bin/xinyi-speech-worker', 'usr/bin/xqvoice-small-cnn',
           'usr/bin/xinyi-engine', CONFIG_PATH, 'opt/xq-picture/pcm/whole-bank-manifest.json'}
REQUIRED = {'usr/bin/xinyi-one', 'usr/bin/xinyi-speech-worker', 'usr/bin/xqvoice-small-cnn', CONFIG_PATH}
SHA = lambda data: hashlib.sha256(data).hexdigest()


def file_identity(path):
    sha, crc, count = hashlib.sha256(), 0, 0
    with Path(path).open('rb') as stream:
        while data := stream.read(1024 * 1024):
            sha.update(data); crc = zlib.crc32(data, crc); count += len(data)
    return dict(bytes=count, sha256=sha.hexdigest(), crc32=f'{crc:08x}')


def reserve_voice_dtb(blob, initrd_bytes, bank_bytes, span):
    require(bank_bytes > 0 and span == (bank_bytes + PAGE - 1) & ~(PAGE - 1), 'Exact page reservation required')
    require(BANK_BASE + span < BANK_LIMIT, 'Voice reservation must end below0x0f000000')
    h, props, ends = tokens(blob)
    old = {n: v[0] for n, v in props.items()}
    require(old['/reserved-memory/#address-cells'] == struct.pack('>I', 1) and
            old['/reserved-memory/#size-cells'] == struct.pack('>I', 1) and
            old['/reserved-memory/ranges'] == b'', 'Frozen one-cell memory map required')
    require(old['/memory@0/reg'] == struct.pack('>II', 0, 0x1c000000), 'Unexpected advertised RAM')
    require(old['/cpus/timebase-frequency'] == struct.pack('>I', 60000000) and
            old['/cpus/cpu@0/clock-frequency'] == struct.pack('>I', 60000000), 'CPU60/TIME clock changed')
    require(0 < initrd_bytes <= 0x01000000 and old['/chosen/linux,initrd-start'] == struct.pack('>I', 0x03000000),
            'Frozen16MiB initrd window required')
    require(not any(n.startswith(BANK_NODE + '/') for n in old), 'Never silently replace a reservation')
    reservations = []
    for name, value in old.items():
        if name.startswith('/reserved-memory/') and name.endswith('/reg'):
            require(len(value) == 8, 'Unknown reserved memory encoding')
            base, size = struct.unpack('>II', value)
            require(not (base < BANK_BASE + span and BANK_BASE < base + size), 'Bank overlaps ' + name)
            reservations.append(dict(node=name[:-4], base=base, bytes=size))
    # The separate memreserve map is retained byte for byte and checked too.
    at = h[4]
    while True:
        address, length = struct.unpack_from('>QQ', blob, at); at += 16
        if not address and not length: break
        require(not (address < BANK_BASE + span and BANK_BASE < address + length), 'Bank overlaps memreserve map')
    structure = bytearray(blob[h[2]:h[2] + h[9]])
    struct.pack_into('>I', structure, props['/chosen/linux,initrd-end'][1], 0x03000000 + initrd_bytes)
    strings = bytearray(blob[h[3]:h[3] + h[8]])
    def prop(name, data):
        offset = len(strings); strings.extend(name.encode() + b'\0')
        return struct.pack('>III', 3, len(data), offset) + data + b'\0' * (-len(data) % 4)
    node = struct.pack('>I', 1) + BANK_NODE.rsplit('/', 1)[1].encode() + b'\0'
    node += b'\0' * (-len(node) % 4)
    node += prop('reg', struct.pack('>II', BANK_BASE, span)) + prop('no-map', b'') + struct.pack('>I', 2)
    structure[ends['/reserved-memory']:ends['/reserved-memory']] = node
    result = bytearray(blob[:h[2]]) + structure + strings
    updated = list(h)
    updated[1], updated[3], updated[8], updated[9] = len(result), h[2] + len(structure), len(strings), len(structure)
    struct.pack_into('>10I', result, 0, *updated)
    expected = dict(old)
    expected['/chosen/linux,initrd-end'] = struct.pack('>I', 0x03000000 + initrd_bytes)
    expected[BANK_NODE + '/reg'] = struct.pack('>II', BANK_BASE, span)
    expected[BANK_NODE + '/no-map'] = b''
    after = {n: v[0] for n, v in tokens(result)[1].items()}
    require(after == expected, 'Unexpected DT property mutation')
    require(result[40:h[2]] == blob[40:h[2]], 'Original memory reservation prefix changed')
    return bytes(result), reservations


def validate_bank(layout, bank, config):
    require(layout['schema'] == 'xinyi-whole-sd-bank/1' and
            layout['status'] == 'PACKED_AND_REOPENED_ALL5103_CRC_SHA_PASS_NOT_INSTALLED', 'Unverified bank manifest')
    require(layout['physical_base'] == BANK_BASE and layout['reserved_end'] == BANK_BASE + layout['reserved_span'] and
            layout['filename'] == 'P18VOICE.BIN' and layout['dt_node'] == BANK_NODE, 'Wrong sidecar assignment')
    info = file_identity(bank)
    require(info == {k: layout[k] for k in ['bytes', 'sha256', 'crc32']}, 'Bank file identity mismatch')
    size, span = info['bytes'], layout['reserved_span']
    require(span == ((size + PAGE - 1) & ~(PAGE - 1)) and BANK_BASE + span < BANK_LIMIT, 'Invalid bank aperture')
    require(len(config) == 96 and SHA(config) == layout['config_sha256'] and config[:8] == b'XQWBCFG1', 'Wrong96-byte cfg')
    le = lambda data, at: struct.unpack_from('<I', data, at)[0]
    require([le(config, at) for at in [8, 12, 16, 20, 24, 28]] ==
            [1, BANK_BASE, span, size, int(layout['header_index_crc32'], 16), 5103], 'Cfg disagrees with sidecar')
    cfg = bytearray(config); wanted = le(cfg, 64); struct.pack_into('<I', cfg, 64, 0)
    require(zlib.crc32(cfg) == wanted and not any(config[68:]), 'Cfg CRC/reserved bytes mismatch')
    require(config[32:64] == bytes.fromhex(layout['source_manifest_sha256']), 'Cfg source manifest mismatch')
    with Path(bank).open('rb') as f: meta = bytearray(f.read(81920))
    require(len(meta) == 81920 and meta[:8] == b'XQWBANK1', 'Missing bank metadata')
    require([le(meta, at) for at in range(8, 48, 4)] ==
            [1, 128, 16000, 1, 1, 5103, 128, 16, 81920, size], 'Bank header mismatch')
    require(meta[56:88] == config[32:64] and not any(meta[88:128]) and not any(meta[81776:81920]), 'Bank reserved bytes mismatch')
    require(zlib.crc32(meta[128:81776]) == le(meta, 48) == int(layout['index_crc32'], 16), 'Index CRC mismatch')
    wanted = le(meta, 52); struct.pack_into('<I', meta, 52, 0)
    require(zlib.crc32(meta[:81776]) == wanted == le(config, 24), 'Header/index CRC mismatch')
    end, previous = 81920, b''
    require(len(layout['clips']) == 5103, 'Missing clip metadata')
    for i, clip in enumerate(layout['clips']):
        at = 128 + 16 * i; key = bytes(meta[at:at+4]); offset, length, crc = struct.unpack_from('<III', meta, at+4)
        require(key > previous and list(key) == clip['tokens'] and offset == end == clip['offset'] and
                length == clip['bytes'] and 0 < length <= 30720 and not length % 2 and
                f'{crc:08x}' == clip['crc32'] and offset + length <= size, 'Invalid clip index')
        end = (offset + length + 3) & ~3; previous = key
    require(end == size, 'Bank index is not closed')
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['pn15', 'bank-layout', 'replacements', 'output']:
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--plumbing-only', action='store_true', help='Explicit unselected loader/DT fixture; not a software delivery')
    a = ap.parse_args(); logical = a.output.absolute()
    require(logical.is_relative_to(ROOT / 'build'), 'Use private build junction')
    out = workspace_path(a.output)
    require(out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve()), 'Use existing E junction')
    require(not out.exists(), 'Never overwrite earlier output'); out.mkdir(parents=True)
    inputs = {}
    def read(path):
        path = workspace_path(path); data = path.read_bytes(); info = identity(data)
        require(str(path) not in inputs or inputs[str(path)] == info, 'Input changed between reads')
        inputs[str(path)] = info; return data
    def save(path, data):
        require(not path.exists(), 'Never replace output: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    def record(path, value): save(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())
    base_dir = workspace_path(a.pn15)
    base_bytes = read(base_dir / 'manifest.json'); require(SHA(base_bytes) == PN15_MANIFEST, 'Exact original PN15 required')
    base = json.loads(base_bytes)
    require(base['prefix'] == 'PN15' and base['target_bitstream_sha256'] == E42 and len(base['full_sd_files']) == 13,
            'Wrong complete baseline')
    baseline = {}
    for name, expected in base['full_sd_files'].items():
        data = read(base_dir / 'sd-full' / name); require(identity(data) == expected, 'Baseline SD drift: ' + name)
        baseline[name] = data
    layout_data = read(a.bank_layout); layout = json.loads(layout_data)
    bank = workspace_path(Path(layout['bank_path'])); cfg = read(Path(layout['config_path']))
    bank_identity = validate_bank(layout, bank, cfg); inputs[str(bank)] = bank_identity
    change_data = read(a.replacements); document = json.loads(change_data)
    replacements = document.get('replacements', document)
    require(set(replacements) <= ALLOWED and (a.plumbing_only or REQUIRED <= set(replacements)), 'Unselected rootfs replacement')
    require(document.get('cpu_hz', 60000000) == 60000000, 'CPU60 delivery only')
    replacements = dict(replacements)
    if CONFIG_PATH not in replacements:
        replacements[CONFIG_PATH] = dict(file=str(Path(layout['config_path'])), sha256=SHA(cfg), mode=0o100644)
    original = cpio_read(baseline['PN04FS.BIN']); merged = dict(original)
    merged.update(cpio_read(gzip.decompress(baseline['PN15UPD.GZ'])))
    inherited = dict(merged); next_inode = max(v[0][0] for v in merged.values()) + 1
    def replace(name, data, mode):
        nonlocal next_inode
        require(name and not name.startswith('/') and '..' not in Path(name).parts, 'Unsafe rootfs path')
        for parent in reversed(Path(name).parents):
            key = parent.as_posix()
            if key != '.' and key not in merged:
                merged[key] = ([next_inode, 0o40755, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0], b''); next_inode += 1
        if name in merged:
            fields = merged[name][0].copy(); require(fields[4] == 1, 'Do not replace hard links')
            fields[1] = mode
        else:
            fields = [next_inode, mode, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]; next_inode += 1
        merged[name] = (fields, data)
    selected = {}
    for name, row in replacements.items():
        file = Path(row.get('file', row.get('path', '')))
        data = read(file); require(SHA(data) == row['sha256'], 'Replacement SHA mismatch: ' + name)
        if 'bytes' in row: require(len(data) == row['bytes'], 'Replacement size mismatch')
        default_mode = 0o100755 if name.startswith('usr/bin/') else 0o100644
        mode = row.get('mode', default_mode)
        if isinstance(mode, str): mode = int(mode, 8)
        require(mode == default_mode, 'Unexpected file mode')
        if name.startswith('usr/bin/'): elf32(data, name)
        if name == CONFIG_PATH: require(data == cfg, 'Selected cfg differs from reserved bank')
        replace(name, data, mode); selected[name] = SHA(data)
    sums = {}
    for line in inherited['opt/xinyi/runtime.sha256'][1].decode().splitlines():
        h, path = line.split('  ', 1); sums[path] = h
    for name in replacements: sums['/' + name] = SHA(merged[name][1])
    replace('opt/xinyi/runtime.sha256', ''.join(h + '  ' + n + '\n' for n, h in sorted(sums.items())).encode(), 0o100644)
    for name, h in sums.items(): require(SHA(merged[name.lstrip('/')][1]) == h, 'Runtime manifest closure')
    for name, content in inherited.items():
        if name not in replacements and name != 'opt/xinyi/runtime.sha256':
            require(merged[name] == content, 'Inherited rootfs changed: ' + name)
    require(merged['usr/bin/xq-coach-worker'] == inherited['usr/bin/xq-coach-worker'] and
            merged['opt/xinyi/models.sha256'] == inherited['opt/xinyi/models.sha256'], 'Frozen image/model drift')
    delta = {n: v for n, v in merged.items() if n not in original or original[n] != v}
    for name in list(delta):
        for parent in Path(name).parents:
            key = parent.as_posix()
            if key != '.' and key in merged: delta.setdefault(key, merged[key])
    overlay = gzip.compress(cpio_write(delta), compresslevel=9, mtime=0)
    check = dict(original); check.update(cpio_read(gzip.decompress(overlay)))
    require(check == merged, 'Overlay round-trip mismatch')
    offset = base['overlay_offset']; initrd_bytes = offset + len(overlay)
    require(initrd_bytes <= 0x01000000, 'No large PCM may enter initrd')
    dtb, reservations = reserve_voice_dtb(baseline['PN15.DTB'], initrd_bytes, layout['bytes'], layout['reserved_span'])
    entries = [(n, addr, baseline[n]) for n, addr in [('PN04SBI.BIN', 0x18000000), ('PN04FS.BIN', 0x03000000),
        ('PN04NN.PFF', 0x10000000), ('PN04ATK.BIN', 0x15000000), ('PN08K.BIN', 0x00400000)]]
    entries.extend([('PN18.DTB', 0x1a000000, dtb), ('PN18UPD.GZ', 0x03000000 + offset, overlay)])
    support = out / 'support'
    for file in sorted((base_dir / 'support').rglob('*')):
        if file.is_file() and file.name not in ['payloads.h', 'loader.c']:
            save(support / file.relative_to(base_dir / 'support'), read(file))
    save(support / 'loader.c', read(ROOT / 'linux/xinyi_board/boot/loader_pn18.c'))
    header = ('#include "fat_ro.h"\n#define XINYI_BOOT_PREFIX "PN18"\n#define XINYI_ROOTFS_OVERLAY 1\n'
        f'#define XINYI_ROOTFS_BASE_BYTES {base["rootfs_base_bytes"]}u\n#define XINYI_ROOTFS_OVERLAY_OFFSET {offset}u\n'
        f'#define XINYI_WHOLE_BANK_BASE 0x{BANK_BASE:08x}u\n#define XINYI_WHOLE_BANK_BYTES {layout["bytes"]}u\n'
        f'#define XINYI_WHOLE_BANK_SPAN {layout["reserved_span"]}u\n#define XINYI_WHOLE_BANK_INDEX 7u\n'
        'typedef struct {const char *name;uint32_t address,bytes,crc32;fat_ro_file_t file;} payload_t;\nstatic payload_t payloads[]={\n')
    payload_records = []
    for name, address, data in entries:
        info = identity(data); save(out / 'payloads' / name, data)
        payload_records.append(dict(name=name, address=address, **info))
    payload_records.append(dict(name='P18VOICE.BIN', address=BANK_BASE, **bank_identity))
    for row in payload_records:
        header += f'{{"{row["name"]}",0x{row["address"]:08x}u,{row["bytes"]}u,0x{row["crc32"]}u,{{0}}}},\n'
    header += '};\n#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))\n'
    save(support / 'payloads.h', header.encode())
    (out / 'payloads').mkdir(exist_ok=True)
    shutil.copyfile(bank, out / 'payloads/P18VOICE.BIN')
    require(file_identity(out / 'payloads/P18VOICE.BIN') == bank_identity, 'Bank copy mismatch')
    for n in ['scripts/prepare_picture_pn18.py', 'scripts/prepare_picture_candidate.py',
              'scripts/prepare_xinyi_cpu60_kit.py', 'scripts/build_xinyi_cpu60_loader.ps1',
              'scripts/riscv_toolchain.ps1', 'scripts/picture_workspace.py']: read(ROOT / n)
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT / 'scripts/build_xinyi_cpu60_loader.ps1'), '-CandidateDirectory', str(logical), '-Prefix', 'PN04']
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=180)
    save(out / 'evidence/loader-build.log', proc.stdout + proc.stderr)
    require(proc.returncode == 0, 'PN18 loader GCC16 failed')
    binary = read(out / 'PN04BOOT.BIN')
    for row in payload_records:
        needle = struct.pack('<III', row['address'], row['bytes'], int(row['crc32'], 16))
        require(binary.count(needle) == 1, 'Loader descriptor mismatch')
        at = binary.index(needle); pointer = struct.unpack_from('<I', binary, at-4)[0] - 0x01000000
        require(binary[pointer:pointer+len(row['name'])+1] == row['name'].encode() + b'\0', 'Loader filename mismatch')
    for file in sorted(support.rglob('*')):
        if file.is_file(): read(file)
    update = {'PN18.DTB': dtb, 'PN18UPD.GZ': overlay, 'PN18BOOT.BIN': binary}
    public = dict(schema='picture-pn18/1', prefix='PN18',
        status='PN18_PLUMBING_ONLY_UNSELECTED' if a.plumbing_only else 'PN18_OFFLINE_FULL_SD_PREPARED_NOT_INSTALLED',
        target_bitstream_sha256=E42, cpu_hz=60000000, sys_hz=49500000,
        base_pn15_manifest_sha256=PN15_MANIFEST, kernel_filename='PN08K.BIN', kernel_sha256=base['kernel_sha256'],
        kernel_changed=False, rtl_changed=False, image_model_and_worker_unchanged=True,
        estimated_board_recommendations_preserved=True, selected_rootfs_sha256=selected,
        rootfs_base_bytes=base['rootfs_base_bytes'], overlay_offset=offset, overlay_bytes=len(overlay),
        rootfs_bound_bytes=initrd_bytes, rootfs_aperture_bytes=0x01000000,
        whole_voice=dict(filename='P18VOICE.BIN', base=BANK_BASE, bytes=layout['bytes'],
            span=layout['reserved_span'], end=BANK_BASE+layout['reserved_span'], **{'crc32':layout['crc32'],'sha256':layout['sha256']}),
        original_reserved_memory=reservations, payloads=payload_records, payload_count=8,
        hardware_used=False, sd_written=False, flash_written=False, selector_modified=False,
        standalone_boot_tested=False, physical_audio_1000ms_pass=False,
        linux_memory_effect_unmeasured=dict(reserved_kib=layout['reserved_span']//1024,
            historical_memtotal_kib=307784, subtraction_only_memtotal_kib=307784-layout['reserved_span']//1024),
        previous_entry_backup='PN15XQ.BIN', previous_entry_backup_scope='Original PN15 package entry, not a backup of a currently attached card')
    update['PN18.JSN'] = (json.dumps(public, ensure_ascii=False, indent=2)+'\n').encode()
    update['PN18SRC.JSN'] = (json.dumps(dict(selected_rootfs_sha256=selected, bank_layout_sha256=SHA(layout_data),
        replacements_manifest_sha256=SHA(change_data), input_files=inputs), ensure_ascii=False, indent=2)+'\n').encode()
    checks = {name: identity(data) for name, data in update.items()}
    checks['P18VOICE.BIN'] = bank_identity
    update['PN18.SHA'] = ''.join(v['sha256']+'  '+n+'\n' for n,v in sorted(checks.items())).encode()
    for name, data in update.items(): save(out/'sd-update'/name, data)
    shutil.copyfile(bank, out/'sd-update/P18VOICE.BIN')
    full = dict(baseline); full['PN15XQ.BIN'] = baseline['xiangqi.bin']; full['xiangqi.bin'] = binary; full.update(update)
    for name, data in full.items(): save(out/'sd-full'/name, data)
    shutil.copyfile(bank, out/'sd-full/P18VOICE.BIN')
    public['new_sd_files'] = {f.name:file_identity(f) for f in (out/'sd-update').iterdir()}
    public['full_sd_files'] = {f.name:file_identity(f) for f in (out/'sd-full').iterdir()}
    require(len(public['full_sd_files']) == 21, 'Unexpected complete SD file set')
    for name, expected in base['full_sd_files'].items():
        target = out/'sd-full'/('PN15XQ.BIN' if name=='xiangqi.bin' else name)
        require(file_identity(target) == expected, 'Old PN15 payload not preserved')
    require(all(file_identity(Path(n)) == value for n,value in inputs.items()), 'Source drift during build')
    public['source_inputs'] = inputs
    record(out/'manifest.json', public)
    save(out/'README.txt', ('PN18 full SD contents are in sd-full/. This directory contains the complete old PN15 resources,\n'
        'a new eight-payload loader and an uncompressed whole-voice sidecar. No kernel/RTL/Flash change.\n'
        'ROM console xqboot reads xqmodel.bin then xiangqi.bin. The new entry selects PN18.DTB/PN18UPD.GZ/P18VOICE.BIN.\n'
        'The voice bank is loaded and full-CRC checked before Linux, then excluded from allocation by exact DT no-map.\n'
        'Do not load this bank into an unreserved running Linux RAM range. Linux available memory will decrease.\n'
        'PN15XQ.BIN is only the old entry from the original package. Back up the actual on-card entry separately before replacing it.\n'
        'No card is written by this preparation tool. Existing PN04/PN08/PN15 files must remain available for rollback.\n'
        'New Linux boot, UI/recognition resource headroom and physical audio completion still require board validation.\n').encode())
    print(public['status'], 'files=21', 'bank_bytes='+str(layout['bytes']), 'initrd_bytes='+str(initrd_bytes))


if __name__ == '__main__':
    main()
