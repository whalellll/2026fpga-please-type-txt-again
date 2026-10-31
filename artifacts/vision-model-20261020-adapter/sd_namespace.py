"""Picture_new SD payload names, content binding and compiled-loader checks.

Only deployment copies receive new names. Training inputs and runtime paths in
each private rootfs remain unchanged. No function in this module writes media.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import zlib

REPO = Path(__file__).resolve().parents[2]
PROFILE = 'picture-new-sd-namespace-v1'
E8 = 'e8a037fa676e10f31a994b2f67d35a458586a6669c61800ace53e9edacb97b45'
CPU80_CONV = '30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1'
ENTRY = 0x01000000
ROLES = {
    'sbi': ('brfw.bin', 'SBI.BIN', 'PICTURE_SBI', 0x18000000),
    'kernel': ('Image', 'K.BIN', 'PICTURE_KERNEL', 0x00400000),
    'rootfs': ('brfs2.bin', 'FS.BIN', 'PICTURE_INITRD', 0x03000000),
    'dtb': ('br.dtb', '.DTB', 'PICTURE_DTB', 0x1a000000),
    'nnue': ('pikafish.pff', 'NN.PFF', 'PICTURE_NNUE', 0x10000000),
    'attack': ('pikafish.atk', 'ATK.BIN', 'PICTURE_ATTACK', 0x15000000),
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), crc32=f'{zlib.crc32(data):08x}')


def names(prefix):
    # PN is reserved for Picture_new; four characters leave room for BOOT.
    if not re.fullmatch(r'PN[0-9A-Z]{2}', prefix):
        raise ValueError('Picture_new prefix must be PN plus two uppercase letters/digits, e.g. PN01')
    result = {role: prefix + fields[1] for role, fields in ROLES.items()}
    result['loader'] = prefix + 'BOOT.BIN'
    if any(not re.fullmatch(r'[A-Z0-9]{1,8}\.[A-Z0-9]{1,3}', name) for name in result.values()):
        raise ValueError('All deployment names must be FAT short names')
    return result


def check_file(path, item):
    actual = identity(path)
    if any(actual[key] != item[key] for key in ('bytes', 'sha256', 'crc32')):
        raise ValueError(f'Payload identity mismatch: {Path(path).name}')
    return actual


def stage(ram, output, prefix='PN01'):
    ram, output = Path(ram).resolve(), Path(output).resolve()
    layout = names(prefix)
    if output.exists() or not output.is_relative_to((REPO / 'build').resolve()):
        raise ValueError('Choose a fresh directory inside build/')
    contract_path = ram / 'sd_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    cpu80=(contract.get('fixed_sbit_sha256')==CPU80_CONV and
           contract.get('hardware_profile')=='cpu80-conv-34338722' and
           contract.get('cpu_hz')==80000000 and contract.get('sys_hz')==49500000)
    if contract.get('fixed_sbit_sha256') != E8 and not cpu80:
        raise ValueError('Expected the unchanged E8 hardware candidate')
    if set(contract['files']) != {fields[0] for fields in ROLES.values()}:
        raise ValueError('Expected exactly the six canonical native RAM payloads')
    sources = {}
    for role, (canonical, _, _, _) in ROLES.items():
        item = contract['files'][canonical]
        path = Path(item['path'])
        if not path.is_absolute():
            path = REPO / path
        check_file(path, item)
        sources[role] = path
    output.mkdir(parents=True)
    files = {}
    header = '/* Picture_new private SD names; generated from sd_contract.json. */\n'
    for role, (canonical, _, macro, _) in ROLES.items():
        target = output / layout[role]
        shutil.copyfile(sources[role], target)
        files[target.name] = check_file(target, contract['files'][canonical])
        item = files[target.name]
        header += (f'#define {macro}_NAME "{target.name}"\n'
                   f'#define {macro}_BYTES {item["bytes"]}u\n'
                   f'#define {macro}_CRC 0x{item["crc32"]}u\n')
    result = dict(contract)
    result.update(scope='Picture_new private SD deployment candidate; NOT BoardRelease',
                  format_profile=PROFILE, files=files, uart_kernel=False,
                  sd_written=False, flash_written=False, board_validated=False,
                  cold_boot_board_validated=False, source_contract_sha256=sha(contract_path),
                  deployment=dict(prefix=prefix, layout=layout, loader_entry=ENTRY,
                                  boot_method='sd-resident-menu-then-private-sd-payloads',
                                  shared_sd_dependencies=[], shared_sd_files_replaced=[],
                                  create_only=True))
    (output / 'picture_payloads.h').write_text(header, encoding='ascii')
    (output / 'sd_contract.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def verify_compiled_loader(candidate, contract):
    candidate = Path(candidate)
    deployment = contract['deployment']
    layout = names(deployment['prefix'])
    if contract.get('format_profile') != PROFILE or deployment['layout'] != layout:
        raise ValueError('Namespace contract mismatch')
    if deployment.get('shared_sd_dependencies') or deployment.get('shared_sd_files_replaced'):
        raise ValueError('Private deployment cannot depend on or replace shared SD files')
    if set(contract['files']) != {layout[role] for role in ROLES}:
        raise ValueError('Private deployment must contain exactly six payloads')
    elf = (candidate / 'loader-picture-candidate.elf').read_bytes()
    if (elf[:7] != b'\x7fELF\x01\x01\x01' or len(elf) < 52
            or struct.unpack_from('<H', elf, 18)[0] != 243
            or struct.unpack_from('<I', elf, 24)[0] != ENTRY
            or struct.unpack_from('<I', elf, 36)[0] != 0):
        raise ValueError('Loader must be RV32 ELF, soft-float without RVC, at 0x01000000')
    binary = candidate / 'loader-picture-candidate.bin'
    raw = binary.read_bytes()
    if not raw or len(raw) > 0x100000 - 16384:
        raise ValueError('Loader exceeds its private RAM range')
    descriptors = {}
    for role, (_, _, _, address) in ROLES.items():
        name = layout[role]
        item = contract['files'][name]
        check_file(Path(item['path']), item)
        needle = struct.pack('<III', address, item['bytes'], int(item['crc32'], 16))
        if raw.count(needle) != 1:
            raise ValueError(f'Loader descriptor absent or ambiguous: {name}')
        offset = raw.index(needle)
        if offset < 4:
            raise ValueError(f'Invalid loader filename pointer: {name}')
        pointer = struct.unpack_from('<I', raw, offset - 4)[0] - ENTRY
        if not 0 <= pointer < len(raw) or raw[pointer:pointer+len(name)+1] != name.encode() + b'\0':
            raise ValueError(f'Loader names a different payload: {name}')
        descriptors[name] = dict(role=role, address=hex(address), bytes=item['bytes'], crc32=item['crc32'])
    return binary, descriptors
