"""Check word-input/tiled-export through the real HWC adapter, off-board.

Reuses sealed synthetic kit inputs and immutable full-head SHA references.
Exercises intermediate and output-head OOM, IO/cancel and byte-exact recovery.
Does not rerun unchanged exhaustive quantizer/operator suites or access photos.
"""
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
    parser.add_argument('--kit', type=Path, default=ROOT / 'build/hwc-acceptance-kit')
    parser.add_argument('--rgb8-shared-tail', action='store_true', help='Validate legacy arbitrary-F32 behavior with DIRECT=1 enabled')
    args = parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT / 'build')
    out = workspace_path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    kit = workspace_path(args.kit)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(kit / 'models/detector.xqi') == 'd72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942'
    assert sha(kit / 'models/detector.xqm') == 'd65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d'
    expected = json.loads((kit / 'expected.json').read_text())
    runtime = 'artifacts/vision-model-20261020-adapter/runtime'
    hwc = 'linux/picture_new/hwc_fast'
    common = [hwc + '/adapter.c', hwc + '/tests/picture_new_graph_mock.c',
              'linux/picture_new/graph_runtime.c', 'linux/picture_new/graph_tensor.c',
              'linux/picture_new/graph_ops.c', 'linux/picture_new/vision32_layer.c',
              runtime + '/xq_sha256.c', 'linux/picture_new/vision32_backend.c',
              'linux/picture_new/graph_profile.c', 'sw/bootloader/crc32_fast.c']
    includes = [hwc, runtime, 'linux/picture_new', 'linux/vision', 'linux/mac_accel', 'sw/bootloader']
    files = set(common + [hwc + '/tests/product_adapter.c', hwc + '/tests/product_candidate_faults.c',
        'scripts/check_picture_hwc_product_candidates.py', 'linux/picture_new/vision32_locality.c',
        'linux/picture_new/vision32_exact.c', 'linux/picture_new/whole_layer_fast/vision32_layer.c',
        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c'])
    files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / hwc).rglob('*')
                 if p.is_file() and p.suffix in {'.c', '.h'})
    for directory in includes:
        files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).glob('*.h'))
    before = {name: sha(ROOT / name) for name in sorted(files)}
    input_hashes = {case: sha(kit / ('synthetic/' + case + '.f32')) for case in ['fixed', 'zero', 'signed']}
    checks = []
    def run(name, argv, seconds=360):
        with (out / (name + '.log')).open('xb') as log:
            result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 ' + str(seconds) + ' ' + shlex.join(argv)],
                stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 20)
        text = (out / (name + '.log')).read_text(errors='replace')
        assert result.returncode == 0, (name, text[-2000:])
        return text
    for target in ['host', 'rv32', 'sanitizer']:
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'gcc'
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
                 '-ffp-contract=off', '-ffunction-sections', '-fdata-sections',
                 '-DXQ_HWC_DETECTOR=1', '-DXQ_CLASSIFIER_S16=1', '-DXQ_FAST_REQUANT=1',
                 '-DXQ_HWC_WORD_INPUT=1', '-DXQ_HWC_TILE_EXPORT=1']
        if target == 'rv32':
            flags += ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
        if args.rgb8_shared_tail:
            flags += ['-DXQ_HWC_RGB8_DIRECT=1']
        if target == 'sanitizer':
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        binaries = {}
        for kind, test in [('normal', 'product_adapter.c'), ('faults', 'product_candidate_faults.c')]:
            if target == 'sanitizer' and kind == 'normal':
                continue
            binary = out / (target + '-' + kind)
            run(target + '-' + kind + '-build', [cc, *flags, *['-I' + wsl_path(ROOT / d) for d in includes],
                *[wsl_path(ROOT / name) for name in [hwc + '/tests/' + test, *common]],
                '-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl,--wrap=malloc,--wrap=calloc',
                '-Wl,--gc-sections', '-lm', '-o', wsl_path(binary)], 90)
            binaries[kind] = binary
        for case in ['fixed'] + ([] if target == 'sanitizer' else ['zero', 'signed']):
            output = out / (target + '-' + case + '.heads.f32')
            kind = 'faults' if case == 'fixed' else 'normal'
            text = run(target + '-' + case, [*(['qemu-riscv32'] if target == 'rv32' else []),
                wsl_path(binaries[kind]), wsl_path(kit / 'models/detector.xqm'),
                wsl_path(kit / ('synthetic/' + case + '.f32')), wsl_path(output)])
            assert 'HWC_PRODUCT_BOUNDARY_NO_CPU_FALLBACK_NO_RAW2_OBSERVER_OOM_CANCEL_IOCTL_INVALIDATE_PASS' in text
            if case == 'fixed':
                assert 'HWC_CANDIDATE_EARLY_MIDDLE_HEAD_OOM_IO_CANCEL_AND_RECOVERY_PASS' in text
            assert sha(output) == expected['cases'][case]['output_sha256'], (target, case, 'heads differ')
            checks.append(dict(target=target, case=case, full_three_heads_equal_frozen_reference=True,
                               extended_middle_and_head_faults=case == 'fixed',
                               recovered_heads_full_bytes_equal=case == 'fixed'))
    assert before == {name: sha(ROOT / name) for name in before}
    assert input_hashes == {case: sha(kit / ('synthetic/' + case + '.f32')) for case in input_hashes}
    receipt = dict(status='WORD_AND_TILE_REAL_ADAPTER_FULL_HEADS_MIDDLE_HEAD_OOM_IO_CANCEL_RECOVERY_PASS_NOT_BOARD',
                   hardware_used=False, photos_accessed=False, source_sha256=before, checks=checks,
                   input_and_models_unchanged=True, mock_device=True, real_driver_drain_accepted=False)
    receipt['rgb8_shared_tail_enabled']=args.rgb8_shared_tail
    receipt['legacy_f32_nonfinite_rejected_without_jobs']=True
    (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['status'])


if __name__ == '__main__':
    main()
