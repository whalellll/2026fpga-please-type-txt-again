"""Final bounded identity/privacy/source audit for the no-board r08 checkpoint."""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / 'docs/validation/picture-r08-offline-20261021'
BUILD = REPO / 'build/picture-r08-20261021'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    for root in (BUILD / 'delivery', HERE.parent / 'vision-model-20261020'):
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        for name, entry in manifest['files'].items():
            expected = entry if isinstance(entry, str) else entry['sha256']
            assert sha(root / name) == expected, name
    reference = next((BUILD / 'delivery').rglob('exact_mm_int64_reference.py'))
    assert sha(reference) == sha(HERE / reference.name)
    registration = json.loads((HERE / 'candidates/v2-band-r08/registration.json').read_text(encoding='utf-8'))
    assert registration['selected'] is False and registration['production_ready'] is False
    runtime = json.loads((OUT / 'runtime-r03.json').read_text(encoding='utf-8'))
    for name, expected in runtime['sources'].items():
        assert sha(REPO / name) == expected, name
    regression = json.loads((OUT / 'regression.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'PARTIAL_TOOLCHAIN_BLOCKED' and regression['full_suite_passed'] is False
    for group in ('source_files_sha256', 'test_files_sha256', 'linux_files_sha256'):
        for name, expected in regression[group].items():
            assert sha(REPO / name) == expected, name
    identity = json.loads((OUT / 'exact-pc-rerun/inputs.json').read_text(encoding='utf-8'))
    assert identity['evaluator_sha256'] == sha(HERE / 'evaluate_combined.py')
    target = BUILD / 'rv32-worker-r01'
    assert (target / 'source-before.sha256').read_bytes() == (target / 'source-after.sha256').read_bytes()
    elf = (target / 'elf-inspection.txt').read_text(encoding='utf-8')
    assert 'ELF32' in elf and re.search(r'Flags:\s+0x0\s*\n', elf)
    arch = re.search(r'Tag_RISCV_arch: "([^"]+)"', elf).group(1)
    assert arch.startswith('rv32i') and not re.search(r'(^|_)c\d', arch)
    write('rv32-build.json', dict(status='PASS', scope='Offline compile/ELF/source checks only; never run on device',
          binary_sha256=sha(target / 'xq-native-worker'), bytes=(target / 'xq-native-worker').stat().st_size,
          compiler_sha256=sha(target / 'compiler.txt'), isa=arch,
          source_receipt_sha256=sha(target / 'source-before.sha256'), source_before_after_equal=True,
          hardware_used=False, deployed=False))
    write('execution-notes.json', dict(
          final_host_runtime='runtime-r03; 135/135 packets byte-identical, source-bound',
          early_host_runs=[dict(run='runtime-r01', result='synthetic geometry dispatch assertion failed during integration; raw files retained in build'),
                           dict(run='runtime-r02', result='stopped before completion to freeze final sources; never counted as PASS')],
          environment_failures=['default nonexistent G: PDS path', 'CPU_TOOLCHAIN/host GCC path unset',
                                'mandatory LTO build with installed --disable-lto GCC'],
          harness_corrections=['preserved an intentional native negative-test exit code instead of treating the passed policy script as failed',
                               'restored the isolated build/ fixture directory'],
          continuation='Only failed/unrun suffixes resumed; earlier successful CPU/SoC and speaker transcripts retained',
          reused_boot_build='Exact-input historical r06 boot build for existing SkipBootloaderBuild speaker checks; full LTO gate remains failed',
          hardware_used=False, full_suite_passed=False))
    changed = subprocess.check_output(['git', 'diff', '--name-only', '-z'], cwd=REPO).decode().split('\0')
    added = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=REPO).decode().split('\0')
    paths = [REPO / name for name in set(changed + added) - {''} if (REPO / name).is_file()]
    forbidden = {'rtl', 'ip', 'pds'}
    assert not any(p.relative_to(REPO).parts[0] in forbidden for p in paths)
    for name in ('runtime/xq_int8_layer.c', 'runtime/xq_resident_matrix.c'):
        path = HERE / name
        frozen = subprocess.check_output(['git', 'show', 'HEAD:' + path.relative_to(REPO).as_posix()], cwd=REPO)
        assert path.read_bytes().replace(b'\r\n', b'\n') == frozen.replace(b'\r\n', b'\n')
    live = REPO / 'build/picture-p21-native/live-sd-r01'
    private_hashes = [sha(live / name).encode() for name in ('frame.png', 'frame.rgb565')]
    request = (live / 'request.txt').read_text().split()
    private_token = request[1].encode()
    for path in paths:
        content = path.read_bytes()
        assert not any(value in content for value in private_hashes), 'private capture hash leaked'
        if len(private_token) >= 9:
            assert private_token not in content, 'private capture token leaked'
        assert path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.rgb565', '.pt', '.onnx', '.npz', '.bin', '.elf', '.zip'}
        if path.suffix == '.py':
            ast.parse(content.decode('utf-8'), filename=str(path))
    subprocess.run(['git', 'diff', '--check'], cwd=REPO, check=True)
    write('closeout.json', dict(status='PASS_WITH_DECLARED_FULL_REGRESSION_BLOCKER',
          date='2026-10-21', branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=REPO, text=True).strip(),
          head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
          received_delivery_and_frozen_r2_reverified=True, exact_source_unchanged=True,
          runtime_and_functional_test_source_bindings_match=True, live_hash_token_scan_pass=True,
          no_photographs_or_model_payloads_in_changes=True, numerical_device_kernels_unchanged=True,
          rtl_ip_pds_unchanged=True, hardware_used=False, deployed=False, push=False, tag=False,
          production_ready=False, p0_1_resolved=False, board_validation='pending',
          full_suite_passed=False, blocker=regression['blocker'],
          source_sha256={p.relative_to(REPO).as_posix(): sha(p) for p in paths
                         if p.is_relative_to(HERE) or p.is_relative_to(REPO / 'linux')}))
    print('R08_FINAL_IDENTITY_PRIVACY_SOURCE_AUDIT_PASS FULL_REGRESSION_LTO_BLOCKER_RETAINED')


if __name__ == '__main__':
    main()
