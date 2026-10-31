"""Prepare a source-bound metrics probe; run only explicit device mocks offline."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shlex
import subprocess

from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--targets', default='host,sanitizer,rv32')
    a = ap.parse_args()
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    names = ['linux/xinyi_board/mac_metrics_r18.c', 'linux/xinyi_board/accelerator_idle.c',
             'linux/xinyi_board/accelerator_idle.h', 'linux/mac_accel/pango_mac_uapi.h',
             'sw/pikafish_mlp_stage_b/pf_mlp_stage_b_ref.c',
             'sw/pikafish_mlp_stage_b/pf_mlp_stage_b.h', 'scripts/check_xinyi_mac_metrics_r18.py',
             'scripts/picture_workspace.py']
    sources = [names[0], names[1], names[4]]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {n: sha(ROOT / n) for n in names}
    result = dict(status='FAILED_PRESERVED', hardware_used=False,
                  source_sha256=before, runs=[], production_run=False)

    def run(name, command, limit=90, fail=False):
        with (out / (name + '.log')).open('xb') as log:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 ' + str(limit) + ' ' + shlex.join(command)],
                stdout=log, stderr=subprocess.STDOUT, timeout=limit + 15)
        text = (out / (name + '.log')).read_text(errors='replace')
        assert (p.returncode != 0) if fail else (p.returncode == 0), (name, p.returncode, text[-3000:])
        return text

    def build(target, mock, destination, source_root=ROOT):
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
        flags = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
        if target == 'sanitizer':
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-no-pie']
        options = [cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
                   '-ffunction-sections', '-fdata-sections', '-ffile-prefix-map=' + wsl_path(source_root) + '=.']
        if mock:
            options.append('-DR18_MOCK=1')
        # mac_accel contains freestanding string.h; quote-only paths preserve
        # the real libc headers and their complete strcmp/memcmp declarations.
        for folder in ['linux/xinyi_board', 'linux/mac_accel', 'sw/pikafish_mlp_stage_b']:
            options.extend(['-iquote', wsl_path(source_root / folder)])
        return [*options, *flags, *[wsl_path(source_root / n) for n in sources],
                '-Wl,--gc-sections', '-o', wsl_path(destination)]

    try:
        for target in a.targets.split(','):
            assert target in ['host', 'sanitizer', 'rv32']
            exe = out / (target + '-mock')
            run(target + '-build', build(target, True, exe))
            runner = ['qemu-riscv32'] if target == 'rv32' else []
            for mode in ['vision', 'nnue']:
                text = run(target + '-' + mode, [*runner, wsl_path(exe), '--run', mode], 65)
                assert 'R18_PROBE_PASS' in text and 'backend=mock_NOT_BOARD' in text
                assert 'known=1 five_busy0=1' in text and text.count('R18_PAIR ') == 3
                negatives = []
                for case in ['badcaps', 'badclock', 'badoutput', 'iofail', 'cancel']:
                    text = run(target + '-' + mode + '-' + case,
                               [*runner, wsl_path(exe), '--run', mode, case], 65, True)
                    assert 'R18_PROBE_FAIL' in text and 'R18_PROBE_PASS' not in text
                    if case in ['badcaps', 'badclock', 'cancel']:
                        assert 'calls=0 ' in text
                    negatives.append(case)
                result['runs'].append(dict(target=target, mode=mode, status='PASS_NOT_BOARD',
                    numerical_full_output=True, negative_controls=negatives, executable_sha256=sha(exe)))
        executable = out / 'mac-metrics-r18.unstripped'
        run('production-build', build('rv32', False, executable))
        production = out / 'mac-metrics-r18'
        run('production-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
                                '-o', wsl_path(production), wsl_path(executable)], 30)
        data = production.read_bytes()
        assert data[:7] == b'\x7fELF\x01\x01\x01' and int.from_bytes(data[18:20], 'little') == 243
        assert int.from_bytes(data[36:40], 'little') == 0
        # This entry point prints a static description and never opens a device.
        text = run('production-description', ['qemu-riscv32', wsl_path(production), '--describe'], 20)
        assert 'no_device_open=1' in text
        compressed = gzip.compress(data, mtime=0)
        (out / 'mac-metrics-r18.gz').write_bytes(compressed)
        exported = out / 'source'
        for n, h in before.items():
            data = (ROOT / n).read_bytes()
            assert hashlib.sha256(data).hexdigest() == h
            path = exported / n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        reproduced = out / 'reproduced.unstripped'
        run('source-rebuild', build('rv32', False, reproduced, exported))
        stripped = out / 'reproduced'
        run('source-rebuild-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
                                    '-o', wsl_path(stripped), wsl_path(reproduced)], 30)
        assert stripped.read_bytes() == production.read_bytes()
        assert before == {n: sha(ROOT / n) for n in names}
        result.update(status='R18_MAC_OPERATOR_MOCKS_AND_SOURCE_BOUND_RV32_PROBE_PASS_NOT_BOARD',
            production=dict(path=str(production), bytes=production.stat().st_size, sha256=sha(production),
                            gzip_path=str(out / 'mac-metrics-r18.gz'), gzip_bytes=len(compressed),
                            gzip_sha256=sha(out / 'mac-metrics-r18.gz'), source_rebuild_byte_equal=True),
            operator_scope_only=True, warm_pairs=3, measured_pairs=3)
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
