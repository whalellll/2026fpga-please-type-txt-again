"""Archive a redacted engineering outcome; keep camera files/identifiers in build/."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zlib

REPO = Path(__file__).resolve().parents[2]
LIVE = REPO / 'build/picture-p21-native/live-sd-r01'
DEST = REPO / 'docs/validation/picture-p21-runtime-20261020/live-native-sd-r01'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    data = path.read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')


def recognition(text):
    rows = [line for line in text.splitlines() if line.startswith('XQ_NATIVE_RECOGNITION ')]
    assert len(rows) == 1, 'Require exactly one complete inference'
    result = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', rows[0])}
    required = {'status', 'models_loaded', 'executed_mask', 'cpu_reference',
                'board_ms', 'detector_ms', 'classifier_ms', 'refine_ms', 'assign_ms',
                'total_ms', 'proposals', 'fixed', 'crossings', 'inliers', 'jobs', 'cycles'}
    assert set(result) == required
    return rows[0], result


def main():
    assert not DEST.exists(), 'Use a fresh archive; never replace evidence'
    # Validate local capture binding without publishing any camera identifiers.
    raw = (LIVE / 'frame.rgb565').read_bytes()
    request = (LIVE / 'request.txt').read_text().split()
    assert len(raw) == 1280 * 720 * 2
    assert len(request) == 5 and request[0] == 'XQ_MODEL_REQUEST_V1'
    assert request[4] == 'rv32-driver-quantized-mac'
    assert zlib.crc32(raw) == int(request[3], 16)
    references = json.loads((LIVE / 'pc-references.json').read_text())
    digest = hashlib.sha256(raw).hexdigest()
    assert references['input_sha256'] == digest
    assert references['input_crc32'] == request[3]
    packet = (LIVE / 'cpu-int32-reference.packet').read_text().splitlines()[0].split()
    assert len(packet) == 7 and packet[0] == 'XQ_MODEL_RESULT_V1'
    assert packet[1:4] == request[1:4]
    assert packet[4:] == ['cpu-int32-reference', '6', '0']
    pc = {}
    for name in ('pc-fp32', 'pc-quantized-mac', 'explicit-int32-reference'):
        pc[name] = json.loads((LIVE / (name + '.json')).read_text())
        assert pc[name]['frame']['sha256'] == digest
    assert pc['pc-fp32']['status'] == 'candidate_board'
    assert pc['pc-quantized-mac']['status'] == 'cell_conflict'
    assert len(pc['pc-quantized-mac']['issues']) == 4
    assert pc['explicit-int32-reference']['diagnostic_backend'] == 'EXPLICIT_INT32_ORACLE_NOT_ORIGINAL_TORCH_INT_MM'
    assert pc['explicit-int32-reference']['status'] == 'candidate_board'
    for name in ('pc-fp32', 'explicit-int32-reference'):
        counts = Counter(piece['class_name'] for piece in pc[name]['pieces'])
        assert counts['black_jiang'] == 0 and counts['black_zu'] == 7
    native_text = read(LIVE / 'native-final.log')
    line, native = recognition(native_text)
    _, cpu = recognition(read(LIVE / 'cpu-int32-reference.log'))
    assert native['status'] == 6 and native['models_loaded'] == 3
    assert native['executed_mask'] == 7 and native['cpu_reference'] == 0
    assert native['jobs'] == 62526 and native['cycles'] == 538735461
    assert native['total_ms'] == 3292131
    for key in ('status', 'models_loaded', 'executed_mask', 'proposals', 'fixed', 'crossings', 'inliers'):
        assert native[key] == cpu[key], key
    assert cpu['cpu_reference'] == 1 and cpu['jobs'] == 0
    assert 'NATIVE_GUI_IDLE_AFTER_RESULT' in native_text and 'XQ_ADAPTER_DONE=0' in native_text
    gui = read(LIVE / 'gui-final-observation-r01.log')
    reject_lines = [
        'XQ_MODEL_REJECT strict_result_or_identity_invalid no_fallback=1',
        'XQ_PICTURE_RECOGNIZE_FAIL backend=rv32-driver-quantized-mac no_fallback=1',
    ]
    assert all(item in gui for item in reject_lines)
    assert re.search(r'^XQ LINUX INJECT STATUS .*engine=ready nodes=0 ', gui, re.M)
    boot_path = REPO / 'docs/validation/picture-native-sd-20261020/boot-r03/result.json'
    boot = json.loads(boot_path.read_text())
    assert boot['status'] == 'SD_BOOT_AND_THREE_MODEL_DEPLOYMENT_PASS'
    assert boot['kernel_driver_features'] == '0x67' and not boot['flash_written']
    display_path = REPO / 'docs/validation/picture-native-sd-20261020/human-display-confirmation-20261020.json'
    display = json.loads(display_path.read_text(encoding='utf-8'))
    assert display['chess_page_retained_during_recognition'] and display['recognition_status_visible']
    package_check = read(REPO / 'build/picture-p21-native/final-live-package-check.log')
    adapter_check = read(REPO / 'build/picture-p21-native/final-live-adapter-check.log')
    assert json.loads(package_check)['package_integrity_passed'] is True
    assert 'PICTURE_MODEL_MANIFEST_PASS' in adapter_check
    # Reuse the passed full suite only after verifying every recorded input.
    regression_path = REPO / 'docs/validation/picture-p21-runtime-20261020/regression-r05.json'
    regression = json.loads(regression_path.read_text())
    assert regression['status'] == 'PASS' and regression['marker'] == 'SOC_ALL_TESTS_PASS'
    checked = {}
    for group in ('source_files_sha256', 'test_files_sha256', 'linux_files_sha256'):
        for relative, expected in regression[group].items():
            assert sha(REPO / relative) == expected, relative
        checked[group] = len(regression[group])
    result = dict(
        schema_version=1, recorded_utc=datetime.now(timezone.utc).isoformat(),
        status='NATIVE_LIVE_REJECTION_PATH_PASS',
        scope='Real camera, three native FPGA models, IPC consumption and safe GUI rejection; NOT positive recognition acceptance',
        backend='rv32-driver-quantized-mac', models_loaded=3, executed_mask=7,
        cpu_reference=False, native_status=6,
        stage_ms={key: native[key] for key in ('board_ms', 'detector_ms', 'classifier_ms', 'refine_ms', 'assign_ms', 'total_ms')},
        actual_mac_jobs=native['jobs'], actual_mac_busy_cycles=native['cycles'],
        mac_timebase_hz=49500000, mac_busy_seconds=native['cycles'] / 49500000,
        latency_sample_count=1, clean_latency_benchmark=False, p50_p95_available=False,
        timing_contention=['Concurrent UART image transfer', 'Bounded synthetic piece_fit numeric diagnostics'],
        elapsed_seconds=native['total_ms'] / 1000, five_second_gate_passed=False,
        pc_input_binding_verified_locally=True,
        native_and_cpu_reference_aggregate_diagnostics_equal=True,
        native_and_cpu_reference_full_packet_bit_exact_claim=False,
        observed_issue='PC candidates miss the black general and exceed the black-pawn limit; native finish stage rejects consistently',
        original_fp32_geometric_candidate_is_playable=False,
        original_quantized_mac_has_cell_conflicts=True,
        explicit_int32_oracle_is_original_backend=False,
        gui_rejected=True, stale_or_fabricated_fen_submitted=False,
        automatic_move_after_rejection=False, engine_ready_nodes_zero=True,
        request_and_result_consumed=True, gui_idle_after_result=True,
        human_chess_page_retained=True, human_recognition_status_visible=True,
        physical_space_key_accepted=False, font_size_preference_accepted=False,
        audio_listening_accepted=False, positive_live_recognition_accepted=False,
        full_games_accepted=False, production_ready=False, m0_accepted=False,
        new_sd_write=False, flash_written=False, hardware_rebuilt=False,
        original_package_integrity_rechecked=True, adapter_integrity_rechecked=True,
        full_regression_reused_with_inputs_reverified=checked,
        full_regression_receipt_sha256=sha(regression_path),
        boot_receipt='../../picture-native-sd-20261020/boot-r03/result.json',
        boot_receipt_sha256=sha(boot_path),
        human_display_receipt='../../picture-native-sd-20261020/human-display-confirmation-20261020.json',
        human_display_receipt_sha256=sha(display_path),
        data_handling='Camera pixels, image identifiers, request/result packets, coordinates and FEN remain in build/ or board RAM; this archive contains only redacted engineering outcomes',
        caveats=['No user-confirmed per-piece FEN truth for this live capture; no accuracy rate inferred',
                 'The earlier 32-piece positive replay used a training-derived input, not this photograph',
                 'The unused optional result-witness upload failed and the witness was never executed'],
    )
    # Whitelist log lines: never copy the GUI STATUS line carrying its FEN.
    sanitized = [item for item in native_text.splitlines()
                 if item.startswith(('XQ_NATIVE_READY ', 'XQ_NATIVE_STAGE ', 'XQ_NATIVE_RECOGNITION '))]
    sanitized += reject_lines + ['NATIVE_GUI_IDLE_AFTER_RESULT']
    assert sanitized.count(line) == 1
    DEST.mkdir()
    log_path = DEST / 'engineering-redacted.log'
    log_path.write_text('\n'.join(sanitized) + '\n', encoding='utf-8')
    result['evidence_sha256'] = {log_path.name: sha(log_path)}
    (DEST / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], elapsed_seconds=result['elapsed_seconds'],
                          mac_jobs=result['actual_mac_jobs'], regression_inputs=checked), indent=2))


if __name__ == '__main__':
    main()
