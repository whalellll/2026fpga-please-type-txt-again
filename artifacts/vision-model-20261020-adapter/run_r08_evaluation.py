"""Bounded exact PC evaluation, using historical input identities, no hardware."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=135)
    args = parser.parse_args()
    identity = json.loads((REPO / 'docs/validation/picture-p20-combined-20261020/fp32/inputs.json').read_text())['files']
    dataset = Path(identity['IMG00908/image']['path']).parents[1]
    board = Path(identity['IMG00908/board']['path']).parent
    args.out.mkdir(parents=True, exist_ok=False)
    # Separate per-platform characterization precedes all evaluation.
    with (args.out / 'probe.log').open('w') as log:
        subprocess.run([sys.executable, '-B', str(HERE / 'probe_mm_char.py'),
                        '--out', str(args.out / 'probe.json')], stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=180)
    print('R08_PLATFORM_PROBE_COMPLETE', flush=True)
    command = [sys.executable, '-B', str(HERE / 'evaluate_combined.py'),
               '--backend', 'quantized-mac', '--dataset', str(dataset),
               '--board-dir', str(board), '--label-policy', 'user-original-game3-20261020',
               '--out', str(args.out / 'exact'), '--limit', str(args.limit)]
    with (args.out / 'evaluation.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=7200)
    print('R08_EXACT_EVALUATION_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
