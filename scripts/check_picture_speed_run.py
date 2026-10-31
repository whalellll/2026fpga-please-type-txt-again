"""Check one saved PN08 run against the strict <300s correct-display target.

Read-only and offline: independent observations supply physical input, framing,
correctness and actual runtime identity. Output never includes transcript text,
paths, hashes, positions or identifiers. This is not a BoardRelease verifier.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / 'docs/validation/picture-e42-integration-20261026/pn08-offline.json'
LIMIT_MS = 300000
MAX_LOG_BYTES = 8 * 1024 * 1024
RUNTIME_HASHES = ('target_bitstream_sha256', 'kernel_sha256', 'worker_sha256', 'gui_sha256')
OBSERVATIONS = ('physical_space', 'complete_board_in_frame', 'recognition_correct',
                'external_hdmi_correct', 'runtime_identity_verified')


def _fields(line):
    result = {}
    for token in line.split()[1:]:
        key, separator, value = token.partition('=')
        if not separator or not value or key in result:
            raise ValueError('malformed_record')
        result[key] = value
    return result


def _integer(fields, name, maximum):
    value = fields.get(name, '')
    if not re.fullmatch(r'[0-9]{1,8}', value) or int(value) > maximum:
        raise ValueError('malformed_record')
    return int(value)


def evaluate(transcript, observations, expected):
    """Return only allowlisted counters and reason codes; never echo inputs."""
    failed, missing = [], []
    elapsed = None
    captures, presents = [], []
    if len(transcript) > MAX_LOG_BYTES:
        failed.append('transcript_too_large')
    else:
        for index, line in enumerate(transcript.decode('utf-8-sig', errors='replace').splitlines()):
            line = line.strip()
            marker = line.split(maxsplit=1)[0] if line else ''
            if marker not in ('XINYI_PHOTO_PHASE', 'XINYI_PHOTO_PRESENT'):
                continue
            try:
                fields = _fields(line)
                if marker == 'XINYI_PHOTO_PRESENT':
                    if set(fields) != {'elapsed_ms', 'time_valid', 'gui_buffer_presented',
                                       'physical_visibility_pending'}:
                        raise ValueError('malformed_record')
                    ms = _integer(fields, 'elapsed_ms', 7200000)
                    valid = _integer(fields, 'time_valid', 1)
                    submitted = _integer(fields, 'gui_buffer_presented', 1)
                    _integer(fields, 'physical_visibility_pending', 1)
                    presents.append((index, ms))
                    if valid != 1:
                        failed.append('invalid_present_clock')
                    if submitted != 1:
                        failed.append('buffer_not_submitted')
                elif fields.get('phase') == 'capture_and_geometry':
                    captures.append((index, _integer(fields, 'elapsed_ms', 7200000)))
                    if _integer(fields, 'okay', 1) != 1:
                        failed.append('capture_not_usable')
                elif fields.get('phase') not in ('recommendation', 'audio'):
                    raise ValueError('malformed_record')
            except ValueError:
                failed.append('malformed_photo_record')
    if not captures:
        missing.append('capture_completion')
    if not presents:
        missing.append('after_present_timing')
    if len(captures) > 1 or len(presents) > 1:
        failed.append('multiple_runs_require_separate_transcripts')
    if len(captures) == len(presents) == 1:
        elapsed = presents[0][1]
        if captures[0][0] >= presents[0][0] or captures[0][1] > elapsed:
            failed.append('capture_present_order_or_clock_mismatch')
        if elapsed >= LIMIT_MS:
            failed.append('display_not_under_300s')

    if not isinstance(observations, dict):
        observations = {}
        failed.append('invalid_observations')
    if observations.get('schema') != 'picture-speed-observation-v1':
        missing.append('observation_schema_v1')
    digest = observations.get('transcript_sha256')
    if digest is None:
        missing.append('transcript_binding')
    elif digest != hashlib.sha256(transcript).hexdigest():
        failed.append('transcript_binding_mismatch')
    for name in OBSERVATIONS:
        value = observations.get(name)
        if value is None:
            missing.append(name)
        elif value is not True:
            failed.append(name + '_not_confirmed')
    runtime = observations.get('actual_runtime')
    if not isinstance(runtime, dict):
        runtime = {}
    for name in RUNTIME_HASHES:
        value = runtime.get(name)
        expected_value = expected.get(name)
        if not isinstance(expected_value, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_value):
            failed.append('invalid_expected_' + name)
        elif value is None:
            missing.append('actual_' + name)
        elif value != expected_value:
            failed.append('runtime_mismatch_' + name)
    supported = not failed and not missing
    return dict(status='SUPPORTED_BY_PROVIDED_EVIDENCE' if supported else
                'REJECTED' if failed else 'INCOMPLETE',
                provided_evidence_supports_target=supported, target_exclusive_ms=LIMIT_MS,
                after_present_elapsed_ms=elapsed,
                failures=sorted(set(failed)), missing=sorted(set(missing)),
                endpoint='after_GUI_buffer_submit_with_independent_HDMI_observation',
                tool_accessed_hardware=False, production_ready=False, formal_release=False)


def _load_json(path, maximum):
    if path.stat().st_size > maximum:
        raise ValueError('input_too_large')
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    value = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError('expected_json_object')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True, help='Saved transcript of exactly one capture')
    parser.add_argument('--observations', type=Path, required=True, help='Independent, transcript-bound observations JSON')
    parser.add_argument('--output', type=Path, help='New redacted JSON under build/; existing files are preserved')
    args = parser.parse_args()
    try:
        if args.log.stat().st_size > MAX_LOG_BYTES:
            raise ValueError('input_too_large')
        result = evaluate(args.log.read_bytes(), _load_json(args.observations, 65536),
                          _load_json(IDENTITY, 65536))
        data = json.dumps(result, indent=2) + '\n'
        if args.output:
            from picture_workspace import workspace_path
            output = workspace_path(args.output)
            build = (ROOT / 'build').resolve()
            private = ROOT / 'build/picture-e42-20261025'
            private_allowed = (private.is_junction() or private.is_symlink()) and output.is_relative_to(private.resolve())
            if not output.is_relative_to(build) and not private_allowed:
                raise ValueError('output_outside_build')
            with output.open('x', encoding='utf-8') as stream:
                stream.write(data)
    except (OSError, ValueError, TypeError, RecursionError):
        # Exceptions may contain private paths or input text. Never print them.
        print(json.dumps(dict(status='INPUT_ERROR', provided_evidence_supports_target=False,
                              tool_accessed_hardware=False, production_ready=False, formal_release=False)))
        return 2
    print(data, end='')
    return 0 if result['provided_evidence_supports_target'] else 1 if result['failures'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
