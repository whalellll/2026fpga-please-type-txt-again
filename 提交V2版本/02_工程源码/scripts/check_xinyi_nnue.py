"""Validate dedicated NNUE software with strict local backend policy, off-board.

Runs host/RV32 QEMU intercepted-driver and Stage A/B tests. An optional read-only
prepared official engine source builds engine/search/latency binaries in a new
native worksite. Never builds a GUI or changes boot outputs.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import shlex
import struct
import subprocess
import tarfile
import uuid

R = Path(__file__).resolve().parents[1]
PORT = 'linux/pikafish/'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--distribution', default='Ubuntu-22.04')
    p.add_argument('--engine-baseline', type=Path)
    p.add_argument('--timeout-seconds', type=int, default=1800)
    a = p.parse_args()
    out = a.output.resolve()
    assert out.is_relative_to(R/'build') and not out.exists()
    assert 60 <= a.timeout_seconds <= 7200
    names = ['pikafish_mac_runtime.cpp', 'pikafish_mac_runtime.h', 'pikafish_mac_backend_policy.h',
             'pikafish_mac_backend_policy_test.cpp', 'pikafish_mmio_shadow.h', 'pango_mac_uapi.h',
             'pikafish_stagea_accel.cpp', 'pikafish_stagea_accel.h', 'pikafish_feature_updates.h', 'pikafish_stageb_accel.cpp',
             'pikafish_stageb_accel.h', 'pikafish_stagea_pack_test.cpp', 'pikafish_stageb_phase4_test.cpp',
             'test_xinyi_nnue_runtime.cpp', 'apply_nnue_pipeline.py', 'pikafish-pipeline.patch',
             'pikafish_pipeline_search.cpp', 'pikafish_nnue_pipeline_latency.cpp', 'nnue_clint_clock.c',
             'pikafish_embedded.h']
    paths = [PORT+n for n in names]
    paths += ['linux/mac_accel/pango_mac_uapi.h', 'sw/mac_accel/mac_accel_kernel.h',
              'sw/pikafish_mlp_stage_b/pf_mlp_mac_pack.h', 'sw/pikafish_mlp_stage_b/pf_mlp_stage_b.h',
              'sw/pikafish_mlp_stage_b/pf_stageb_position_golden.h', 'scripts/build_xinyi_nnue.sh']
    data = {name: (R/name).read_bytes() for name in paths}
    assert data[PORT+'pango_mac_uapi.h'] == data['linux/mac_accel/pango_mac_uapi.h'], 'UAPI copies differ'
    assert b'backend_policy(' in data[PORT+'pikafish_mac_runtime.cpp']
    assert b'(info.features & policy.requiredFeatures) != policy.requiredFeatures' in data[PORT+'pikafish_mac_runtime.cpp']
    source_hashes = {name: sha(blob) for name, blob in data.items()}
    source_hashes[Path(__file__).relative_to(R).as_posix()] = sha(Path(__file__).read_bytes())
    pack_path = R/'artifacts/pikafish-stageb-mac.bin'
    pack = pack_path.read_bytes()
    data['inputs/stageb-mac.bin'] = pack
    baseline_hashes = {}
    baseline_commit = None
    if a.engine_baseline:
        baseline = a.engine_baseline.resolve()
        baseline_commit = subprocess.check_output(['git', '-C', str(baseline), 'rev-parse', 'HEAD'], text=True).strip()
        assert baseline_commit == '56be6f65c21c6a3c7f9b884a976fc85d31d03287'
        for group in ['src', 'scripts']:
            for path in (baseline/group).rglob('*'):
                if not path.is_file() or path.suffix in ('.o', '.d') or path.name in ('pikafish', 'pikafish.exe'):
                    continue
                # The prepared worksite contains official source plus explicit
                # portability patches, not the NNUE training weight file.
                assert path.suffix not in ('.nnue', '.pff', '.atk')
                rel = path.relative_to(baseline).as_posix()
                blob = path.read_bytes();baseline_hashes[rel] = sha(blob);data['baseline/'+rel] = blob
        assert 'src/Makefile' in baseline_hashes
    out.mkdir(parents=True)
    from workspace_paths import wsl_path
    native = wsl_path(out/'native')
    q = shlex.quote
    includes = ['-iquote', native+'/linux/pikafish', '-iquote', native+'/sw/pikafish_mlp_stage_b']
    flags = ['-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread']
    script = ['set -eu', 'export TMPDIR='+shlex.quote(native+'/out'), 'export PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin',
              'command -v g++', 'command -v qemu-riscv32', '/opt/toolchain/bin/riscv32-linux-musl-g++ -dumpmachine']
    strict = ['missing-feature', 'missing-pipeline', 'open-failure', 'invalid-features',
              'invalid-backend', 'strict-mmio-conflict']
    phase4 = ['disabled', 'default', 'verify', 'enabled', 'reuse', 'threads', 'fault-busy', 'fault-error', 'fault-timeout']
    for target, cc, extra, prefix in [
        ('host', 'g++', [], []),
        ('qemu', '/opt/toolchain/bin/riscv32-linux-musl-g++', ['-static', '-march=rv32ima', '-mabi=ilp32'], ['qemu-riscv32'])]:
        def compile_binary(name, sources, defines=(), link=()):
            exe = native+'/out/'+name+'-'+target
            command = [cc, *flags, *extra, *includes, *defines,
                       *[native+'/'+PORT+source for source in sources], *link, '-o', exe]
            script.append(shlex.join(command))
            return exe
        policy = compile_binary('policy', ['pikafish_mac_backend_policy_test.cpp'])
        script.append(shlex.join([*prefix, policy]))
        runtime = compile_binary('runtime', ['test_xinyi_nnue_runtime.cpp', 'pikafish_mac_runtime.cpp', 'pikafish_stagea_accel.cpp'],
                                 ['-DPIKAFISH_STAGEA_ACCEL', '-DPIKAFISH_STAGEB_ACCEL'],
                                 ['-Wl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap,--wrap=ioctl'])
        script.append(shlex.join([*prefix, runtime]))
        script.append(shlex.join(['env', 'MOCK_PIKAFISH_DEDICATED=1', *prefix, runtime]))
        for scenario in strict:
            script.append(shlex.join([*prefix, runtime, scenario]))
        pack_a = compile_binary('stagea', ['pikafish_stagea_pack_test.cpp', 'pikafish_stagea_accel.cpp', 'pikafish_mac_runtime.cpp'],
                                ['-DPIKAFISH_STAGEA_ACCEL', '-DPIKAFISH_MAC_RUNTIME_EMULATED'])
        script.append(shlex.join([*prefix, pack_a]))
        pack_b = compile_binary('stageb', ['pikafish_stageb_phase4_test.cpp', 'pikafish_stageb_accel.cpp', 'pikafish_mac_runtime.cpp'],
                                ['-DPIKAFISH_STAGEB_ACCEL', '-DPIKAFISH_MAC_RUNTIME_EMULATED', '-DPIKAFISH_STAGEB_TESTING'])
        for scenario in phase4:
            script.append(shlex.join([*prefix, pack_b, scenario, native+'/inputs/stageb-mac.bin']))
    if a.engine_baseline:
        script.append(shlex.join(['sh', native+'/scripts/build_xinyi_nnue.sh', native, native+'/baseline', native+'/out/engine']))
    build = ('\n'.join(script)+'\n').encode()
    (out/'build.sh').write_bytes(build)
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode='w') as archive:
        for name, blob in {**data, 'build.sh': build}.items():
            item = tarfile.TarInfo(name);item.size = len(blob);item.mode = 0o644
            archive.addfile(item, io.BytesIO(blob))
    command = 'set -eu; test ! -e '+q(native)+'; mkdir -p '+q(native+'/out')
    command += '; tar -xf - -C '+q(native)+'; timeout --kill-after=10 '+str(a.timeout_seconds)+' sh '+q(native+'/build.sh')
    result = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'sh', '-c', command],
                            input=bundle.getvalue(), capture_output=True, timeout=a.timeout_seconds+60)
    (out/'stdout.log').write_bytes(result.stdout)
    (out/'stderr.log').write_bytes(result.stderr)
    log = result.stdout + result.stderr
    (out/'build.log').write_bytes(log)
    assert result.returncode == 0, log.decode(errors='replace')[-6000:]
    for marker, expected in [(b'PIKAFISH_MAC_BACKEND_POLICY_TEST_PASS', 2),
                             (b'NNUE_PIPELINE_RUNTIME_CONTEXT_ORDER_POINTER_REUSE_STALE_AND_GATHER_PASS', 4),
                             (b'NNUE_STAGEA_BOTH_PERSPECTIVES_REFRESH_INTERMEDIATE_ZERO_REUPLOAD_PASS', 4),
                             (b'XINYI_NNUE_STRICT_POLICY_REJECT_PASS', 12),
                             (b'PIKAFISH_STAGEA_PACK_TEST_PASS', 2),
                             (b'PIKAFISH_STAGEB_PHASE4_FAULT_PASS', 6),
                             (b'PIKAFISH_STAGEB_PHASE4_THREADS_PASS', 2)]:
        assert log.count(marker) == expected, (marker, log.count(marker))
    returned = subprocess.check_output(['wsl.exe', '-d', a.distribution, '--', 'tar', '-cf', '-', '-C', native+'/out', '.'], timeout=60)
    with tarfile.open(fileobj=io.BytesIO(returned)) as archive:
        for item in archive.getmembers():
            if not item.isfile():
                continue
            relative = Path(item.name.removeprefix('./'))
            assert not relative.is_absolute() and '..' not in relative.parts
            destination = out/relative;destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(item).read())
    elf_files = sorted(out.glob('*-qemu'))
    if a.engine_baseline:
        assert b'XINYI_NNUE_ENGINE_SEARCH_LATENCY_RV32_BUILD_PASS_NOT_BOARD' in log
        integration = json.loads((out/'engine/pipeline-integration.json').read_bytes())
        assert integration['status'] == 'ALL_THREE_NNUE_PIPELINE_HOOKS_VERIFIED'
        elf_files += [out/'engine'/name for name in ['pikafish-rv32', 'pikafish-pipeline-search', 'pikafish-nnue-pipeline-latency']]
    for path in elf_files:
        elf = path.read_bytes()
        assert elf[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', elf, 18)[0] == 243
        assert struct.unpack_from('<I', elf, 36)[0] == 0, str(path)
    assert all(sha((R/name).read_bytes()) == digest for name, digest in source_hashes.items())
    assert sha(pack_path.read_bytes()) == sha(pack)
    if a.engine_baseline:
        assert all(sha((a.engine_baseline/name).read_bytes()) == digest for name, digest in baseline_hashes.items())
    record = dict(status='PASS', scope='dedicated NNUE userspace host and RV32 QEMU mock/emulation; not board acceptance',
                  hardware_used=False, strict_backend_policy_preserved=True, uapi_copies_equal=True,
                  strict_reject_cases=strict, dedicated_and_generic_pipeline_context_pass=True,
                  stagea_pack_lanes=24576, stageb_scenarios=phase4, source_stable=True,
                  source_sha256=source_hashes, stageb_pack_sha256=sha(pack), baseline_commit=baseline_commit,
                  baseline_sha256=baseline_hashes, native_root=native, engine_built=bool(a.engine_baseline),
                  outputs_sha256={p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()},
                  limitations='Mock pipeline score is a diagnostic weighted sum, not actual NNUE MLP; real kernel/hardware, latency and full search correctness remain board work.')
    (out/'result.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print('XINYI_NNUE_HOST_RV32_STRICT_POLICY_STAGEAB_PASS_NOT_BOARD')


if __name__ == '__main__':
    main()
