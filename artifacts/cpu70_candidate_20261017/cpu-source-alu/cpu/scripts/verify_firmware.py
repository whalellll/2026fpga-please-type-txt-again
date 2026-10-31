"""Check CoreMark source/recipe and artifact bindings without building firmware."""
import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

ROOT = Path(os.path.abspath(__file__)).parent.parent
OUTPUTS = ('coremark.elf', 'coremark.bin', 'ram.hex', 'macros.txt',
           'coremark_build_config.h')
FIXED_INPUTS = ('coremark_test_soc/sw/start.S', 'coremark_test_soc/sw/link.ld',
                'scripts/build_coremark.ps1',
                'coremark_test_soc/sw/coremark/upstream.json')


def unlinked(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise SystemExit('Linked firmware input: ' + str(path))
    return info


def regular(root, relative):
    if (not isinstance(relative, str) or not relative or
            re.search(r'[\\<>:"|?*]', relative) or
            any(not part or part in ('.', '..') or part.endswith((' ', '.'))
                for part in relative.split('/'))):
        raise SystemExit('Noncanonical firmware manifest path: ' + str(relative))
    # No absolute path, parent segment or link can redirect this traversal.
    current = root
    unlinked(current)
    for part in relative.split('/'):
        current = current / part
        unlinked(current)
    if not current.is_file():
        raise SystemExit('Firmware input is not a regular file: ' + relative)
    return current


def source_inputs():
    inputs = set(FIXED_INPUTS)
    pending = [ROOT / 'coremark_test_soc/sw/coremark']
    while pending:
        directory = pending.pop()
        unlinked(directory)
        for path in directory.iterdir():
            unlinked(path)
            if path.is_dir():
                pending.append(path)
            elif path.suffix.lower() in ('.c', '.h'):
                inputs.add(path.relative_to(ROOT).as_posix())
    return inputs


def check_map(mapping, expected, root, label):
    if not isinstance(mapping, dict) or not mapping:
        raise SystemExit('Missing or invalid ' + label + ' map')
    if set(mapping) != set(expected):
        raise SystemExit(label + ' file set changed; rebuild firmware')
    for name, digest in mapping.items():
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise SystemExit('Invalid SHA256 in ' + label + ': ' + name)
        path = regular(root, name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest.lower():
            raise SystemExit(label + ' changed: ' + name + '; rebuild firmware')


def verify(directory):
    directory = Path(os.path.abspath(directory))
    manifest = json.loads(regular(directory, 'manifest.json').read_text(encoding='utf-8-sig'))
    if type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 3:
        raise SystemExit('Unsupported firmware manifest; rebuild with scripts/build_coremark.ps1')
    if (manifest.get('run_mode') not in ('performance', 'validation') or
            manifest.get('evidence_class') not in ('calibration', 'formal_candidate') or
            manifest.get('tick_report') != 'PORT_TICKS64' or
            manifest.get('coremark_upstream') != 'cfa9ab377835911f23d9b0831c7be302ed1f58de' or
            manifest.get('coremark_sim') is not False):
        raise SystemExit('Firmware must use official CoreMark seeds, unmodified time checks and PORT_TICKS64')
    if ((manifest.get('isa'), manifest.get('march'), manifest.get('abi'),
         manifest.get('compressed_instructions'), manifest.get('compiler_target')) !=
            ('rv32ima', 'rv32ima_zicsr_zifencei', 'ilp32', 0, 'riscv32-unknown-elf') or
            type(manifest.get('compressed_instructions')) is not int or
            manifest.get('optimization') not in ('-O2', '-O3')):
        raise SystemExit('Unexpected firmware ISA, ABI, compiler target or optimization')
    for name, maximum in (('cpu_hz', 1000000000), ('iterations', 2147483647)):
        if type(manifest.get(name)) is not int or not 1 <= manifest[name] <= maximum:
            raise SystemExit('Invalid firmware ' + name)
    seed1 = 0x3415 if manifest['run_mode'] == 'validation' else 0
    expected_seeds = {'seed1': seed1, 'seed2': seed1, 'seed3': 0x66,
                      'seed4': manifest['iterations'], 'seed5': 0}
    if manifest.get('seeds') != expected_seeds or manifest.get('total_data_size_bytes') != 2000:
        raise SystemExit('Firmware seed tuple or TOTAL_DATA_SIZE is wrong')
    check_map(manifest.get('source_files'), source_inputs(), ROOT, 'Firmware source/recipe/upstream')
    check_map(manifest.get('files'), OUTPUTS, directory, 'Firmware output')
    definitions = {
        'ITERATIONS': str(manifest['iterations']),
        'PERFORMANCE_RUN': str(int(manifest['run_mode'] == 'performance')),
        'VALIDATION_RUN': str(int(manifest['run_mode'] == 'validation')),
        'PROFILE_RUN': '0', 'CORE_CLOCKS_PER_SEC': str(manifest['cpu_hz']) + 'ULL',
        'COMPILER_VERSION': '"GCC ' + str(manifest.get('compiler_version')) + ' (riscv32-unknown-elf)"',
        'COMPILER_FLAGS': '"' + str(manifest.get('compiler_flags')) + '"',
    }
    for filename in ('coremark_build_config.h', 'macros.txt'):
        text = regular(directory, filename).read_text(encoding='utf-8-sig')
        required = dict(definitions)
        if filename == 'macros.txt':
            required['TOTAL_DATA_SIZE'] = '2*1000'
        for name, expected in required.items():
            values = re.findall(r'^#define\s+' + name + r'\s+([^\r\n]+)', text, re.MULTILINE)
            if values != [expected]:
                raise SystemExit('Firmware manifest disagrees with ' + filename + ': ' + name)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        verify(args.directory)
    except (OSError, ValueError) as error:
        raise SystemExit('Firmware input check failed: ' + str(error)) from error
    print('FIRMWARE_INPUTS_PASS')


if __name__ == '__main__':
    main()
