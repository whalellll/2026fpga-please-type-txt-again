"""Exercise the short-RTL evidence gate with real, freshly executed run inputs."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("performance", type=Path)
parser.add_argument("validation", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
checker = Path(__file__).with_name("check_timed_coremark.py")
results = []

for mode, original in (("performance", args.performance), ("validation", args.validation)):
    manifest = json.loads((original / "manifest.json").read_text())
    assert manifest["run_mode"] == mode
    assert manifest["iterations"] == 10 and manifest["evidence_class"] == "calibration"
    for scenario in ("valid", "wrong_final_crc", "missing_done", "wrong_clock", "changed_firmware", "short_as_formal"):
        with tempfile.TemporaryDirectory(prefix="cpu_short_gate_") as temporary:
            fixture = Path(temporary)
            for name in set(manifest["files"]) | {"manifest.json", "macros.txt", "run.log"}:
                assert Path(name).name == name
                shutil.copy2(original / name, fixture / name)
            log = (fixture / "run.log").read_text()
            if scenario == "wrong_final_crc":
                log, count = re.subn(r"(\[0\]crcfinal\s*:\s*0x)[0-9a-fA-F]+", r"\g<1>0000", log)
                assert count == 1
            elif scenario == "missing_done":
                assert "COREMARK_DONE" in log
                log = log.replace("COREMARK_DONE", "REMOVED_DONE_MARKER")
            elif scenario == "wrong_clock":
                log, count = re.subn(r"(TB_COREMARK_SOC_START cpu_hz=)\d+", r"\g<1>59400000", log)
                assert count == 1
            elif scenario == "changed_firmware":
                binary = fixture / "coremark.bin"
                data = bytearray(binary.read_bytes())
                data[0] ^= 1
                binary.write_bytes(data)
            elif scenario == "short_as_formal":
                promoted = dict(manifest, evidence_class="formal_candidate")
                (fixture / "manifest.json").write_text(json.dumps(promoted))
            (fixture / "run.log").write_text(log)
            command = [sys.executable, str(checker), str(fixture)]
            if scenario != "short_as_formal":
                command.append("--calibration")
            run = subprocess.run(command, capture_output=True, text=True, timeout=30)
            expected_pass = scenario == "valid"
            assert (run.returncode == 0) == expected_pass, (mode, scenario, run.stdout, run.stderr)
            if expected_pass:
                checked = json.loads((fixture / "result.json").read_text())
                assert checked["status"] == "CALIBRATION_ONLY"
                assert checked["at_least_10_seconds"] is False
            else:
                assert not (fixture / "result.json").exists()
            results.append({"mode": mode, "scenario": scenario, "expected": "accept calibration only" if expected_pass else "reject", "exit_code": run.returncode, "diagnostic": run.stderr.strip() if not expected_pass else "CALIBRATION_ONLY"})

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({"status": "PASS", "checks": len(results), "results": results}, indent=2) + "\n")
print("COREMARK_CALIBRATION_GATE_FIXTURES_PASS", len(results))
