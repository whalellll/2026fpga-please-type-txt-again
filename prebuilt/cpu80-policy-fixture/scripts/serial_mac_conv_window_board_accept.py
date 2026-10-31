"""Capture the isolated window harness result from its 115200-baud UART."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import serial


EXPECTED = (
    "WINDOW_BOARD_PASS C0=0010/0004 C1=0060/0012 "
    "C2=0060/0012 C3=01E7/006C "
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--sbit", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    deadline = time.monotonic() + args.seconds
    lines: list[str] = []
    with serial.Serial(args.port, 115200, timeout=0.5) as uart:
        uart.reset_input_buffer()
        while time.monotonic() < deadline:
            line = uart.readline().decode("ascii", errors="replace").strip()
            if line:
                lines.append(line)
                if line.startswith("WINDOW_BOARD_"):
                    break
    record = {
        "port": args.port,
        "baud": 115200,
        "lines": lines,
        "bitstream_sha256": sha256(args.sbit),
        "source_sha256": sha256(args.source),
        "expected_sha256": sha256(args.expected),
        "expected_line": EXPECTED.strip(),
        "pass": EXPECTED.strip() in lines,
    }
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    if not record["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
