#!/usr/bin/env python3
"""Compatibility CLI for the current PowerShell ADS resource-gate fixture.

The PowerShell runner extracts and executes the actual build_fpga.ps1 function.
It does not launch PDS or treat the supplied report as current release evidence.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    powershell = shutil.which("powershell")
    if powershell is None:
        raise RuntimeError("Windows PowerShell is required for the current FPGA resource gate")
    runner = Path(__file__).with_suffix(".ps1")
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(runner),
         "-Report", str(args.report.resolve()), "-Output", str(args.output.resolve())],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    print(result.stdout.strip())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print("PDS_RESOURCE_GATE_FIXTURES_FAIL " + str(error), file=sys.stderr)
        sys.exit(1)
