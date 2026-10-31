#!/usr/bin/env python3
"""Measure real-board GUI search latency through its Linux control FIFO."""

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import serial


ROOT = Path(__file__).resolve().parents[1]
FIFO = "/run/xiangqi-pikafish.in"
STATUS = re.compile(r"XQ LINUX INJECT STATUS side=(\w+) engine=(\w+)[^\r\n]*")
MOVE = re.compile(
    r"XQ LINUX INJECT MOVE_PASS red=(\w{4}) black=(\w{4}) "
    r"nodes=(\d+) search_ms=(\d+) total_ms=(\d+)"
)
FAIL = re.compile(r"XQ LINUX INJECT MOVE_FAIL[^\r\n]*")
PROFILE_LINE = re.compile(r"XQ (SEARCH|STAGEA) PROFILE ([^\r\n]*)")
PROFILE_FIELD = re.compile(r"([a-z_]+)=(\d+)")


class BoardConsole:
    def __init__(self, port, baud, log_path):
        self.port = serial.Serial()
        self.port.port = port
        self.port.baudrate = baud
        self.port.timeout = 0.2
        self.port.write_timeout = 5
        self.port.dtr = False
        self.port.rts = False
        self.log = log_path.open("w", encoding="utf-8", newline="")
        self.port.open()

    def close(self):
        self.port.close()
        self.log.close()

    def send(self, command):
        # Pace characters like the existing serial acceptance scripts.
        for byte in (command + "\n").encode("ascii"):
            self.port.write(bytes((byte,)))
            time.sleep(0.1)
        self.port.flush()

    def until(self, patterns, timeout):
        if not isinstance(patterns, (list, tuple)):
            patterns = [patterns]
        end = time.monotonic() + timeout
        data = ""
        while time.monotonic() < end:
            chunk = self.port.read(4096).decode("utf-8", "replace")
            if not chunk:
                continue
            self.log.write(chunk)
            self.log.flush()
            data += chunk
            for pattern in patterns:
                match = pattern.search(data)
                if match:
                    return match, data
            if len(data) > 250000:
                data = data[-125000:]
        raise TimeoutError(f"Timed out after {timeout}s; see {self.log.name}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fifo_command(console, value):
    console.send(f"printf '{value}\\n' > {FIFO}")


def parse_profiles(transcript):
    profiles = {}
    for name, fields in PROFILE_LINE.findall(transcript):
        profiles[name.lower()] = {
            key: int(value) for key, value in PROFILE_FIELD.findall(fields)
        }
    return profiles


def measure(console, move, trials, ready_timeout, move_timeout, skip_board_hash,
            stageb_ready_verified, gui_path, require_profiles):
    console.send("")
    console.until(re.compile(r"(?m)^/[^\r\n]* # "), 20)

    gui_hash = digest(gui_path)
    pack_hash = digest(ROOT / "artifacts/pikafish-stageb-mac.bin")
    if not skip_board_hash:
        console.send(
            "sha256sum /usr/bin/xiangqi-pikafish-gui "
            "/opt/pikafish/stageb-mac.bin"
        )
        _, hashes = console.until(re.compile(pack_hash, re.I), 180)
        if gui_hash not in hashes.lower():
            raise RuntimeError("Board GUI/model hash differs from current artifacts")

    console.send(
        f"test -p {FIFO} && "
        "kill -0 $(cat /run/xiangqi-pikafish.pid) 2>/dev/null "
        "&& echo XQ_GUI_PROBE_OK"
    )
    console.until(re.compile(r"(?m)^XQ_GUI_PROBE_OK\r*$"), 30)

    deadline = time.monotonic() + ready_timeout
    while True:
        fifo_command(console, "XQ_STATUS")
        match, _ = console.until(STATUS, 15)
        if match.group(2) == "ready":
            break
        if match.group(2) == "failed" or time.monotonic() >= deadline:
            raise RuntimeError(f"GUI engine status: {match.group(2)}")
        time.sleep(5)

    samples = []
    for index in range(trials):
        fifo_command(console, "XQ_NEWGAME")
        console.until(re.compile(r"XQ LINUX INJECT NEW_GAME_PASS"), 20)
        fifo_command(console, "XQ_STATUS")
        status, _ = console.until(STATUS, 15)
        if status.group(1) != "red" or status.group(2) != "ready":
            raise RuntimeError(f"Trial {index + 1}: unexpected GUI status")

        started = time.monotonic()
        fifo_command(console, f"XQ_MOVE {move}")
        match, transcript = console.until([MOVE, FAIL], move_timeout)
        host_ms = round((time.monotonic() - started) * 1000)
        if match.re is FAIL:
            raise RuntimeError(f"Trial {index + 1}: {match.group(0)}")
        if match.group(1) != move:
            raise RuntimeError(f"Trial {index + 1}: red move mismatch")
        active_marker = bool(re.search(
            r"PIKAFISH_STAGEB_ACCEL_ACTIVE[^\r\n]*mode=1", transcript
        ))
        if not active_marker and not stageb_ready_verified:
            raise RuntimeError(f"Trial {index + 1}: hardware Stage B mode=1 not proven")
        if re.search(r"CPU_FALLBACK|RUNTIME_FUSED|mismatch|SEARCH FAILED", transcript, re.I):
            raise RuntimeError(f"Trial {index + 1}: fallback or engine failure")
        sample = {
            "trial": index + 1,
            "red": move,
            "black": match.group(2),
            "nodes": int(match.group(3)),
            "search_ms": int(match.group(4)),
            "total_ms": int(match.group(5)),
            "host_ms": host_ms,
            "stageb_active_marker_seen": active_marker,
        }
        profiles = parse_profiles(transcript)
        if require_profiles and not {"search", "stagea"}.issubset(profiles):
            raise RuntimeError(f"Trial {index + 1}: phase profile markers missing")
        if profiles:
            sample["profiles"] = profiles
        samples.append(sample)
        print(json.dumps(sample, ensure_ascii=False), flush=True)
    return gui_hash, pack_hash, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM17")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--move", default="h2e2")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--ready-timeout", type=int, default=900)
    parser.add_argument("--move-timeout", type=int, default=600)
    parser.add_argument("--skip-board-hash", action="store_true",
                        help="Use when GUI and model were verified separately before a live run")
    parser.add_argument("--stageb-ready-verified", action="store_true",
                        help="Use when Stage B mode=1 active was captured in an earlier board log")
    parser.add_argument("--sbit", type=Path, default=ROOT / "artifacts/soc_v2_top.sbit",
                        help="Bitstream programmed to CRAM for this board run")
    parser.add_argument("--gui", type=Path, default=ROOT / "artifacts/xiangqi-pikafish-gui",
                        help="Exact GUI executable running on the board")
    parser.add_argument("--require-profiles", action="store_true",
                        help="Require search and Stage A phase counters on every move")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/gui_latency_retry")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-i][0-9][a-i][0-9]", args.move):
        parser.error("--move must be a four-character ICCS move")
    if args.trials < 1:
        parser.error("--trials must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = args.output_dir / f"gui_injection_{stamp}.log"
    result_path = args.output_dir / f"gui_injection_{stamp}.json"
    console = BoardConsole(args.port, args.baud, log_path)
    try:
        gui_hash, pack_hash, samples = measure(
            console, args.move, args.trials, args.ready_timeout, args.move_timeout,
            args.skip_board_hash, args.stageb_ready_verified, args.gui,
            args.require_profiles,
        )
    finally:
        console.close()
    result = {
        "port": args.port,
        "baud": args.baud,
        "timestamp_utc": stamp,
        "gui_sha256": gui_hash,
        "stageb_pack_sha256": pack_hash,
        "host_sbit_sha256": digest(args.sbit),
        "board_hash_checked_in_run": not args.skip_board_hash,
        "stageb_ready_verified_before_run": args.stageb_ready_verified,
        "samples": samples,
        "mean_search_ms": statistics.mean(s["search_ms"] for s in samples),
        "mean_total_ms": statistics.mean(s["total_ms"] for s in samples),
        "median_search_ms": statistics.median(s["search_ms"] for s in samples),
        "median_total_ms": statistics.median(s["total_ms"] for s in samples),
    }
    if all("profiles" in sample for sample in samples):
        phase_fields = (
            ("search", "transform_us"),
            ("search", "propagate_us"),
            ("search", "stageb_host_us"),
            ("stagea", "session_us"),
            ("stagea", "pack_us"),
            ("stagea", "submit_us"),
            ("stagea", "merge_us"),
        )
        result["mean_profile_us"] = {
            f"{section}.{key}": statistics.mean(
                sample["profiles"][section][key] for sample in samples)
            for section, key in phase_fields
            if all(section in sample["profiles"]
                   and key in sample["profiles"][section]
                   for sample in samples)
        }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"GUI_INJECTION_LATENCY_PASS trials={len(samples)} json={result_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, TimeoutError, serial.SerialException) as exc:
        print(f"GUI_INJECTION_LATENCY_FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
