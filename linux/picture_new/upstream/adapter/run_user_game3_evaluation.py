"""Fresh two-backend inference under the user's original game-3 label ruling."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
           MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
with (a.out/'pip-freeze.txt').open('x') as log:
    subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=log, check=True, env=env, timeout=60)
for backend in ('fp32', 'quantized-mac'):
    baseline = json.loads((REPO/'docs/validation/picture-p20-combined-20261020'/backend/'inputs.json').read_text())['files']
    dataset = Path(baseline['IMG00908/image']['path']).parent.parent
    board = Path(baseline['IMG00908/board']['path']).parent
    command = [sys.executable, '-B', str(HERE/'evaluate_combined.py'), '--backend', backend,
               '--dataset', str(dataset), '--board-dir', str(board), '--out', str(a.out/backend),
               '--label-policy', 'user-original-game3-20261020']
    print('USER_LABEL_REPLAY_START', backend, flush=True)
    with (a.out/(backend+'.log')).open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, env=env, timeout=1800)
    report = json.loads((a.out/backend/'metrics_summary.json').read_text())
    print('USER_LABEL_REPLAY_DONE', backend, json.dumps(report['whole_board_exact']),
          json.dumps(report['end_to_end']), flush=True)
    subprocess.run([sys.executable,'-B',str(HERE/'rescore_retained_missing.py'),'--source',str(a.out/backend)],
                   check=True,env=env,timeout=120)
print('USER_LABEL_REPLAY_BOTH_COMPLETE', flush=True)
