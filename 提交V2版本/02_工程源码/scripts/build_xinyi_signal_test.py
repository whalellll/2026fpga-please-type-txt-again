"""Build an explicit RAM-only serial-control GUI from authenticated product objects.

Production main.c and the normal SD builder remain unchanged. USR1/USR2/HUP
exercise the existing start/Space/Esc controller, not physical HID acceptance.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path
from verify_xinyi_elf import inspect


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--product', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    out = workspace_path(a.output)
    product = workspace_path(a.product)
    assert not out.exists()
    out.mkdir(parents=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    checked = {}
    for line in (product/'source-before.sha256').read_text().splitlines():
        expected, name = line.split(None, 1)
        relative = name.split('/performance_soc/', 1)[1]
        p = ROOT/relative
        assert sha(p) == expected, relative
        checked[relative] = expected
    assert (product/'source-before.sha256').read_bytes() == (product/'source-after.sha256').read_bytes()
    source = (ROOT/'linux/xinyi_board/main.c').read_text()
    before = '    int first=1;uint64_t last_present=0;'
    poll = '        (void)xy_runtime_poll(&runtime);'
    assert source.count(before) == source.count(poll) == 1
    source = '#include "signal_test_control.h"\n' + source.replace(before,
        '    if(!xy_signal_test_attach())exit_requested=1;\n'+before).replace(poll,
        '        xy_signal_test_poll(&runtime);\n'+poll)
    (out/'main-signal-test.c').write_text(source)
    files = ['signal_test_control.c', 'signal_test_control.h', 'test_signal_control.c']
    checked.update({'linux/xinyi_board/'+p: sha(ROOT/'linux/xinyi_board'/p) for p in files})
    objects = sorted(p for p in (product/'obj').glob('*.o') if p.name != '0.o')
    assert len(objects) == 21 and inspect(product/'xinyi-one')['allocated'] == inspect(product/'xinyi-one-stripped')['allocated']
    object_hashes = {p.name: sha(p) for p in objects}
    flags = ['-std=c11', '-D_POSIX_C_SOURCE=200809L', '-O2', '-Wall', '-Wextra', '-Werror',
             '-ffunction-sections', '-fdata-sections']
    target = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
    cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc'
    dirs = ['linux/xinyi_board', 'linux/xinyi', 'linux/pikafish', 'linux/vision', 'linux/voice_ctc',
            'linux/voice_speech', 'linux/voice', 'linux/mac_accel', 'linux/picture_new', 'sw/xiangqi', 'sw/bootloader']
    inc = ['-I'+wsl_path(ROOT/p) for p in dirs]

    def run(name, argv):
        with (out/(name+'.log')).open('xb') as log:
            r = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'timeout', '90', *argv],
                               stdout=log, stderr=subprocess.STDOUT, timeout=100)
        assert r.returncode == 0, name

    for name, compiler, extra in [('host', 'gcc', []), ('rv32', cc, target)]:
        exe = out/('test-'+name)
        run('test-build-'+name, [compiler, *flags, *extra, *inc,
            wsl_path(ROOT/'linux/xinyi_board/signal_test_control.c'),
            wsl_path(ROOT/'linux/xinyi_board/test_signal_control.c'), '-Wl,--wrap=sigprocmask', '-o', wsl_path(exe)])
        run('test-'+name, [*(['qemu-riscv32'] if name == 'rv32' else []), wsl_path(exe)])
        assert 'NO_QUEUE_PASS_NOT_BOARD' in (out/('test-'+name+'.log')).read_text()
    for name, src in [('main', out/'main-signal-test.c'), ('control', ROOT/'linux/xinyi_board/signal_test_control.c')]:
        run(name+'-build', [cc, *flags, *target, *inc, '-pthread', '-c', wsl_path(src), '-o', wsl_path(out/(name+'.o'))])
    run('link', [cc, *target, '-pthread', wsl_path(out/'main.o'), wsl_path(out/'control.o'),
                 *map(wsl_path, objects), '-Wl,--gc-sections', '-lm', '-o', wsl_path(out/'xinyi-one')])
    run('strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '-o', wsl_path(out/'xinyi-one-stripped'), wsl_path(out/'xinyi-one')])
    assert inspect(out/'xinyi-one')['allocated'] == inspect(out/'xinyi-one-stripped')['allocated']
    packed = gzip.compress((out/'xinyi-one-stripped').read_bytes(), mtime=0)
    (out/'xinyi-one-stripped.gz').write_bytes(packed)
    assert all(sha(ROOT/p) == h for p, h in checked.items())
    assert all(sha(p) == object_hashes[p.name] for p in objects)
    receipt = dict(status='HOST_RV32_SIGNAL_CONTROL_AND_RV32_BUILD_PASS_NOT_BOARD',
        base_gui_sha256=sha(product/'xinyi-one-stripped'), gui_sha256=sha(out/'xinyi-one-stripped'),
        gzip_sha256=hashlib.sha256(packed).hexdigest(), gzip_bytes=len(packed),
        reused_objects=object_hashes, source_sha256=checked, generated_main_sha256=sha(out/'main-signal-test.c'),
        physical_hid_acceptance=False, hardware_used=False, sd_written=False, source_stable=True)
    (out/'manifest.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['status'])


if __name__ == '__main__':
    main()
