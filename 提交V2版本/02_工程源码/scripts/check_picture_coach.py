"""Test stateless coach geometry/candidate IPC with synthetic data, off-board."""
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
import zlib

R = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--models', type=Path, default=R/'build/picture-merge-20261023/native-models')
    p.add_argument('--distribution', default='Ubuntu-22.04')
    p.add_argument('--timeout-seconds', type=int, default=600)
    p.add_argument('--hwc-detector', action='store_true', help='Build the explicit e42 HWC candidate and exercise its lifecycle')
    p.add_argument('--grid-recovery', action='store_true', help='Exercise the explicit current-frame grid proposal worker entry')
    p.add_argument('--fast-fp32-bilinear', action='store_true', help='Exercise the bit-exact S16-parent FP32 bilinear candidate')
    p.add_argument('--hwc-rgb-quant', action='store_true', help='Exercise exact byte/255.f lookup with arbitrary input fallback')
    p.add_argument('--geometry-fast', action='store_true', help='Exercise exact mask counts and distance-bound pruning')
    p.add_argument('--geometry-arith', action='store_true', help='Exercise exact small division and nonnegative zero shortcuts')
    a = p.parse_args()
    assert not a.hwc_rgb_quant or a.hwc_detector
    assert not a.geometry_arith or a.geometry_fast
    from picture_workspace import workspace_path
    assert a.output.absolute().is_relative_to(R/'build')
    out = workspace_path(a.output)
    assert not out.exists() and 60 <= a.timeout_seconds <= 3600
    paths = set()
    paths.update(['linux/picture_new/whole_layer_fast/vision32_layer.c',
        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h'])
    for directory in ['artifacts/vision-model-20261020-adapter/runtime', 'linux/picture_new', 'linux/vision', 'sw/xiangqi']:
        paths.update(p.relative_to(R).as_posix() for p in (R/directory).glob('*') if p.is_file() and p.suffix in ('.c', '.h'))
    paths.update(['linux/picture_new/build_native_coach.sh', 'linux/picture_new/build_native_v321.sh',
                  'linux/picture_new/build_test_coach_worker.sh',
                  'scripts/check_picture_coach.py', 'scripts/check_picture_coach_lifecycle.py',
                  'linux/picture_new/r14-models.sha256', 'linux/mac_accel/pango_mac_uapi.h',
                  'linux/xinyi/xinyi_product.c', 'linux/xinyi/xinyi_product.h',
                  'linux/xinyi/xinyi_layout.h',
                  'linux/xinyi/coremark/reference.h',
                  'sw/bootloader/crc32_fast.c', 'sw/bootloader/crc32_fast.h',
                  'artifacts/vision-model-20261020/geometry/geometry_reference.c',
                  'artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref/geometry_ref.c',
                  'artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref/geometry_ref.h'])
    if a.hwc_detector:
        paths.update('linux/picture_new/hwc_fast/'+name for name in
                     ['adapter.c', 'adapter.h', 'integer_hwc.c', 'integer_hwc.h','input_quant.c','input_quant.h'])
    paths.add('scripts/picture_workspace.py')
    data = {name: (R/name).read_bytes() for name in paths}
    sources = {name: sha(blob) for name, blob in data.items()}
    models = {}
    for name in ['board.xqm', 'detector.xqm', 'classifier.xqm', 'native_parameters.h', 'refinement_rng.bin'] + (['detector.xqi'] if a.hwc_detector else []):
        blob = (a.models/name).read_bytes();data['build/models/'+name] = blob;models[name] = sha(blob)
    # No photo input: a deterministic zero-filled frame is deliberately paired
    # with a wrong raw CRC, so the worker must reject before running a graph.
    zero_frame = bytes(1843200);wrong_crc = zlib.crc32(zero_frame)^1
    data['build/fixture/frame.rgb565'] = zero_frame
    data['build/fixture/coach-request.txt'] = f'XQ_COACH_REQUEST_V1 321 52 {wrong_crc:08x} rv32-v321-coach\n'.encode()
    data['build/fixture/old-request.txt'] = f'XQ_MODEL_REQUEST_V1 321 52 {wrong_crc:08x} rv32-driver-quantized-mac\n'.encode()
    out.mkdir(parents=True)
    native = '/var/tmp/picture-coach-'+uuid.uuid4().hex
    q = shlex.quote
    includes = ['-I'+native+'/'+d for d in ['linux/picture_new', 'artifacts/vision-model-20261020-adapter/runtime',
                'linux/vision', 'linux/xinyi', 'linux/mac_accel', 'sw/xiangqi', 'sw/bootloader', 'build/models']]
    unit_sources = ['linux/picture_new/coach_test.c', 'linux/picture_new/coach_protocol.c', 'linux/picture_new/coach_geometry.c',
                    'linux/xinyi/xinyi_product.c', 'sw/xiangqi/xiangqi_search.c', 'sw/bootloader/crc32_fast.c']
    flags = ['-std=c11', '-O2', '-ffp-contract=off', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror']
    flags += ['-DXQ_GEOMETRY_FAST='+str(int(a.geometry_fast)), '-DXQ_GEOMETRY_ARITH='+str(int(a.geometry_arith))]
    script = ['set -eu', 'export PATH=/opt/toolchain/bin:/usr/local/bin:/usr/bin:/bin']
    for target, cc, extra, prefix in [('host', 'gcc', [], []), ('qemu', '/opt/toolchain/bin/riscv32-linux-musl-gcc',
        ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'], ['qemu-riscv32'])]:
        binary = native+'/build/unit-'+target
        script.append(shlex.join([cc, *flags, *extra, *includes, *[native+'/'+s for s in unit_sources],
                                 '-Wl,--gc-sections', '-lm', '-o', binary]))
        script.append(shlex.join([*prefix, binary, native+'/build/unit-result-'+target+'.txt']))
        partial=native+'/build/partial-'+target
        partial_sources=['linux/picture_new/coach_partial_test.c',*unit_sources[1:]]
        script.append(shlex.join([cc,*flags,*extra,*includes,*[native+'/'+s for s in partial_sources],
                                 '-Wl,--gc-sections','-lm','-o',partial]))
        script.append(shlex.join([*prefix,partial]))
        guard = native+'/build/guard-'+target
        script.append(shlex.join([cc, *flags, *extra, *includes,
                                 native+'/linux/picture_new/coach_guard_test.c',
                                 native+'/linux/picture_new/coach_driver_guard.c', '-o', guard]))
        for mode in ['busy', 'unknown', 'stale']:
            script.append(shlex.join([*prefix, guard, mode]))
        producer = native+'/build/producer-'+target
        script.append(shlex.join([cc, *flags, *extra, *includes,
                                 native+'/linux/picture_new/coach_producer_test.c',
                                 native+'/linux/picture_new/coach_protocol.c',
                                 native+'/sw/bootloader/crc32_fast.c', '-Wl,--gc-sections', '-lm', '-o', producer]))
        script.append(shlex.join([*prefix, producer, native+'/build/producer-result-'+target+'.txt']))
        name = 'rv32' if target == 'qemu' else 'host'
        for builder, suffix in [('build_native_coach.sh', 'coach'), ('build_native_v321.sh', 'legacy')]:
            build = native+'/build/worker-'+suffix+'-'+target
            settings = (['XQ_HWC_DETECTOR=1'] if a.hwc_detector else []) + (['XQ_GRID_RECOVERY=1'] if a.grid_recovery else []) + (['XQ_FAST_FP32_BILINEAR=1'] if a.fast_fp32_bilinear else []) + (['XQ_HWC_RGB_QUANT=1'] if a.hwc_rgb_quant else [])
            settings += (['XQ_GEOMETRY_FAST=1'] if a.geometry_fast else []) + (['XQ_GEOMETRY_ARITH=1'] if a.geometry_arith else [])
            environment = ['env', *settings] if settings and suffix == 'coach' else []
            script.append(shlex.join([*environment, 'bash', native+'/linux/picture_new/'+builder, native, build, native+'/build/models', name]))
            worker = build+('/xq-coach-worker' if suffix == 'coach' else '/xq-native-worker')
            request = native+'/build/fixture/'+('coach-request.txt' if suffix == 'coach' else 'old-request.txt')
            output = native+'/build/worker-result-'+suffix+'-'+target+'.txt'
            invocation = shlex.join([*prefix, worker, '--models', native+'/build/models', '--cpu-reference', '--request', request,
                                     '--input', native+'/build/fixture/frame.rgb565', '--output', output])
            if a.hwc_detector and suffix == 'coach':
                script.append('set +e; '+invocation+'; worker_status=$?; set -e; test "$worker_status" -eq 2; test ! -e '+q(output))
            else:
                script.append('set +e; '+invocation+'; worker_status=$?; set -e; test "$worker_status" -eq 1; test -s '+q(output))
            if suffix == 'coach':
                manual = shlex.join([*prefix, worker, '--manual-corners', '/nonexistent'])
                script.append('set +e; '+manual+'; manual_status=$?; set -e; test "$manual_status" -eq 2')
        mock_build = native+'/build/lifecycle-worker-'+target
        settings = (['XQ_HWC_DETECTOR=1'] if a.hwc_detector else []) + (['XQ_GRID_RECOVERY=1'] if a.grid_recovery else []) + (['XQ_FAST_FP32_BILINEAR=1'] if a.fast_fp32_bilinear else []) + (['XQ_HWC_RGB_QUANT=1'] if a.hwc_rgb_quant else [])
        settings += (['XQ_GEOMETRY_FAST=1'] if a.geometry_fast else []) + (['XQ_GEOMETRY_ARITH=1'] if a.geometry_arith else [])
        environment = ['env', *settings] if settings else []
        script.append(shlex.join([*environment, 'bash', native+'/linux/picture_new/build_test_coach_worker.sh', native,
                                 mock_build, native+'/build/models', name]))
        lifecycle = ['python3', native+'/scripts/check_picture_coach_lifecycle.py',
                     '--worker', mock_build+'/xq-coach-worker-hostmock', '--models', native+'/build/models',
                     '--frame', native+'/build/fixture/frame.rgb565', '--output', native+'/build/lifecycle-'+target]
        if target == 'qemu':
            lifecycle.append('--qemu')
        script.append(shlex.join(lifecycle))
    build_script = ('\n'.join(script)+'\n').encode();(out/'build.sh').write_bytes(build_script)
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name, blob in {**data, 'build.sh': build_script}.items():
            item = tarfile.TarInfo(name);item.size = len(blob);item.mode = 0o644;archive.addfile(item, io.BytesIO(blob))
    command = 'set -eu; test ! -e '+q(native)+'; mkdir -p '+q(native+'/build')+'; tar -xf - -C '+q(native)
    command += '; timeout --kill-after=5 '+str(a.timeout_seconds)+' sh '+q(native+'/build.sh')
    with (out/'build.log').open('wb') as log:
        result = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'sh', '-c', command], input=payload.getvalue(),
                                stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout_seconds+60)
    log_data = (out/'build.log').read_bytes()
    assert result.returncode == 0, log_data.decode(errors='replace')[-6000:]
    markers = ['XQCOACH_90_GRID_AND_REAL_CONFIDENCE_PASS', 'XQCOACH_THREE_ROOKS_DELETE_ONLY_LEGACY_REJECT_PASS',
               'XQCOACH_DUPLICATE_CELL_SAME_SIDE_KINGS_AND_MISSING_KING_PASS',
               'XQCOACH_ORIENTATION_NO_VOTES_CONFLICT_AND_UNCHANGED_MARGIN_REJECT_PASS',
               'XQCOACH_IDENTITY_RAW_BODY_CRC_RANGES_FINITE_AND_OLD_PROTOCOL_REJECT_PASS',
               'XQCOACH_GEOMETRY_REJECT_KEEP_PREVIOUS_AND_ATOMIC_IPC_PASS',
               'XQCOACH_RELEASE9_EMPTY_IDENTITY_AND_KEEP_PREVIOUS_PASS',
               'XQCOACH_ACTUAL_PRODUCER_GEOMETRY_2_5_6_TO_5_ONLY_DIAGNOSTICS_UNCHANGED_PASS',
               'XQCOACH_CANCEL_RELEASE9_IDLE_REUSE_TERM_AND_UNPROVEN_DRAIN_HOSTMOCK_PASS']
    for marker in markers:
        assert log_data.count(marker.encode()) == 2, marker
    assert log_data.count(b'XQCOACH_GUARD_DONE_ERRORS_BUSY_UNKNOWN_AND_STICKY_REJECT_PASS') == 4
    assert log_data.count(b'XQCOACH_GUARD_PREVIOUS_DONE_CANNOT_PROVE_FAILED_NEW_JOB_DRAIN_PASS') == 2
    if a.hwc_detector:
        assert log_data.count(b'XQ_NATIVE_HWC_EXACT_DRIVER_REQUIRED no_fallback=1') == 2
    assert b'XQ_NATIVE_STAGE' not in log_data and b'XQ_NATIVE_RECOGNITION' not in log_data, 'Bad raw CRC must not execute graph'
    wanted = ['unit-host', 'unit-qemu', 'guard-host', 'guard-qemu', 'producer-host', 'producer-qemu',
              'producer-result-host.txt', 'producer-result-qemu.txt']
    for target in ['host', 'qemu']:
        wanted += ([] if a.hwc_detector else ['worker-result-coach-'+target+'.txt'])
        wanted += ['worker-result-legacy-'+target+'.txt', 'unit-result-'+target+'.txt',
                   'worker-coach-'+target, 'worker-legacy-'+target,
                   'lifecycle-'+target, 'lifecycle-worker-'+target]
    archive_data = subprocess.check_output(['wsl.exe', '-d', a.distribution, '--', 'tar', '-cf', '-', '-C', native+'/build', *wanted], timeout=60)
    with tarfile.open(fileobj=io.BytesIO(archive_data)) as archive:
        for item in archive.getmembers():
            if not item.isfile():
                continue
            relative = Path(item.name);assert not relative.is_absolute() and '..' not in relative.parts
            destination = out/relative;destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(item).read())
    for target in ['host', 'qemu']:
        coach_path = out/('worker-result-coach-'+target+'.txt')
        legacy = (out/('worker-result-legacy-'+target+'.txt')).read_bytes()
        if a.hwc_detector:
            assert not coach_path.exists()
        else:
            assert coach_path.read_bytes() == f'XQ_COACH_RESULT_V1 321 52 {wrong_crc:08x} rv32-v321-coach 7 0 00000000\n'.encode()
        assert legacy == f'XQ_MODEL_RESULT_V1 321 52 {wrong_crc:08x} rv32-driver-quantized-mac 7 0\n'.encode()
    for path in [out/'unit-qemu', out/'guard-qemu', out/'producer-qemu', out/'worker-coach-qemu/xq-coach-worker',
                 out/'worker-legacy-qemu/xq-native-worker', out/'lifecycle-worker-qemu/xq-coach-worker-hostmock']:
        elf = path.read_bytes();assert elf[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', elf, 18)[0] == 243
        assert struct.unpack_from('<I', elf, 36)[0] == 0
    # Frontend owner can continue work independently. The captured repair
    # source is bound below; its current stability is reported separately.
    frontend_stable = {n: sha((R/n).read_bytes()) == h for n, h in sources.items() if n.startswith('linux/xinyi/')}
    assert all(sha((R/n).read_bytes()) == h for n, h in sources.items() if not n.startswith('linux/xinyi/'))
    assert all(sha((a.models/n).read_bytes()) == h for n, h in models.items())
    record = dict(status='PASS', hardware_used=False, scope='Host/RV32 synthetic coach geometry, 300-candidate IPC, actual worker pre-inference CRC rejection and controlled hostmock cancellation/reuse',
                  strict_refinement_changed=False, graph_arithmetic_changed=False, old_protocol_unchanged=True,
                  no_manual_or_cross_capture_geometry=True, candidates_repair_not_legal_acceptance=True,
                  release_ack_status=9, release_requires_same_identity_and_idle=True,
                  detector_hwc_candidate=a.hwc_detector,
                  grid_recovery_candidate=a.grid_recovery,
                  exact_fp32_bilinear_candidate=a.fast_fp32_bilinear,
                  hwc_rgb_quant_candidate=a.hwc_rgb_quant,
                  geometry_fast_candidate=a.geometry_fast,
                  geometry_arith_candidate=a.geometry_arith,
                  hwc_cpu_reference_rejected_before_output=a.hwc_detector,
                  timeout_busy_or_unknown_drain_withholds_ack=True,
                  tests=markers, sources_sha256=sources, models_sha256=models, source_stable=True,
                  frontend_snapshot_current=frontend_stable, native_root=native,
                  limitations='Synthetic coordinates only; no live photographs, model recognition, camera, FPGA, performance or accuracy acceptance.',
                  outputs_sha256={p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()})
    (out/'result.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print('STATELESS_COACH_CANDIDATE_IPC_HOST_RV32_PASS_NOT_BOARD')


if __name__ == '__main__':
    main()
