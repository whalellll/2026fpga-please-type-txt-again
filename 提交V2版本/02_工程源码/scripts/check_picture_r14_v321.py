"""Check immutable r14 80B1 CRC/SHA through a V321 mock, on host and RV32 QEMU.

Only synthetic-inputs-r01 and its hash-pinned real model packs are accepted.
The mock is an independent CPU implementation of the hardware raw-dot contract;
this proves software transport/numerics, never real kernel, FPGA or accuracy.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import re
import shlex
import struct
import subprocess
import tarfile
import uuid

R = Path(__file__).resolve().parents[1]
ADAPTER = 'artifacts/vision-model-20261020-adapter/runtime'
CORE = ['linux/picture_new/vision32_backend.c', 'linux/picture_new/vision32_layer.c',
        'linux/mac_accel/pango_mac_uapi.h']
SOURCES = ['linux/picture_new/test_v321_golden.c', 'linux/picture_new/test_v321_mock.c',
           'linux/picture_new/vision32_backend.c', 'linux/picture_new/vision32_layer.c',
           ADAPTER+'/xq_native_graph.c', ADAPTER+'/xq_sha256.c', 'sw/bootloader/crc32_fast.c']
INCLUDES = [ADAPTER, 'linux/picture_new', 'linux/vision', 'linux/mac_accel', 'sw/bootloader']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compare(expected, payload):
    lines = payload.decode('ascii').splitlines()
    assert lines[0] == 'XQ_NATIVE_CHECKS_V1'
    rows = []
    for line in lines[1:]:
        fields = line.split()
        assert len(fields) == 11
        rows.append([*map(int, fields[:3]), *[int(x, 16) for x in fields[3:7]], *fields[7:]])
    assert len(rows) == 80 and sorted(row[0] for row in rows) == list(range(80))
    assert rows == expected['rows'], '80-layer four-tensor CRC/SHA mismatch'
    return dict(layers=80, tensors_per_layer=4, crc_and_sha_equal=True, checks_sha256=sha(payload))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--models', type=Path, default=R/'build/picture-merge-20261023/native-models')
    p.add_argument('--inputs', type=Path, default=R/'build/picture-board-resume-20261023/synthetic-inputs-r01')
    p.add_argument('--distribution', default='Ubuntu-22.04')
    p.add_argument('--timeout-seconds', type=int, default=3600)
    p.add_argument('--targets', choices=['host', 'host,qemu'], default='host,qemu')
    p.add_argument('--source-ref', help='Optional read-only Git core/UAPI overlay before software intake; runtime remains current r14.')
    a = p.parse_args()
    out = a.output.resolve()
    assert out.is_relative_to(R/'build') and not out.exists()
    assert 60 <= a.timeout_seconds <= 7200
    expected_raw = (a.inputs/'expected.json').read_bytes()
    expected = json.loads(expected_raw)
    assert len(expected['rows']) == 80
    assert expected['synthetic_input_manifest_sha256'] == sha((a.inputs/'manifest.json').read_bytes())
    input_manifest = json.loads((a.inputs/'manifest.json').read_text(encoding='utf-8'))
    assert 'no photographs' in input_manifest['scope'] and len(input_manifest['models']) == 3
    files = set(SOURCES+[ADAPTER+'/xq_int8_layer.c', 'linux/picture_new/test_v321_mock.h',
                         'linux/picture_new/graph_profile.h',
                         'sw/bootloader/crc32_fast.h', 'linux/vision/xq_mac.h'])
    files.update(p.relative_to(R).as_posix() for p in (R/ADAPTER).glob('*.h'))
    files.add('linux/mac_accel/pango_mac_uapi.h')
    if not a.source_ref:
        files.update(['linux/picture_new/whole_layer_fast/vision32_layer.c',
            'linux/picture_new/vision32_locality.c',
            'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
            'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h'])
    data = {name: (R/name).read_bytes() for name in files if name not in CORE or not a.source_ref}
    core_ref = None
    if a.source_ref:
        core_ref = subprocess.check_output(['git', 'rev-parse', a.source_ref], cwd=R, text=True).strip()
        for name in CORE:
            data[name] = subprocess.check_output(['git', 'show', core_ref+':'+name], cwd=R)
        name = 'linux/picture_new/vision32_layer.c'
        old = b'"upstream/adapter/runtime/xq_int8_layer.c"'
        new = b'"../../artifacts/vision-model-20261020-adapter/runtime/xq_int8_layer.c"'
        assert data[name].count(old) == 1
        data[name] = data[name].replace(old, new)
    assert all(name in data for name in SOURCES)
    source_hashes = {name: sha(blob) for name, blob in data.items()}
    current_hashes = {name: sha((R/name).read_bytes()) for name in files if name not in CORE or not a.source_ref}
    current_hashes[Path(__file__).relative_to(R).as_posix()] = sha(Path(__file__).read_bytes())
    fixture = {}
    for index, name in enumerate(['board', 'detector', 'classifier']):
        model = (a.models/(name+'.xqm')).read_bytes()
        assert sha(model) == expected['model_pack_sha256'][name], 'r14 model identity mismatch: '+name
        raw = (a.inputs/(name+'.input')).read_bytes()
        assert sha(raw) == input_manifest['models'][index]['sha256']
        assert input_manifest['models'][index]['model'] == name
        fixture['models/'+name+'.xqm'] = model
        fixture['inputs/'+name+'.input'] = raw
    fixture_hashes = {name: sha(blob) for name, blob in fixture.items()}
    out.mkdir(parents=True)
    native = '/var/tmp/picture-r14-v321-'+uuid.uuid4().hex
    quote = shlex.quote
    # Discard unused legacy graph pin API: resident.c owns the dense xqm_matrix
    # symbol and must never override the V321 backend in this executable.
    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
             '-ffunction-sections', '-fdata-sections']
    flags += ['-I'+native+'/'+directory for directory in INCLUDES]
    sources = [native+'/'+name for name in SOURCES]
    script = ['set -eu', 'export PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin',
              'command -v gcc', 'test -x /opt/toolchain/bin/riscv32-linux-musl-gcc',
              '/opt/toolchain/bin/riscv32-linux-musl-gcc -dumpmachine']
    targets = [('host', 'gcc', [])]
    if a.targets == 'host,qemu':
        script += ['command -v qemu-riscv32']
        targets.append(('qemu', '/opt/toolchain/bin/riscv32-linux-musl-gcc',
                        ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']))
    for target, cc, extra in targets:
        executable = native+'/out/golden-'+target
        script.append(shlex.join([cc, *flags, *extra, *sources, '-Wl,--wrap=ioctl', '-Wl,--gc-sections', '-lm', '-o', executable]))
        prefix = ['qemu-riscv32'] if target == 'qemu' else []
        for mode, suffix in [('--fail-second-ioctl', 'failure'), ('--mock-v321', 'checks')]:
            script.append(shlex.join([*prefix, executable, native+'/models', native+'/inputs',
                                      native+'/out/'+target+'-'+suffix+'.txt', mode]))
        if target == 'qemu':
            script.append('riscv32-linux-musl-readelf -h -A '+quote(executable)+' > '+quote(native+'/out/elf.txt'))
    build = ('\n'.join(script)+'\n').encode()
    (out/'build.sh').write_bytes(build)
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode='w') as archive:
        for name, blob in {**data, **fixture, 'build.sh': build}.items():
            item = tarfile.TarInfo(name);item.size = len(blob);item.mode = 0o644
            archive.addfile(item, io.BytesIO(blob))
    command = 'set -eu; test ! -e '+quote(native)+'; mkdir -p '+quote(native+'/out')
    command += '; tar -xf - -C '+quote(native)+'; timeout --kill-after=5 '+str(a.timeout_seconds)+' sh '+quote(native+'/build.sh')
    with (out/'build.log').open('wb') as log:
        process = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'sh', '-c', command],
                                 input=bundle.getvalue(), stdout=log, stderr=subprocess.STDOUT,
                                 timeout=a.timeout_seconds+60)
    log_data = (out/'build.log').read_bytes()
    assert process.returncode == 0, log_data.decode(errors='replace')[-5000:]
    returned = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'tar', '-cf', '-', '-C', native+'/out', '.'],
                              capture_output=True, check=True, timeout=60).stdout
    with tarfile.open(fileobj=io.BytesIO(returned)) as archive:
        for item in archive.getmembers():
            if not item.isfile():
                continue
            name = item.name.removeprefix('./')
            assert name and '/' not in name and '\\' not in name and name not in ('.', '..')
            (out/name).write_bytes(archive.extractfile(item).read())
    results = {}
    for target, _, _ in targets:
        results[target] = compare(expected, (out/(target+'-checks.txt')).read_bytes())
        assert log_data.count(b'V321_MOCK_IOCTL_ERROR_FATAL_PASS') == len(targets)
        models = re.findall(rb'V321_MOCK_MODEL_PASS model=(\w+) records=(\d+) jobs=(\d+) cycles=(\d+)', log_data)
        rows = models[len(results)*3-3:len(results)*3]
        # Job count is a performance-contract guard, separate from all four
        # tensor CRC/SHA checks above. P3 spatial halo tiles replace tiny jobs.
        detector_jobs=19444 if core_ref else 98
        assert [(n.decode(), int(count), int(jobs)) for n, count, jobs, _ in rows] == [
            ('board', 12, 44), ('detector', 60, detector_jobs), ('classifier', 8, 8)]
        results[target]['models'] = [dict(model=n.decode(), layers=int(count), jobs=int(jobs)) for n, count, jobs, _ in rows]
    if a.targets == 'host,qemu':
        elf = (out/'golden-qemu').read_bytes()
        assert elf[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', elf, 18)[0] == 243
        assert struct.unpack_from('<I', elf, 36)[0] == 0, 'RV32 soft-float/no compressed ELF required'
    assert all(sha((R/name).read_bytes()) == digest for name, digest in current_hashes.items())
    for name, blob in fixture.items():
        directory = a.models if name.startswith('models/') else a.inputs
        assert sha((directory/Path(name).name).read_bytes()) == sha(blob)
    result = dict(status='PASS', scope='r14 synthetic B1 full graphs; independent V321 ioctl mock on '+a.targets,
                  hardware_used=False, production_ready=False, accuracy_accepted=False,
                  numerical_contract='raw-I32 dot; CPU bias once, ties-even saturating S16, 65536-entry LUT',
                  no_cpu_graph_fallback=True, ioctl_error_fatal=True, source_stable=True,
                  software_core_ref=core_ref, core_overlay_include_retargeted=bool(core_ref),
                  native_root=native, targets=results, staged_source_sha256=source_hashes,
                  current_source_sha256=current_hashes, fixture_sha256=fixture_hashes,
                  expected_sha256=sha(expected_raw),
                  limitations='Mock emulates hardware with CPU dots; no FPGA, real kernel, actual DMA, timing, accuracy or board acceptance.')
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('R14_V321_80_LAYER_FOUR_TENSOR_HOST_QEMU_PASS' if a.targets == 'host,qemu' else 'R14_V321_80_LAYER_FOUR_TENSOR_HOST_PASS')


if __name__ == '__main__':
    main()
