"""Bounded, synthetic-only PN05 graph profile/equivalence on Linux or WSL.

Example (PowerShell): wsl -d Ubuntu-22.04 -- python3
  /mnt/d/LJL/WORK/GitHub/performance_soc/scripts/check_picture_integer_graph.py
  --output /mnt/e/picture-integer-20261025/baseline --mode baseline

CPU timing in QEMU is emulator time, never RV32 hardware timing. No photographs,
dataset traversal, hardware access, training, or model export occurs here.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = 'artifacts/vision-model-20261020-adapter/runtime'
BASE = ['linux/picture_new/vision32_backend.c', 'linux/picture_new/vision32_layer.c',
        'linux/picture_new/test_v321_mock.c', 'linux/picture_new/graph_runtime.c',
        ADAPTER+'/xq_sha256.c', 'sw/bootloader/crc32_fast.c']
INCLUDES = [ADAPTER, 'linux/picture_new', 'linux/vision', 'linux/mac_accel', 'sw/bootloader']
FLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
         '-ffunction-sections', '-fdata-sections']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log, seconds, expected_codes=(0,)):
    """Stop the entire command group on timeout or Ctrl+C, preserving its log."""
    with log.open('xb') as stream:
        process = subprocess.Popen(list(map(str, command)), stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=seconds)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if code not in expected_codes:
        raise RuntimeError(f'{command[0]} exited {code}: {log}\n'+log.read_text(errors='replace')[-4000:])


def parse_profile(log):
    result = {}
    for line in log.read_text().splitlines():
        if not line.startswith('XQG_'):
            continue
        fields = dict(item.split('=', 1) for item in line.split()[1:])
        model = fields.pop('model')
        entry = result.setdefault(model, {'phases': {}, 'output_sha256': {}})
        if line.startswith('XQG_TOTAL '):
            entry.update({k: int(v) for k, v in fields.items()})
        elif line.startswith('XQG_PHASE '):
            phase = fields.pop('phase')
            entry['phases'][phase] = {k: int(v) for k, v in fields.items()}
        else:
            entry['output_sha256'][fields['index']] = fields['sha256']
    assert set(result) == {'board', 'detector', 'classifier'}
    for name, entry in result.items():
        assert entry['jobs'] == {'board': 44, 'detector': 98, 'classifier': 8}[name]
        assert len(entry['phases']) == 18 and entry['output_sha256']
        submit = entry['phases']['submit_mock']
        entry['userspace_cpu_ns_excluding_mock'] = entry['cpu']-submit['cpu']
        assert entry['userspace_cpu_ns_excluding_mock'] > 0
        for phase, row in entry['phases'].items():
            row['userspace_cpu_percent'] = (100*row['cpu']/entry['userspace_cpu_ns_excluding_mock']
                                           if phase != 'submit_mock' else None)
        accounted = sum(row['cpu'] for row in entry['phases'].values())
        entry['unattributed_cpu_ns'] = entry['cpu']-accounted
        assert entry['unattributed_cpu_ns'] >= 0, 'Overlapping instrumentation'
    return result


def inventory(models):
    result = {}
    names = {1: 'conv', 3: 'sigmoid', 4: 'maxpool', 5: 'nearest', 6: 'bilinear',
             7: 'concat', 8: 'add', 9: 'avgpool', 10: 'identity', 11: 'relu'}
    for name in ['board', 'detector', 'classifier']:
        raw = (models/(name+'.xqm')).read_bytes()
        h = struct.unpack_from('<10I', raw, 8)
        offset = 48+(16 if h[0] == 2 else 0)
        nodes = [struct.unpack_from('<32i', raw, offset+i*128) for i in range(h[2])]
        counts = Counter(names[n[0]] for n in nodes)
        decisions = [{'node': i, 'type': names[n[0]], 'carrier': 'FP32',
                      'decision': 'v1 FP32 retained; v2 selection awaits validated exporter/reference/whole-graph acceptance'}
                     for i, n in enumerate(nodes) if n[0] != 1]
        result[name] = {'node_counts': dict(counts), 'nonconv_decisions': decisions,
                        'conv_to_conv_edges': sum(n[0] == 1 and n[5] >= 0 and nodes[n[5]][0] == 1 for n in nodes)}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--mode', choices=['baseline', 'candidate'], required=True)
    ap.add_argument('--targets', choices=['host', 'host,qemu'], default='host')
    ap.add_argument('--models', type=Path, default=ROOT/'build/picture-merge-20261023/native-models')
    ap.add_argument('--inputs', type=Path, default=ROOT/'build/picture-board-resume-20261023/synthetic-inputs-r01')
    ap.add_argument('--baseline', type=Path)
    ap.add_argument('--fast-requant', action='store_true')
    ap.add_argument('--full-checks', action='store_true')
    ap.add_argument('--worker-checks', action='store_true', help='Output must be a lexical repo/build/ path (E junction is supported).')
    ap.add_argument('--sanitize', action='store_true', help='Host memory/UB checks; timing is not a performance result.')
    ap.add_argument('--classifier-s16', choices=['0','1'], default='1', help='Authorized integer GAP;0 preserves PN05 r03 rollback.')
    ap.add_argument('--timeout-seconds', type=int, default=180)
    a = ap.parse_args()
    classifier_s16=a.mode=='candidate' and a.classifier_s16=='1'
    assert os.name == 'posix', 'Invoke under WSL/Linux'
    assert 30 <= a.timeout_seconds <= 3600
    assert not a.sanitize or (a.targets == 'host' and not a.worker_checks)
    assert not a.output.exists(), 'Preserve all previous receipts'
    expected = json.loads((a.inputs/'expected.json').read_text())
    manifest = json.loads((a.inputs/'manifest.json').read_text())
    assert 'no photographs' in manifest['scope']
    assert sha(a.inputs/'manifest.json') == expected['synthetic_input_manifest_sha256']
    fixture = {}
    for i, name in enumerate(['board', 'detector', 'classifier']):
        model, inp = a.models/(name+'.xqm'), a.inputs/(name+'.input')
        assert sha(model) == expected['model_pack_sha256'][name]
        assert manifest['models'][i]['model'] == name and sha(inp) == manifest['models'][i]['sha256']
        fixture[str(model)] = sha(model);fixture[str(inp)] = sha(inp)
    sources = set(BASE+['linux/picture_new/graph_profile.c', 'linux/picture_new/graph_profile.h',
                        'linux/picture_new/test_graph_profile.c', 'linux/picture_new/test_v321_golden.c',
                        'linux/picture_new/test_v321_mock.h', 'linux/picture_new/vision32_locality.c',
                        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
                        'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h',
                        'linux/mac_accel/pango_mac_uapi.h', 'linux/vision/xq_mac.h',
                        'sw/bootloader/crc32_fast.h', 'scripts/check_picture_integer_graph.py'])
    sources.update(p.relative_to(ROOT).as_posix() for p in (ROOT/ADAPTER).glob('*.h'))
    # Carrier implementation is an ordinary source, optional only during initial baseline capture.
    tensor = ROOT/'linux/picture_new/graph_tensor.c'
    if tensor.exists():
        sources.update(['linux/picture_new/graph_tensor.c', 'linux/picture_new/graph_tensor.h'])
    if classifier_s16:
        sources.update(['linux/picture_new/graph_ops.c','linux/picture_new/graph_ops.h',
                        'linux/picture_new/test_classifier_s16_reference.c','scripts/classifier_reference.py'])
    if a.full_checks:
        sources.update(['linux/picture_new/test_graph_tensor.c', 'linux/picture_new/test_graph_runtime.c',
                        'scripts/check_picture_r14_v321.py'])
    if a.worker_checks:
        for directory in ['artifacts/vision-model-20261020-adapter/runtime', 'linux/picture_new',
                          'linux/vision', 'sw/xiangqi',
                          'artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref']:
            sources.update(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).glob('*')
                           if p.is_file() and p.suffix in ('.c', '.h'))
        sources.update(['linux/picture_new/build_native_coach.sh', 'linux/picture_new/build_test_coach_worker.sh',
                        'scripts/check_picture_coach_lifecycle.py', 'linux/picture_new/r14-models.sha256',
                        'artifacts/vision-model-20261020/geometry/geometry_reference.c'])
        for name in ['native_parameters.h', 'refinement_rng.bin']:
            fixture[str(a.models/name)] = sha(a.models/name)
    hashes = {name: sha(ROOT/name) for name in sorted(sources)}
    a.output.mkdir(parents=True)
    result = {'status': 'RUNNING', 'mode': a.mode, 'fast_requant': a.fast_requant,
              'classifier_s16':classifier_s16,'detector_integer_graph_selected':False,
              'sanitized': a.sanitize, 'hardware_used': False,
              'accuracy_accepted': False, 'production_ready': False,
              'source_sha256': hashes, 'fixture_sha256': fixture,
              'inventory': inventory(a.models), 'targets': {},
              'limitations': 'Synthetic B1; independent CPU V321 mock. Host/QEMU times are not board latency. '
                             'No selection-set or accuracy acceptance; detector switch waits for r24b. '
                             'Output layout/requant are fused. Kernel staging copy/wait split unavailable.'}
    save = lambda: (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    save()
    try:
        targets = [('host', 'gcc', [], [])]
        if a.targets == 'host,qemu':
            targets.append(('qemu', '/opt/toolchain/bin/riscv32-linux-musl-gcc',
                            ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'], ['qemu-riscv32']))
        for target, cc, extra, prefix in targets:
            flags = FLAGS+extra+['-I'+str(ROOT/d) for d in INCLUDES]
            if a.sanitize:
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
            flags += ['-DXQ_INTEGER_CARRIER='+('0' if a.mode == 'baseline' else '1')]
            flags += ['-DXQ_FAST_REQUANT='+str(int(a.fast_requant))]
            flags += ['-DXQ_CLASSIFIER_S16='+str(int(classifier_s16))]
            common = [str(ROOT/n) for n in BASE]
            if tensor.exists():
                common.append(str(tensor))
            if classifier_s16:
                common.append(str(ROOT/'linux/picture_new/graph_ops.c'))
            binary = a.output/(target+'-profile')
            command = [cc, *flags, '-DXQ_GRAPH_PROFILE', '-DXQ_NATIVE_COACH', *common,
                       str(ROOT/'linux/picture_new/graph_profile.c'),
                       str(ROOT/'linux/picture_new/test_graph_profile.c'),
                       '-Wl,--wrap=ioctl', '-Wl,--gc-sections', '-lm', '-o', binary]
            run(command, a.output/(target+'-profile-compile.log'), 90)
            log = a.output/(target+'-profile.log')
            run([*prefix, binary, a.models, a.inputs], log, a.timeout_seconds)
            assert log.read_text().count('PN05_GRAPH_PROFILE kind=') == 3
            profile = parse_profile(log)
            result['targets'][target] = {'profile': profile, 'profile_binary_sha256': sha(binary)}
            if a.full_checks:
                unit = a.output/(target+'-tensor')
                run([cc, *flags, str(ROOT/'linux/picture_new/test_graph_tensor.c'),
                     str(tensor), str(ROOT/'linux/picture_new/vision32_layer.c'),
                     '-Wl,--gc-sections', '-lm', '-o', unit],
                    a.output/(target+'-tensor-compile.log'), 90)
                unit_log = a.output/(target+'-tensor.log')
                run([*prefix, unit], unit_log, a.timeout_seconds)
                assert 'GRAPH_TENSOR_EXHAUSTIVE_PASS' in unit_log.read_text()
                golden = a.output/(target+'-golden')
                selected_expected=expected
                if classifier_s16:
                    from classifier_reference import verify
                    selected_expected,reference=verify(cc,flags,common,prefix,a.models,a.inputs,a.output,target,expected,a.timeout_seconds)
                    result['targets'][target]['classifier_int64_reference']=reference
                    assert profile['classifier']['output_sha256']['0']==reference['samples'][0]['final_sha256']
                run([cc, *flags, *common, str(ROOT/'linux/picture_new/test_v321_golden.c'),
                     '-Wl,--wrap=ioctl', '-Wl,--gc-sections', '-lm', '-o', golden],
                    a.output/(target+'-golden-compile.log'), 90)
                checks = a.output/(target+'-checks.txt')
                golden_log = a.output/(target+'-golden.log')
                run([*prefix, golden, a.models, a.inputs, checks, '--mock-v321'], golden_log, a.timeout_seconds)
                import check_picture_r14_v321
                result['targets'][target]['golden'] = check_picture_r14_v321.compare(selected_expected, checks.read_bytes())
                result['targets'][target]['golden']['expected_variant']=selected_expected.get('variant','immutable original80')
                run([*prefix, golden, a.models, a.inputs, a.output/(target+'-failure.txt'), '--fail-second-ioctl'],
                    a.output/(target+'-failure.log'), a.timeout_seconds)
                assert 'V321_MOCK_IOCTL_ERROR_FATAL_PASS' in (a.output/(target+'-failure.log')).read_text()
                result['targets'][target]['unit_and_fatal_error_pass'] = True
                bad_refs = a.output/'bad-refcount.xqm'
                duplicate = a.output/'duplicate-output.xqm'
                if not bad_refs.exists():
                    raw = bytearray((a.models/'classifier.xqm').read_bytes())
                    h = struct.unpack_from('<10I', raw, 8)
                    node_offset = 48+(16 if h[0] == 2 else 0)
                    struct.pack_into('<i', raw, node_offset+26*4, 1+struct.unpack_from('<i', raw, node_offset+26*4)[0])
                    struct.pack_into('<I', raw, 44, zlib.crc32(raw[48:]))
                    bad_refs.write_bytes(raw)
                    raw = bytearray((a.models/'classifier.xqm').read_bytes())
                    struct.pack_into('<I', raw, 20, 2)
                    struct.pack_into('<I', raw, 28, struct.unpack_from('<I', raw, 24)[0])
                    duplicate.write_bytes(raw)
                lifecycle = a.output/(target+'-runtime')
                run([cc, *flags, *common, str(ROOT/'linux/picture_new/test_graph_runtime.c'),
                     '-Wl,--wrap=ioctl,--wrap=malloc', '-Wl,--gc-sections', '-lm', '-o', lifecycle],
                    a.output/(target+'-runtime-compile.log'), 90)
                lifecycle_log = a.output/(target+'-runtime.log')
                run([*prefix, lifecycle, a.models/'classifier.xqm', bad_refs, duplicate], lifecycle_log, a.timeout_seconds)
                assert 'GRAPH_RUNTIME_REUSE_CANCEL_IOCTL_OOM_AND_BAD_LIVENESS_PASS' in lifecycle_log.read_text()
                result['targets'][target]['batch3_sha256'] = re.search(r'GRAPH_RUNTIME_BATCH3 sha256=(\w{64})', lifecycle_log.read_text())[1]
                if target == 'qemu':
                    elf = golden.read_bytes()
                    assert elf[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', elf, 18)[0] == 243
                    assert struct.unpack_from('<I', elf, 36)[0] == 0, 'Require RV32 soft float, no compressed ISA'
            if a.worker_checks:
                worker_out = a.output/('worker-'+target)
                # Candidate must use the actual builder default, not an opt-in
                # environment override that could conceal a wrong default.
                env = ['env', '-u', 'XQ_INTEGER_GRAPH', '-u','XQ_CLASSIFIER_S16'] if a.mode == 'candidate' else ['env', 'XQ_INTEGER_GRAPH=0']
                if a.mode=='candidate' and not classifier_s16:env.append('XQ_CLASSIFIER_S16=0')
                run([*env, 'bash', ROOT/'linux/picture_new/build_native_coach.sh', ROOT, worker_out,
                     a.models, 'rv32' if target == 'qemu' else 'host'], a.output/(target+'-worker-build.log'), 180)
                frame, request = a.output/'zero.rgb565', a.output/'request.txt'
                if not frame.exists():
                    frame.write_bytes(bytes(1843200))
                    request.write_text(f'XQ_COACH_REQUEST_V1 321 52 {zlib.crc32(frame.read_bytes())^1:08x} rv32-v321-coach\n')
                response = a.output/(target+'-response.txt')
                worker_log = a.output/(target+'-worker.log')
                worker = worker_out/'xq-coach-worker'
                config = (worker_out/'runtime-config.txt').read_text()
                assert 'integer_carrier='+str(int(a.mode == 'candidate'))+'\n' in config
                assert 'classifier_s16_gap='+str(int(classifier_s16))+'\n' in config
                run([*prefix, worker, '--models', a.models, '--cpu-reference', '--request', request,
                     '--input', frame, '--output', response], worker_log, 60, expected_codes=(1,))
                assert response.read_text() == f'XQ_COACH_RESULT_V1 321 52 {zlib.crc32(frame.read_bytes())^1:08x} rv32-v321-coach 7 0 00000000\n'
                assert 'XQ_NATIVE_STAGE' not in worker_log.read_text()
                mock_out = a.output/('worker-lifecycle-'+target)
                run([*env, 'bash', ROOT/'linux/picture_new/build_test_coach_worker.sh', ROOT, mock_out,
                     a.models, 'rv32' if target == 'qemu' else 'host'], a.output/(target+'-lifecycle-build.log'), 180)
                command = [sys.executable, ROOT/'scripts/check_picture_coach_lifecycle.py',
                           '--worker', mock_out/'xq-coach-worker-hostmock', '--models', a.models,
                           '--frame', frame, '--output', a.output/('ipc-'+target)]
                if target == 'qemu':
                    command.append('--qemu')
                run(command, a.output/(target+'-ipc.log'), a.timeout_seconds)
                assert 'XQCOACH_CANCEL_RELEASE9_IDLE_REUSE_TERM_AND_UNPROVEN_DRAIN_HOSTMOCK_PASS' in (a.output/(target+'-ipc.log')).read_text()
                result['targets'][target]['worker_sha256'] = sha(worker)
                result['targets'][target]['builder_default_integer_carrier'] = a.mode == 'candidate'
                result['targets'][target]['builder_default_classifier_s16']=classifier_s16
                result['targets'][target]['worker_crc_rejection_and_ipc_pass'] = True
                if target == 'qemu':
                    elf = worker.read_bytes()
                    assert struct.unpack_from('<H', elf, 18)[0] == 243 and struct.unpack_from('<I', elf, 36)[0] == 0
            save()
        if a.baseline:
            before = json.loads((a.baseline/'result.json').read_text())
            assert before['status'] == 'PASS' and before['mode'] == 'baseline'
            result['baseline_receipt_sha256'] = sha(a.baseline/'result.json')
            result['legacy_profile_outputs']={target:{model:entry['output_sha256'] for model,entry in value['profile'].items()}
                                              for target,value in before['targets'].items()}
            for target in set(before['targets']) & set(result['targets']):
                for model in ['board', 'detector', 'classifier']:
                    old = before['targets'][target]['profile'][model]
                    new = result['targets'][target]['profile'][model]
                    if model!='classifier' or not classifier_s16:
                        assert old['output_sha256'] == new['output_sha256'], 'Graph output bytes changed'
                    if a.mode == 'candidate':
                        assert new['phases']['integer_requantize']['values'] > 0
                        assert new['phases']['dequantize']['values'] < old['phases']['dequantize']['values']
        assert all(sha(ROOT/n) == h for n, h in hashes.items()), 'Source changed during run'
        assert all(sha(Path(n)) == h for n, h in fixture.items()), 'Fixture changed'
        result['status'] = 'PASS'
    except BaseException as error:
        result.update(status='FAILED_PRESERVED', error=repr(error))
        raise
    finally:
        save()
    print('PICTURE_GRAPH_'+a.mode.upper()+'_PASS_NOT_BOARD')
    for name, entry in result['targets']['host']['profile'].items():
        rows = sorted(((k, v) for k, v in entry['phases'].items() if k != 'submit_mock'),
                      key=lambda row: row[1]['cpu'], reverse=True)[:5]
        print(name, ' '.join(f'{k}={v["userspace_cpu_percent"]:.1f}%' for k, v in rows))


if __name__ == '__main__':
    main()
