"""Frozen recognition CLI with the r08 exact PC oracle installed first.

Arguments and create-only output behavior are owned by the original CLI.
This wrapper never modifies the frozen entry point or model assets.
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent / 'vision-model-20261020/golden'

if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(GOLDEN / 'software'), str(GOLDEN / 'quantization')]
    from pc_exact import install
    install()
    runpy.run_path(str(GOLDEN / 'recognize.py'), run_name='__main__')
