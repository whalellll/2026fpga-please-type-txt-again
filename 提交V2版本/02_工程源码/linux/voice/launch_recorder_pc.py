#!/usr/bin/env python3
"""Start the PC recording window using an editable adjacent JSON config."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    here = Path(__file__).resolve().parent
    config = json.loads((here / 'recorder_config.json').read_text(encoding='utf-8-sig'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['train', 'validation', 'test'], default=config['split'])
    parser.add_argument('--target-per-token', type=int, default=config['target_per_token'])
    parser.add_argument('--batch', action='store_true', help='Long recording followed by human-reviewed word clips')
    parser.add_argument('--seconds', type=int, choices=[10, 15, 20, 30, 45, 60], default=15)
    args = parser.parse_args()
    # Check the dependencies before hiding the launcher's console.
    import serial
    import tkinter
    output = Path(config['output_root']).expanduser()
    if not output.is_absolute():
        output = here.parents[1] / output
    script = 'record_batch_pc.py' if args.batch else 'record_dataset_pc.py'
    extra = ['--seconds', str(args.seconds)] if args.batch else ['--mode', 'all', '--target-per-token', str(args.target_per_token)]
    if args.batch:
        import numpy
    subprocess.Popen([sys.executable, str(here / script),
                      '--port', config['port'], '--speaker', config['speaker'],
                      '--split', args.split, *extra,
                      '--output', str(output)], cwd=str(here.parents[1]))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'Voice recorder launch failed', 0x10)
        raise
