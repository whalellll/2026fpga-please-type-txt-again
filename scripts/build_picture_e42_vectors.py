"""Build synthetic raw2/exact device vectors; host checks never use hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--distribution', default='Ubuntu-22.04')
    a = ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT / 'build')
    out = workspace_path(a.output)
    assert not out.exists()
    out.mkdir(parents=True)
    names = ['linux/picture_new/test_e42_device.c', 'linux/picture_new/vision32_backend.c',
             'linux/picture_new/graph_profile.c', 'sw/bootloader/crc32_fast.c']
    mock = 'linux/picture_new/hwc_fast/tests/picture_new_graph_mock.c'
    includes = ['linux/picture_new', 'linux/vision', 'linux/mac_accel',
                'artifacts/vision-model-20261020-adapter/runtime', 'sw/bootloader']
    files = set(names + [mock, 'scripts/build_picture_e42_vectors.py', 'scripts/picture_workspace.py',
                         'linux/picture_new/hwc_fast/tests/vision_exact_capture.h'])
    for directory in includes:
        files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).glob('*.h'))

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    before = {name: sha(ROOT / name) for name in sorted(files)}
    commands = []

    def run(label, argv):
        commands.append({'name': label, 'argv': argv, 'timeout_seconds': 60})
        with (out / (label + '.log')).open('xb') as log:
            result = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'timeout', '60', *argv],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=75)
        assert result.returncode == 0, (label, (out / (label + '.log')).read_text(errors='replace'))

    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffunction-sections', '-fdata-sections']
    for target in ['host', 'rv32']:
        cc = 'gcc' if target == 'host' else '/opt/toolchain/bin/riscv32-linux-musl-gcc'
        argv = [cc, *flags, *['-I'+wsl_path(ROOT / name) for name in includes]]
        if target == 'host':
            argv += ['-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl', wsl_path(ROOT / mock)]
        else:
            argv += ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
        run(target + '-build', [*argv, *[wsl_path(ROOT / name) for name in names],
                               '-Wl,--gc-sections', '-lm', '-o', wsl_path(out / ('e42-vectors-' + target))])
    for mode in ['raw2', 'exact']:
        run('host-' + mode, [wsl_path(out / 'e42-vectors-host'), '--' + mode])
    assert all(sha(ROOT / name) == digest for name, digest in before.items())
    result = {'status': 'DEVICE_VECTOR_HOST_ORACLE_AND_RV32_BUILD_PASS_NOT_BOARD', 'source_sha256': before,
              'commands': commands, 'hardware_used': False, 'rv32_sha256': sha(out / 'e42-vectors-rv32'),
              'actual_raw2_exact_ownership_pending': True,
              'board_order': ['e42-vectors-rv32 --raw2', 'e42-vectors-rv32 --exact', 'e42-vectors-rv32 --ownership']}
    (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
