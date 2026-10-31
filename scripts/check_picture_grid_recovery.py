"""Host/RV32 proposal guards and optional authorized private-frame comparison.

No model/device access. Private corner outputs remain under the private build
junction; their coordinates, identities and hashes never enter the result JSON.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--private-rgb565', type=Path)
    ap.add_argument('--private-coarse', type=Path)
    a = ap.parse_args()
    assert a.output.absolute().is_relative_to(ROOT/'build')
    assert bool(a.private_rgb565) == bool(a.private_coarse)
    out = workspace_path(a.output); assert not out.exists(); out.mkdir(parents=True)
    sources = ['linux/picture_new/board_grid_recovery.c', 'linux/picture_new/test_grid_recovery.c',
               'linux/vision/xq_roi.c']
    includes = ['linux/picture_new', 'linux/vision', 'linux/mac_accel', 'sw/xiangqi', 'sw/bootloader']
    files = set(sources + ['linux/picture_new/board_grid_recovery.h', 'scripts/check_picture_grid_recovery.py'])
    for d in includes:
        files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/d).glob('*.h'))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {p: sha(ROOT/p) for p in sorted(files)}
    private_inputs = {workspace_path(p): sha(workspace_path(p)) for p in
                      [a.private_rgb565, a.private_coarse] if p}
    if a.private_rgb565:
        assert a.private_rgb565.stat().st_size == 1843200 and a.private_coarse.stat().st_size == 32
    result = dict(status='FAILED_PRESERVED', hardware_used=False, source_sha256=before,
                  private_fixture_used=bool(private_inputs), runs=[])

    def run(name, args):
        with (out/(name+'.log')).open('xb') as log:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'timeout', '120', *args],
                               stdout=log, stderr=subprocess.STDOUT, timeout=140)
        result['runs'].append(dict(name=name, exit=p.returncode))
        assert p.returncode == 0, (name, (out/(name+'.log')).read_text(errors='replace')[-2000:])

    try:
        for target in ['host', 'rv32']:
            cc = 'gcc' if target == 'host' else '/opt/toolchain/bin/riscv32-linux-musl-gcc'
            flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
                     '-ffunction-sections', '-fdata-sections']
            if target == 'rv32': flags += ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
            exe = out/target
            run(target+'-build', [cc, *flags, *['-I'+wsl_path(ROOT/d) for d in includes],
                *[wsl_path(ROOT/p) for p in sources], '-Wl,--wrap=calloc,--gc-sections', '-lm', '-o', wsl_path(exe)])
            prefix = ['qemu-riscv32'] if target == 'rv32' else []
            run(target+'-unit', [*prefix, wsl_path(exe), '--synthetic'])
            assert 'GRID_NOOP_ALIAS_BLANK_CANCEL_OOM_INVALID_NO_OLD_GEOMETRY_PASS_NOT_BOARD' in (out/(target+'-unit.log')).read_text()
            assert 'GRID_SYNTHETIC_FOUR_CORNERS_RECOVER_TWO_BAD_UNCHANGED_ALIAS_PASS_NOT_BOARD' in (out/(target+'-unit.log')).read_text()
            if private_inputs:
                run(target+'-private', [*prefix, wsl_path(exe), '--private-rgb565',
                    wsl_path(a.private_rgb565), wsl_path(a.private_coarse), wsl_path(out/(target+'-private.bin'))])
        if private_inputs:
            assert (out/'host-private.bin').read_bytes() == (out/'rv32-private.bin').read_bytes(), 'host/RV32 proposal differs'
            result['private_proposal_host_rv32_byte_equal'] = True
        assert all(sha(ROOT/p) == h for p, h in before.items())
        assert all(sha(p) == h for p, h in private_inputs.items())
        result.update(status='GRID_RECOVERY_GUARDS_HOST_RV32_PASS_NOT_BOARD', source_stable=True,
                      no_normal_case_allocation=True, cancel_and_oom_invalidate=True,
                      synthetic_recovery_all_four_corners=True, two_bad_corners_unchanged=True,
                      no_previous_geometry_or_piece_layout_input=True)
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__': main()
