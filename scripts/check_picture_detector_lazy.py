"""Compare lazy bbox decode to the immutable decoder, with no photo or FPGA."""
import argparse
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path
from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--benchmark', action='store_true', help='Optional bounded no-probe synthetic timing; never board latency')
    args = parser.parse_args()
    assert args.output.absolute().is_relative_to(ROOT / 'build')
    out = workspace_path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    source = ROOT / 'artifacts/vision-model-20261020-adapter/runtime/xq_native_worker.c'
    overlay = ROOT / 'linux/picture_new/coach_decode_worker.c'
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    original, private = source.read_text(), overlay.read_text()
    assert re.search(r'Source SHA256 ([0-9a-f]{64})', private)[1] == sha(source)
    private = private[private.index('#define _POSIX_C_SOURCE'):]
    for name in ['HEADER', 'BOARD_BUFFER', 'DETECT']:
        begin_rgb, end_rgb = '/* XQRGB8_' + name + '_BEGIN */\n', '/* XQRGB8_' + name + '_END */\n'
        start_rgb = private.index(begin_rgb)
        stop_rgb = private.index(end_rgb, start_rgb) + len(end_rgb)
        region_rgb = private[start_rgb:stop_rgb]
        if name == 'HEADER':
            restored_rgb = ''
        else:
            restored_rgb = region_rgb.split('\n#else\n', 1)[1].rsplit('#endif\n', 1)[0]
        private = private[:start_rgb] + restored_rgb + private[stop_rgb:]
    begin, end = '/* XQDECODE_LAZY_BEGIN */\n', '/* XQDECODE_LAZY_END */\n'
    start = private.index(begin)
    stop = private.index(end, start) + len(end)
    region = private[start:stop]
    rollback = region.split('\n#else\n', 1)[1].rsplit('#endif\n', 1)[0]
    assert private[:start] + rollback + private[stop:] == original, 'Rollback must restore every frozen byte'
    # The oracle is the actual original proposal decoder and NMS, with only
    # its callable name and a pre-NMS observation seam mechanically changed.
    reference = original[original.index('typedef struct {xqr_box box;unsigned order;} proposal;'):
                         original.index('static int result_packet(')]
    reference = reference.replace('static int detector_boxes(',
        'static unsigned capture_nms(proposal *,unsigned,xqr_box [300]);\nstatic int reference_detector_boxes(', 1)
    assert reference.count('*count=nms(p,n,out);') == 1
    reference = reference.replace('*count=nms(p,n,out);', '*count=capture_nms(p,n,out);')
    assert reference.count('if(obj<=.001f)continue;') == 1
    reference = reference.replace('if(obj<=.001f)continue;', 'if(obj<=.001f)continue;\n            XQDECODE_NOTE_OBJ();', 1)
    assert reference.count('            float cx=') == 1
    reference = reference.replace('            float cx=', '            XQDECODE_NOTE_BOX();\n            float cx=', 1)
    (out / 'decoder_reference.inc').write_text(reference, newline='\n')
    files = ['artifacts/vision-model-20261020-adapter/runtime/xq_native_worker.c',
             'linux/picture_new/coach_decode_worker.c', 'linux/picture_new/detector_lazy_decode.h',
             'linux/picture_new/test_detector_lazy_decode.c', 'scripts/check_picture_detector_lazy.py',
             'build/picture-merge-20261023/native-models/native_parameters.h']
    includes = [out, ROOT / 'linux/picture_new', ROOT / 'linux/vision', ROOT / 'linux/mac_accel',
                ROOT / 'sw/xiangqi', ROOT / 'artifacts/vision-model-20261020-adapter/runtime',
                ROOT / 'build/picture-merge-20261023/native-models']
    for directory in includes[1:]:
        files.extend(p.relative_to(ROOT).as_posix() for p in directory.glob('*.h'))
    before = {name: sha(ROOT / name) for name in sorted(set(files))}
    rows = []
    def run(name, argv, seconds=120, expected_failure=False):
        with (out / (name + '.log')).open('xb') as log:
            result = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 ' + str(seconds) + ' ' + shlex.join(argv)],
                stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 15)
        text = (out / (name + '.log')).read_text(errors='replace')
        if expected_failure:
            assert result.returncode != 0 and 'Assertion' in text, (name, text[-1000:])
        else:
            assert result.returncode == 0, (name, text[-2000:])
        return text
    test = ROOT / 'linux/picture_new/test_detector_lazy_decode.c'
    for target in ['host', 'rv32', 'sanitizer']:
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'gcc'
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off']
        if target == 'rv32':
            flags += ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align']
        if target == 'sanitizer':
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        common = [cc, *flags, *['-I' + wsl_path(p) for p in includes], wsl_path(test), '-Wl,--wrap=malloc', '-lm']
        binary = out / target
        run(target + '-build', [*common, '-DXQDECODE_TEST_PROBE', '-o', wsl_path(binary)])
        text = run(target, [*(['qemu-riscv32'] if target == 'rv32' else []), wsl_path(binary)])
        assert 'DETECTOR_LAZY_PRE_NMS_NMS_THRESHOLDS_NONFINITE_DIMS_OOM_PASS' in text
        rows.append(dict(target=target, result=text.strip()))
        if target != 'sanitizer':
            timing = out / (target + '-timing')
            run(target + '-timing-build', [*common, '-o', wsl_path(timing)])
            text = run(target + '-no-probe-correctness', [*(['qemu-riscv32'] if target == 'rv32' else []), wsl_path(timing)])
            assert 'DETECTOR_LAZY_PRE_NMS_NMS_THRESHOLDS_NONFINITE_DIMS_OOM_PASS' in text
            rows[-1]['no_probe_correctness_result'] = text.strip()
            if args.benchmark:
                text = run(target + '-timing', [*(['qemu-riscv32'] if target == 'rv32' else []), wsl_path(timing), '--bench'])
                rows[-1]['no_probe_synthetic_timings'] = text.splitlines()
    # The independent strict-threshold checks must catch dropping class scores
    # that pass the original .001 gate; change the candidate gate only.
    negative = out / 'negative-threshold'
    negative.mkdir()
    header = (ROOT / 'linux/picture_new/detector_lazy_decode.h').read_text()
    assert header.count('if(scores[cls]>.001f)any=1;') == 1
    (negative / 'detector_lazy_decode.h').write_text(header.replace('if(scores[cls]>.001f)any=1;', 'if(scores[cls]>.01f)any=1;'))
    (negative / 'test.c').write_bytes(test.read_bytes())
    binary = negative / 'test'
    run('negative-build', ['gcc', '-std=c11', '-O2', '-ffp-contract=off', '-DXQDECODE_TEST_PROBE',
        *['-I' + wsl_path(p) for p in [negative, *includes]], wsl_path(negative / 'test.c'),
        '-Wl,--wrap=malloc', '-lm', '-o', wsl_path(binary)])
    run('negative-run', [wsl_path(binary)], 20, expected_failure=True)
    assert before == {name: sha(ROOT / name) for name in before}
    receipt = dict(status='LAZY_BBOX_ORIGINAL_PROPOSALS_NMS_HOST_RV32_SANITIZERS_NEGATIVE_GATE_PASS_NOT_BOARD',
        source_sha256=before, hardware_used=False, image_access=False, source_rollback_byte_exact=True,
        full_pre_nms_and_final_output_bytes_compared=True, original_proposal_allocation_unchanged=True,
        nan_bbox_original_overlap_semantics_preserved=True, floating_status_flags_and_errno_not_observed_by_worker=True,
        wrong_threshold_negative_control_rejected=True, checks=rows,
        benchmark_requested=args.benchmark, benchmark_scope='synthetic inactive-class and sparse-candidate anchors; not board or whole product')
    (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['status'])


if __name__ == '__main__':
    main()
