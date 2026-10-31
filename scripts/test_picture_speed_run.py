"""Synthetic evidence checks only; no captured image or board run is used."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_picture_speed_run import IDENTITY, OBSERVATIONS, ROOT, RUNTIME_HASHES, evaluate

CAPTURE = 'XINYI_PHOTO_PHASE phase=capture_and_geometry okay=1 elapsed_ms=299000\n'
PRESENT = ('XINYI_PHOTO_PRESENT elapsed_ms=299999 time_valid=1 '
           'gui_buffer_presented=1 physical_visibility_pending=1\n')


class SpeedRunTest(unittest.TestCase):
    def setUp(self):
        self.expected = {name: str(index) * 64 for index, name in enumerate(RUNTIME_HASHES)}
        self.log = (CAPTURE + PRESENT).encode()
        self.observations = dict(schema='picture-speed-observation-v1',
                                 actual_runtime=copy.deepcopy(self.expected),
                                 **{name: True for name in OBSERVATIONS})

    def check(self, *, log=None, changes=None, reason=None, missing=None):
        data = self.log if log is None else log
        observations = copy.deepcopy(self.observations)
        observations['transcript_sha256'] = hashlib.sha256(data).hexdigest()
        observations.update(changes or {})
        result = evaluate(data, observations, self.expected)
        if reason:
            self.assertEqual(result['status'], 'REJECTED')
            self.assertIn(reason, result['failures'])
        elif missing:
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertIn(missing, result['missing'])
        else:
            self.assertTrue(result['provided_evidence_supports_target'])
        self.assertFalse(result['production_ready'])
        self.assertFalse(result['formal_release'])
        self.assertFalse(result['tool_accessed_hardware'])
        return result

    def test_correct_physical_run_below_target(self):
        self.assertEqual(self.check()['after_present_elapsed_ms'], 299999)

    def test_exact_boundary_and_slower_fail(self):
        for ms in ('300000', '484258'):
            with self.subTest(ms=ms):
                self.check(log=(CAPTURE + PRESENT.replace('299999', ms)).encode(),
                           reason='display_not_under_300s')

    def test_old_callback_and_cancel_without_completion_are_incomplete(self):
        for log in (CAPTURE.encode(), b'XINYI_STOPPED_RESOURCES_RELEASED\n'):
            with self.subTest(log=log):
                self.check(log=log, missing='after_present_timing')

    def test_invalid_clock_cannot_use_zero_elapsed_as_a_pass(self):
        self.check(log=(CAPTURE.replace('299000', '0') +
                        PRESENT.replace('299999', '0').replace('time_valid=1', 'time_valid=0')).encode(),
                   reason='invalid_present_clock')

    def test_independent_observations_are_required_and_strict_booleans(self):
        for name in OBSERVATIONS:
            for value in (False, 'true', 1):
                with self.subTest(name=name, value=value):
                    self.check(changes={name: value}, reason=name + '_not_confirmed')
            with self.subTest(name=name, value=None):
                self.check(changes={name: None}, missing=name)

    def test_runtime_must_match_current_pn08_payloads(self):
        for name in RUNTIME_HASHES:
            runtime = copy.deepcopy(self.expected)
            runtime[name] = 'f' * 64
            with self.subTest(name=name):
                self.check(changes={'actual_runtime': runtime}, reason='runtime_mismatch_' + name)
        self.check(changes={'actual_runtime': None}, missing='actual_kernel_sha256')

    def test_observations_cannot_be_reused_for_another_transcript(self):
        self.check(changes={'transcript_sha256': 'f' * 64}, reason='transcript_binding_mismatch')

    def test_ambiguous_and_inconsistent_runs_fail(self):
        for log, reason in ((self.log * 2, 'multiple_runs_require_separate_transcripts'),
                            ((PRESENT + CAPTURE).encode(), 'capture_present_order_or_clock_mismatch'),
                            ((CAPTURE.replace('299000', '300000') + PRESENT).encode(),
                             'capture_present_order_or_clock_mismatch'),
                            (PRESENT.encode(), None)):
            with self.subTest(reason=reason):
                self.check(log=log, reason=reason, missing=None if reason else 'capture_completion')

    def test_bad_records_fail_closed(self):
        records = [(CAPTURE + PRESENT.replace('time_valid=1', 'time_valid=1 time_valid=0'),
                    'malformed_photo_record'),
                   (CAPTURE + PRESENT.replace('299999', '-1'), 'malformed_photo_record'),
                   (CAPTURE + PRESENT.replace('299999', 'NaN'), 'malformed_photo_record'),
                   (CAPTURE + PRESENT.replace('299999', '7200001'), 'malformed_photo_record'),
                   (CAPTURE + PRESENT.replace('gui_buffer_presented=1', 'gui_buffer_presented=0'),
                    'buffer_not_submitted'),
                   (CAPTURE.replace('okay=1', 'okay=0') + PRESENT, 'capture_not_usable')]
        for record, reason in records:
            with self.subTest(record=record):
                self.check(log=record.encode(), reason=reason)

    def test_recommendation_and_audio_do_not_change_display_latency(self):
        result = self.check(log=self.log + b'XINYI_PHOTO_PHASE phase=recommendation okay=1 elapsed_ms=330000\n'
                                           b'XINYI_PHOTO_PHASE phase=audio okay=0\n')
        self.assertEqual(result['after_present_elapsed_ms'], 299999)

    def test_output_never_echoes_private_input(self):
        sentinel = 'PRIVATE_SENTINEL_DO_NOT_EXPORT'
        result = self.check(log=(sentinel + '\n').encode() + self.log,
                            changes={'notes': sentinel})
        output = json.dumps(result)
        self.assertNotIn(sentinel, output)
        self.assertNotIn('sha256', output.replace('actual_', '').replace('runtime_mismatch_', ''))

    def test_cli_exit_codes_and_input_errors(self):
        script = Path(__file__).with_name('check_picture_speed_run.py')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log, observation = folder / 'run.log', folder / 'observations.json'
            log.write_bytes(self.log)
            supplied = dict(self.observations, actual_runtime={name: json.loads(IDENTITY.read_text())[name]
                                                              for name in RUNTIME_HASHES},
                            transcript_sha256=hashlib.sha256(self.log).hexdigest())
            for value, code, status in ((True, 0, 'SUPPORTED_BY_PROVIDED_EVIDENCE'),
                                        (False, 1, 'REJECTED'), (None, 2, 'INCOMPLETE')):
                supplied['recognition_correct'] = value
                observation.write_text(json.dumps(supplied))
                result = subprocess.run([sys.executable, '-B', str(script), '--log', str(log),
                                         '--observations', str(observation)], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], status)
            for bad in ('{"private":BROKEN_SECRET}', '[1]', '[' * 1100 + '0' + ']' * 1100):
                observation.write_text(bad)
                result = subprocess.run([sys.executable, '-B', str(script), '--log', str(log),
                                         '--observations', str(observation)], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b'BROKEN_SECRET', result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'INPUT_ERROR')

    def test_duplicate_observation_keys_cannot_override_a_failure(self):
        script = Path(__file__).with_name('check_picture_speed_run.py')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log, observation = folder / 'run.log', folder / 'observations.json'
            log.write_bytes(self.log)
            supplied = dict(self.observations, recognition_correct=False,
                            actual_runtime={name: json.loads(IDENTITY.read_text())[name]
                                            for name in RUNTIME_HASHES},
                            transcript_sha256=hashlib.sha256(self.log).hexdigest())
            observation.write_text(json.dumps(supplied)[:-1] + ',"recognition_correct":true}')
            result = subprocess.run([sys.executable, '-B', str(script), '--log', str(log),
                                     '--observations', str(observation)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'INPUT_ERROR')

    def test_output_is_confined_to_build_and_never_overwrites(self):
        script = Path(__file__).with_name('check_picture_speed_run.py')
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
            folder = Path(directory)
            log, observation, output = folder / 'run.log', folder / 'observations.json', folder / 'result.json'
            log.write_bytes(self.log)
            observation.write_text('{}')
            argv = [sys.executable, '-B', str(script), '--log', str(log),
                    '--observations', str(observation), '--output']
            result = subprocess.run([*argv, str(output)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)  # Incomplete evidence is still written for review.
            self.assertEqual(json.loads(output.read_text())['status'], 'INCOMPLETE')
            original = output.read_bytes()
            result = subprocess.run([*argv, str(output)], capture_output=True, timeout=5)
            self.assertEqual(json.loads(result.stdout)['status'], 'INPUT_ERROR')
            self.assertEqual(output.read_bytes(), original)
            # Resolving .. must not allow an output to escape build/.
            outside = folder / '..' / '..' / (folder.name + '-outside.json')
            result = subprocess.run([*argv, str(outside)], capture_output=True, timeout=5)
            self.assertEqual(json.loads(result.stdout)['status'], 'INPUT_ERROR')
            self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()
