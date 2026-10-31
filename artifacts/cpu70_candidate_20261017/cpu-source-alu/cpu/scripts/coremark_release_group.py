"""Run the fixed V3.1 CoreMark matrix on one immutable Verilator model."""

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


parser = argparse.ArgumentParser()
parser.add_argument("group_root", type=Path)
parser.add_argument("simulator", type=Path)
parser.add_argument("performance_source", type=Path)
parser.add_argument("validation_source", type=Path)
parser.add_argument("--max-cycles", type=int, default=800_000_000)
arguments = parser.parse_args()
project = Path(__file__).resolve().parent.parent
group = arguments.group_root.resolve()
simulator = arguments.simulator.resolve()
if not simulator.is_file() and simulator.with_suffix(".exe").is_file():
    simulator = simulator.with_suffix(".exe")
if not simulator.is_file() or arguments.max_cycles < 500_000_000:
    raise SystemExit("Missing simulator or an insufficient simulation cycle bound")
sources = {
    "performance": arguments.performance_source.resolve(),
    "validation": arguments.validation_source.resolve(),
}
firmware_names = (
    "coremark.elf", "coremark.bin", "ram.hex", "macros.txt",
    "manifest.json", "coremark_build_config.h",
)
manifests = {}
for mode, source in sources.items():
    subprocess.run([sys.executable, str(project / "scripts/verify_firmware.py"), str(source)], check=True)
    manifest = json.loads((source / "manifest.json").read_text())
    if (manifest["run_mode"], manifest["iterations"], manifest["cpu_hz"],
        manifest["optimization"], manifest["compiler_version"]) != (
            mode, 2600, 49_500_000, "-O2", "16.2.0"
        ):
        raise SystemExit("Wrong formal firmware configuration: " + mode)
    if manifest["coremark_sim"] or manifest["compressed_instructions"]:
        raise SystemExit("Formal firmware disabled timing or contains compressed instructions")
    if manifest.get("evidence_class") != "formal_candidate":
        raise SystemExit("Calibration firmware cannot enter a formal CoreMark group")
    manifests[mode] = manifest

cases = (("performance_1", "performance"),
         ("performance_2", "performance"),
         ("performance_3", "performance"),
         ("validation_1", "validation"))
if (group / "group.json").exists() or any((group / name).exists() for name, _ in cases):
    raise SystemExit("Refusing to overwrite a CoreMark release group")
group.mkdir(parents=True, exist_ok=True)
input_files = (
    project / "generated/sim/CoreTop.sv",
    project / "coremark_test_soc/rtl/axi_bram_uart.v",
    project / "coremark_test_soc/rtl/uart_tx_fifo.v",
    project / "coremark_test_soc/rtl/coremark_soc_top.v",
    project / "coremark_test_soc/sim/tb_coremark_soc.v",
    *sorted((project / "scripts/meminit").glob("*.hex")),
)
input_hashes = {str(path.relative_to(project)).replace("\\", "/"): sha256(path)
                for path in input_files}
model_hash = sha256(simulator)
record = {
    "schema_version": 1,
    "status": "RUNNING",
    "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "host_simulator": {"cxx_flags": "-Os", "sha256": model_hash,
                       "path": str(simulator)},
    "target": {"gcc_optimization": "-O2", "cpu_hz": 49_500_000,
               "iterations": 2600, "minimum_target_seconds": 10},
    "max_cycles_per_case": arguments.max_cycles,
    "rtl_and_meminit_sha256": input_hashes,
    "cases": {},
}
for name, mode in cases:
    directory = group / name
    directory.mkdir()
    for filename in firmware_names:
        shutil.copy2(sources[mode] / filename, directory / filename)
    shutil.copytree(project / "scripts/meminit", directory / "scripts/meminit")
    record["cases"][name] = {
        "mode": mode,
        "status": "STAGED",
        "firmware_sha256": {filename: sha256(directory / filename) for filename in firmware_names},
    }
write_json(group / "group.json", record)
lock = threading.Lock()


def run_case(name, mode):
    directory = group / name
    start = time.perf_counter()
    with (directory / "run.log").open("w") as log:
        process = subprocess.Popen(
            [str(simulator), "+max_cycles=" + str(arguments.max_cycles)],
            cwd=directory, stdout=log, stderr=subprocess.STDOUT,
        )
        with lock:
            record["cases"][name].update(status="RUNNING", pid=process.pid)
            write_json(group / "group.json", record)
            print(f"COREMARK_CASE_START name={name} pid={process.pid}", flush=True)
        exit_code = process.wait()
    runtime = {"simulation_wall_seconds": time.perf_counter() - start,
               "max_cycles": arguments.max_cycles, "exit_code": exit_code,
               "host_cxx_flags": "-Os", "simulator_sha256": model_hash}
    write_json(directory / "runtime.json", runtime)
    if exit_code == 0:
        with (directory / "validation.txt").open("w") as output:
            checked = subprocess.run(
                [sys.executable, str(project / "scripts/check_timed_coremark.py"), str(directory)],
                stdout=output, stderr=subprocess.STDOUT,
            )
        exit_code = checked.returncode
    result = json.loads((directory / "result.json").read_text()) if exit_code == 0 else None
    with lock:
        record["cases"][name].update(
            status="PASS" if result and result["status"] == "PASS" else "FAIL",
            exit_code=exit_code, runtime=runtime, result=result,
        )
        write_json(group / "group.json", record)
        print(f"COREMARK_CASE_END name={name} status={record['cases'][name]['status']}", flush=True)


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(run_case, name, mode) for name, mode in cases]
    for future in concurrent.futures.as_completed(futures):
        future.result()
if any(case["status"] != "PASS" for case in record["cases"].values()):
    record["status"] = "FAIL"
else:
    record["status"] = "PASS"
record["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
write_json(group / "group.json", record)
if record["status"] != "PASS":
    raise SystemExit("CoreMark release group failed; inspect per-case run and validation logs")
print("COREMARK_RELEASE_GROUP_PASS", flush=True)
