"""Check compact binary-mask sliding sums against a direct reference, off-board."""
import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT / 'build')
    out = workspace_path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    names = ['linux/picture_new/geometry_mask.h', 'linux/picture_new/test_geometry_mask.c',
             'scripts/check_picture_geometry_mask.py']
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = {name: sha(ROOT / name) for name in names}
    rows = []
    def run(name, argv, seconds=120):
        with (out / (name + '.log')).open('xb') as log:
            result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 ' + str(seconds) + ' ' + shlex.join(argv)],
                stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 15)
        return result.returncode, (out / (name + '.log')).read_text(errors='replace')
    for target in ['host', 'rv32', 'sanitizer']:
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'gcc'
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror']
        if target == 'rv32':
            flags += ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
        if target == 'sanitizer':
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        exe = out / target
        code, log = run(target + '-build', [cc, *flags, wsl_path(ROOT / names[1]), '-o', wsl_path(exe)])
        assert code == 0, log[-1500:]
        code, log = run(target, [*(['qemu-riscv32'] if target == 'rv32' else []), wsl_path(exe)])
        assert code == 0 and 'GEOMETRY_MASK8_DIRECT_REFERENCE_PASS' in log, log[-1500:]
        rows.append(dict(target=target, result=log.strip()))
    # A wrong replicated-edge update must be caught by the independent oracle.
    mutation = out / 'negative-edge'
    mutation.mkdir()
    text = (ROOT / names[0]).read_text()
    assert text.count('y>hy?y-hy:0') == 1
    (mutation / 'geometry_mask.h').write_text(text.replace('y>hy?y-hy:0', 'y>hy?y-hy+1:0'))
    (mutation / 'test.c').write_bytes((ROOT / names[1]).read_bytes())
    code, log = run('negative-build', ['gcc', '-std=c11', '-O2', wsl_path(mutation / 'test.c'),
                                      '-o', wsl_path(mutation / 'test')])
    assert code == 0, log[-1500:]
    code, log = run('negative-run', [wsl_path(mutation / 'test')], 15)
    assert code != 0 and 'Assertion' in log and 'expected' in log, log[-1500:]
    assert before == {name: sha(ROOT / name) for name in names}
    receipt = dict(status='COMPACT_MASK_DIRECT_REFERENCE_HOST_RV32_SANITIZERS_NEGATIVE_EDGE_PASS_NOT_BOARD',
                   hardware_used=False, source_sha256=before, checks=rows,
                   wrong_edge_negative_control_rejected=True, scratch_stack_bytes=2560)
    (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['status'])


if __name__ == '__main__':
    main()
