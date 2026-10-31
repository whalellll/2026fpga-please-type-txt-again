"""Verify all r09 files, retaining the raw delivery exclusively under build/."""
import argparse
import json
from pathlib import Path
from receive_r08 import receive

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = receive(args.archive, args.out, delivery='training_side_20261021_r09')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))
