#!/usr/bin/env python3
import argparse
import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path


POSITIONS = [
    ("startpos", "position startpos"),
    (
        "middlegame-white",
        "position fen r1ba1a3/4kn3/2n1b4/pNp1p1p1p/4c4/6P2/"
        "P1P2R2P/1CcC5/9/2BAKAB2 w",
    ),
    (
        "middlegame-black",
        "position fen 1cbak4/9/n2a5/2p1p3p/5cp2/2n2N3/"
        "6PCP/3AB4/2C6/3A1K1N1 w",
    ),
]


class Engine:
    def __init__(self, name, command, model, timeout):
        self.name = name
        self.timeout = timeout
        self.lines = queue.Queue()
        self.transcript = []
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()

        self.send("uci")
        self.read_until(lambda line: line == "uciok", "uciok")
        self.send(f"setoption name EvalFile value {model}")
        self.send("setoption name Threads value 1")
        self.send("setoption name Hash value 8")
        self.send("setoption name UCI_ShowWDL value true")
        self.send("isready")
        ready = self.read_until(lambda line: line == "readyok", "readyok")
        if any("unknown command" in line.lower() for line in ready):
            raise RuntimeError(f"{name}: UCI setup reported an unknown command")

    def _read_stdout(self):
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            self.lines.put(raw.rstrip("\r\n"))
        self.lines.put(None)

    def send(self, command):
        if self.process.poll() is not None:
            raise RuntimeError(f"{self.name}: process exited with {self.process.returncode}")
        assert self.process.stdin is not None
        self.transcript.append(f"> {command}")
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def read_until(self, predicate, description):
        deadline = time.monotonic() + self.timeout
        result = []
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise RuntimeError(f"{self.name}: timed out waiting for {description}") from exc
            if line is None:
                raise RuntimeError(
                    f"{self.name}: exited with {self.process.poll()} while waiting for {description}"
                )
            self.transcript.append(line)
            result.append(line)
            if predicate(line):
                return result
        raise RuntimeError(f"{self.name}: timed out waiting for {description}")

    def evaluate_and_search(self, position, nodes):
        self.send("ucinewgame")
        self.send(position)
        self.send("eval")
        self.send("isready")
        evaluation = self.read_until(lambda line: line == "readyok", "eval/readyok")
        if not any("evaluation" in line.lower() for line in evaluation):
            raise RuntimeError(f"{self.name}: eval produced no evaluation output")

        self.send(f"go nodes {nodes}")
        search = self.read_until(lambda line: line.startswith("bestmove "), "bestmove")
        best_line = search[-1]
        match = re.match(r"bestmove\s+(\S+)(?:\s+ponder\s+(\S+))?", best_line)
        if not match:
            raise RuntimeError(f"{self.name}: malformed bestmove line: {best_line}")
        if not any(line.startswith("info ") for line in search):
            raise RuntimeError(f"{self.name}: search produced no UCI info lines")
        wdl = None
        for line in search:
            wdl_match = re.search(r"\swdl\s+(\d+)\s+(\d+)\s+(\d+)(?:\s|$)", line)
            if wdl_match:
                wdl = [int(wdl_match.group(index)) for index in range(1, 4)]
        if wdl is None or sum(wdl) != 1000:
            raise RuntimeError(f"{self.name}: search produced no valid WDL")
        return {
            "bestmove": match.group(1),
            "ponder": match.group(2),
            "wdl": wdl,
        }

    def close(self):
        if self.process.poll() is None:
            self.send("quit")
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.process.returncode != 0:
            raise RuntimeError(f"{self.name}: exited with {self.process.returncode}")


def run_engine(name, command, model, nodes, timeout):
    engine = Engine(name, command, model, timeout)
    results = {}
    try:
        for case_name, position in POSITIONS:
            results[case_name] = engine.evaluate_and_search(position, nodes)
    finally:
        engine.close()
    return results, engine.transcript


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", required=True)
    parser.add_argument("--rv32", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reference-model")
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--nodes", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    native, native_log = run_engine(
        "native", [args.native], args.model, args.nodes, args.timeout
    )
    rv32, rv32_log = run_engine(
        "rv32", ["qemu-riscv32", args.rv32], args.model, args.nodes, args.timeout
    )

    reference = None
    reference_log = None
    if args.reference_model:
        reference, reference_log = run_engine(
            "native-reference",
            [args.native],
            args.reference_model,
            args.nodes,
            args.timeout,
        )

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "pikafish-native-uci.log").write_text("\n".join(native_log) + "\n")
    (log_dir / "pikafish-rv32-uci.log").write_text("\n".join(rv32_log) + "\n")
    if reference_log is not None:
        (log_dir / "pikafish-reference-model-uci.log").write_text(
            "\n".join(reference_log) + "\n"
        )

    with Path(args.model).open("rb") as model_file:
        is_pff1 = model_file.read(4) == b"PFF1"
    if is_pff1:
        for name, transcript in (("native", native_log), ("rv32", rv32_log)):
            if not any("PIKAFISH_PFF1_READY" in line for line in transcript):
                raise RuntimeError(f"{name}: PFF1 model did not report READY")

    if reference is not None and reference != native:
        raise RuntimeError(
            "compressed/PFF1 model mismatch:\n"
            + json.dumps({"compressed": reference, "pff1": native}, indent=2)
        )

    if native != rv32:
        raise RuntimeError(
            "native/RV32 bestmove mismatch:\n"
            + json.dumps({"native": native, "rv32": rv32}, indent=2)
        )

    print(
        "PIKAFISH_RV32_UCI_PASS "
        + json.dumps(
            {
                "nodes": args.nodes,
                "positions": rv32,
                "reference_model_match": reference is not None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
