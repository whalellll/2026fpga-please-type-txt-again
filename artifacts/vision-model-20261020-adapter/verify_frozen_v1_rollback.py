"""Smoke-test both frozen-v1 PC rollbacks on one authorized game-3 replay."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main():
    output = REPO / 'build/picture-merge-20261023/frozen-v1-rollback-r01'
    output.mkdir(exist_ok=False)
    receipt = REPO / 'docs/validation/picture-merge-20261023/frozen-v1-rollback.json'
    assert not receipt.exists()
    inputs = json.loads((REPO/'build/picture-r11-20261022/adapter-inputs/game3-inputs.json').read_text())
    item = inputs['frames'][0]
    assert inputs['game'] == 3 and 152 <= item['index'] <= 234
    source = REPO / item['path']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == item['sha256']
    image = cv2.imread(str(source))
    assert image.shape == (720, 1280, 3)
    raw = (((image[:, :, 2].astype(np.uint16) >> 3) << 11)
           | ((image[:, :, 1].astype(np.uint16) >> 2) << 5)
           | (image[:, :, 0].astype(np.uint16) >> 3)).astype('<u2').tobytes()
    frame = REPO / 'build/picture-merge-20261023/replay-r02/frame.rgb565'
    assert frame.read_bytes() == raw, 'verify replay provenance, never substitute game2'
    config_path = HERE / 'working_combination.json'
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    assert config['default_profile'] == 'working-r14' and config['default_backend'] == 'fp32'
    expected = config['profiles']['frozen640-v1']['models']
    results = {}
    environment = dict(os.environ, OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    for backend in ('fp32', 'quantized-mac'):
        target = output / (backend + '.json')
        command = [sys.executable, '-B', str(HERE/'recognize_working.py'),
                   '--profile', 'frozen640-v1', '--backend', backend,
                   '--input', str(frame), '--width', '1280', '--height', '720',
                   '--output', str(target)]
        process = subprocess.run(command, cwd=REPO, env=environment, capture_output=True, timeout=240)
        (output/(backend+'.log')).write_bytes(process.stdout+process.stderr)
        assert process.returncode == 0, f'{backend} failed; inspect private build log'
        result = json.loads(target.read_text())
        assert result['working_profile'] == 'frozen640-v1'
        assert result['selected_classifier'] == 'v1' and result['selected_detector'] == 'frozen640'
        assert result['production_ready'] is False and result['full_integer_pipeline'] is False
        assert {name: value['sha256'] for name, value in result['models'].items()} == {
            name: value['sha256'] for name, value in expected.items()}
        if backend == 'quantized-mac':
            assert result['integer_oracle'] == 'r08-exact-int64'
        else:
            assert 'integer_oracle' not in result
        results[backend] = dict(cli_exit_code=0, model_identities_verified=True,
                                status=result['status'], strict_usable=result['can_use_as_candidate'])
    assert config_path.read_bytes() == config_bytes
    from pc_exact import characterize
    probe = characterize()
    assert probe['golden'] == 'r08-exact-int64' and not probe['int_mm_is_golden']
    report = dict(status='PASS', scope='one authorized game3 RGB565 replay; rollback engineering smoke only',
                  results=results, platform_probe=probe, original_classifier_sha256=expected['classifier']['sha256'],
                  working_combination_sha256=hashlib.sha256(config_bytes).hexdigest(),
                  default='working-r14 FP32', default_unchanged=True, strict_guards_unchanged=True,
                  accuracy_acceptance=False, production_ready=False, hardware_used=False,
                  game2_images_opened=0, game2_inference_runs=0, real_frames_archived_to_git=False)
    with receipt.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print('FROZEN_V1_FP32_AND_EXACT_ROLLBACK_PASS')


if __name__ == '__main__':
    main()
