"""Build T4a host handoff from reviewed sources and synthetic-only references."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
HWC = 'linux/picture_new/hwc_fast'
ADAPTER = 'artifacts/vision-model-20261020-adapter/runtime'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl(path):
    path = path.resolve().as_posix()
    assert path[1:3] == ':/'
    return '/mnt/' + path[0].lower() + path[2:]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT / 'build/hwc-acceptance-kit')
    ap.add_argument('--validation', type=Path, required=True)
    ap.add_argument('--fixed-hwc', type=Path, required=True)
    ap.add_argument('--distribution', default='Ubuntu-22.04')
    a = ap.parse_args()
    logical = a.output.absolute()
    assert logical.is_relative_to(ROOT / 'build')
    out = logical.resolve()
    assert not out.exists() or not any(out.iterdir()), 'Use a fresh empty output directory'
    out.mkdir(parents=True, exist_ok=True)
    logdir = out / 'verification'
    logdir.mkdir()
    validation = a.validation.resolve()
    checked = json.loads((validation / 'result.json').read_text())
    assert checked['status'] == 'HWC_THREE_FULL_HEADS_IMMUTABLE_CPU_REFERENCE_FAILURE_GUARDS_HOST_RV32_PASS_NOT_BOARD'
    includes = [HWC, ADAPTER, 'linux/picture_new', 'linux/vision', 'linux/mac_accel',
                'sw/bootloader', 'sw/xiangqi']
    common = ['linux/picture_new/vision32_backend.c', 'linux/picture_new/graph_profile.c',
              'sw/bootloader/crc32_fast.c', ADAPTER + '/xq_sha256.c']
    host_sources = [HWC + '/kit_host.c', HWC + '/integer_hwc.c',
                    HWC + '/tests/picture_new_graph_mock.c', *common]
    converter_sources = [HWC + '/convert_input.c', 'linux/vision/xq_roi.c',
                         'linux/picture_new/vision32_layer.c', *common]
    files = set(host_sources + converter_sources + [HWC + '/integer_bench.c',
                HWC + '/tests/vision_exact_capture.h', HWC + '/kit_convert.py',
                HWC + '/kit_selftest.py', HWC + '/KIT_README.md',
                'scripts/build_picture_hwc_acceptance_kit.py',
                'linux/picture_new/vision32_locality.c',
                'linux/picture_new/whole_layer_fast/vision32_layer.c',
                'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
                'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h'])
    for rel in includes:
        files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / rel).glob('*.h'))
    before = {name: sha(ROOT / name) for name in sorted(files)}
    commands = []

    def run(name, command, seconds=300):
        commands.append({'name': name, 'argv': command, 'timeout_seconds': seconds})
        with (logdir / (name + '.log')).open('xb') as log:
            result = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 ' + str(seconds) + ' ' + shlex.join(command)],
                stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 20)
        assert result.returncode == 0, (name, (logdir / (name + '.log')).read_text(errors='replace')[-4000:])

    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
             '-static', '-ffp-contract=off', '-ffunction-sections', '-fdata-sections']
    for name, sources, extra in [('integer-host', host_sources,
                                 ['-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl']),
                                ('hwc-convert', converter_sources, [])]:
        run(name + '-build', ['gcc', *flags, *extra, *['-I'+wsl(ROOT / p) for p in includes],
                              *[wsl(ROOT / p) for p in sources], '-Wl,--gc-sections', '-lm',
                              '-o', wsl(out / name)], 90)
        elf = (out / name).read_bytes()
        assert elf[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', elf, 18)[0] == 62
    run('compiler', ['gcc', '--version'], 10)
    models, synthetic, reference = out / 'models', out / 'synthetic', out / 'reference'
    models.mkdir();synthetic.mkdir();reference.mkdir()
    for name in ['detector.xqm', 'detector.xqi']:
        shutil.copyfile(validation / 'models' / name, models / name)
    assert sha(models / 'detector.xqm') == 'd65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'
    assert sha(models / 'detector.xqi') == 'd72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    exponent = struct.unpack_from('<i', (models / 'detector.xqi').read_bytes(), 48 + 18*4)[0]
    expected = {'input_exponent': exponent, 'files': {}, 'cases': {}}
    for case in ['fixed', 'zero', 'signed']:
        inp = synthetic / (case + '.f32')
        shutil.copyfile(validation / (case + '.f32'), inp)
        run(case + '-convert', [wsl(out / 'hwc-convert'), wsl(models / 'detector.xqi'),
             'nchw-f32', wsl(inp), '640', '640', '0', '0', '640', '640', wsl(synthetic / (case + '.hwc8'))])
        full = validation / (case + '-reference.f32')
        assert sha(full) == checked['cases'][case]['full_output_sha256']
        data, at, crc = full.read_bytes(), 0, 0
        for side in [80, 40, 20]:
            assert struct.unpack_from('<4I', data, at) == (1, 57, side, side)
            at += 16;size = 57 * side * side * 4
            crc = zlib.crc32(data[at:at+size], crc);at += size
        assert at == len(data) == 1915248
        expected['cases'][case] = {'input_sha256': sha(synthetic / (case + '.hwc8')),
                                  'output_sha256': sha(full), 'output_crc32': f'{crc:08x}'}
    assert sha(a.fixed_hwc) == '102ed005330661fa1576afa5b6ceb60b6407e7b9c1475252fb183cd176c0f27a'
    assert (synthetic / 'fixed.hwc8').read_bytes() == a.fixed_hwc.read_bytes()
    for rel in ['xq_native_worker.c', 'xq_native_post.c']:
        shutil.copyfile(ROOT / ADAPTER / rel, reference / rel)
    shutil.copyfile(ROOT / 'build/picture-merge-20261023/native-models/native_parameters.h',
                    reference / 'native_parameters.h')
    shutil.copyfile(ROOT / HWC / 'kit_convert.py', out / 'convert.py')
    shutil.copyfile(ROOT / HWC / 'kit_selftest.py', out / 'selftest.py')
    shutil.copyfile(ROOT / HWC / 'KIT_README.md', out / 'README.md')
    for path in [*models.iterdir(), *synthetic.iterdir(), out / 'integer-host', out / 'hwc-convert',
                 out / 'convert.py', out / 'selftest.py', *reference.iterdir()]:
        expected['files'][path.relative_to(out).as_posix()] = sha(path)
    (out / 'expected.json').write_text(json.dumps(expected, indent=2)+'\n', encoding='utf-8')
    run('selftest', ['python3', wsl(out / 'selftest.py')], 900)
    assert 'HWC_ACCEPTANCE_KIT_SYNTHETIC_SELFTEST_PASS' in (logdir / 'selftest.log').read_text()
    assert all(sha(ROOT / name) == digest for name, digest in before.items()), 'Sources changed during build'
    for rel in files:
        target = out / 'source' / rel
        target.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(ROOT / rel, target)
    (out / 'build-commands.json').write_text(json.dumps(commands, indent=2)+'\n', encoding='utf-8')
    provenance = {'status': 'T4A_HOST_CONVERTER_IO_SPEC_SYNTHETIC_SELFTEST_PASS_NOT_T4B',
                  'source_software_snapshot': 'aa134da06b404ee572976c438387c2f8aa3a2c96',
                  'source_implementation': 'da0f914e08fbcdb7678a0b76cfdbe84fd349e6f7',
                  'source_inputs_sha256': before, 'source_stable': True,
                  'compiler': (logdir / 'compiler.log').read_text(),
                  'full_graph_reference': checked, 'hardware_used': False,
                  'camera_v2_or_game2_accessed': False,
                  'training_acceptance_178_pending': True, 'board_latency_accepted': False}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n', encoding='utf-8')
    manifest = ''.join(sha(p) + '  ' + p.relative_to(out).as_posix() + '\n'
                       for p in sorted(out.rglob('*')) if p.is_file())
    (out / 'SHA256SUMS.txt').write_text(manifest, encoding='utf-8')
    archive = out.parent / (out.name + '-20261026.zip')
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(out).as_posix())
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100755 if path.name in ['integer-host', 'hwc-convert'] else 0o100644) << 16
                z.writestr(info, path.read_bytes())
    result = {'status': provenance['status'], 'zip_bytes': archive.stat().st_size,
              'zip_sha256': sha(archive), 'manifest_payloads': len(manifest.splitlines()),
              'output': str(out), 'zip': str(archive), 'hardware_used': False}
    (out.parent / (out.name + '-receipt.json')).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
