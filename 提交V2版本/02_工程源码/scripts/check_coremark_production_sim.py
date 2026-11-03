"""Validate one unaccelerated production-console CoreMark RTL simulation."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_one(pattern, text, label):
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        raise SystemExit(f"Expected one {label}; found {len(matches)}")
    return matches[0]


parser = argparse.ArgumentParser()
parser.add_argument("--log", required=True, type=Path)
parser.add_argument("--mode", required=True, choices=("performance", "validation"))
parser.add_argument("--kind", required=True, choices=("pilot", "long"))
parser.add_argument("--rom", required=True, type=Path)
parser.add_argument("--binary", required=True, type=Path)
parser.add_argument("--build-manifest", required=True, type=Path)
parser.add_argument("--cpu-source", required=True, type=Path)
parser.add_argument("--cpu-rtl", required=True, type=Path)
parser.add_argument("--cpu-hz", required=True, type=int)
parser.add_argument("--expected-iterations", required=True, type=int)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()

text = args.log.read_text(encoding="utf-8", errors="replace").replace("\r", "")
manifest = json.loads(args.build_manifest.read_text(encoding="utf-8"))
source = json.loads(args.cpu_source.read_text(encoding="utf-8"))
hz = args.cpu_hz
root = args.cpu_source.resolve().parents[2]
clock = json.loads((root / "config/clocks.json").read_text(encoding="utf-8"))
soc_version = (root / "VERSION").read_text(encoding="utf-8").strip()
timebase_hz = clock["timebase_hz"]
sys_hz = clock["sys_hz"]
if hz <= 0 or args.expected_iterations < 0 or hz != clock["cpu_hz"]:
    raise SystemExit("Invalid expected clock or iteration count")
clock_quantization = require_one(
    r"^SIM_CLOCK_QUANTIZATION cpu_half_fs=(\d+) sys_half_fs=(\d+)$",
    text,
    "simulated CPU/SYS clock quantization",
)
cpu_half_fs, sys_half_fs = map(int, clock_quantization)
expected_cpu_half_fs = (500_000_000_000_000 + hz // 2) // hz
expected_sys_half_fs = (500_000_000_000_000 + sys_hz // 2) // sys_hz
if (cpu_half_fs, sys_half_fs) != (expected_cpu_half_fs, expected_sys_half_fs):
    raise SystemExit("Simulation waveform quantization disagrees with CPU/SYS clock configuration")
if source["isa"] != "rv32ima_zicsr_zifencei" or source["compressed_instructions"] is not False:
    raise SystemExit("CPU source is not the frozen RV32IMA/no-C profile")
if sha(args.cpu_rtl) != source["sha256"]:
    raise SystemExit("Integrated CPU differs from its source manifest")
if manifest["binary_sha256"] != sha(args.binary):
    raise SystemExit("Firmware binary differs from its build manifest")
manifest_iterations = manifest.get("coremark_iterations")
if type(manifest_iterations) is not int or manifest_iterations != args.expected_iterations:
    raise SystemExit("Firmware build manifest does not explicitly bind the selected CoreMark iteration policy")
if args.kind == "long" and (
    not isinstance(manifest.get("coremark_contract"), dict)
    or not isinstance(manifest["coremark_contract"].get("preprocessed_macros"), dict)
    or manifest["coremark_contract"]["preprocessed_macros"].get("ITERATIONS") != str(args.expected_iterations)
):
    raise SystemExit("Production CoreMark iteration policy differs from preprocessed GCC macros")
words = args.rom.read_text(encoding="ascii").splitlines()
if len(words) != 32768 or any(not re.fullmatch(r"[0-9a-fA-F]{8}", word) for word in words):
    raise SystemExit("Boot ROM is not the complete 128 KiB word image")
rom_bytes = b"".join(int(word, 16).to_bytes(4, "little") for word in words)
binary_bytes = args.binary.read_bytes()
if rom_bytes[: len(binary_bytes)] != binary_bytes or any(rom_bytes[len(binary_bytes) :]):
    raise SystemExit("Boot ROM contents disagree with firmware binary")
if (manifest["compiler_target"], manifest["compiler_version"], manifest["march"], manifest["abi"]) != (
    "riscv32-unknown-elf", "16.2.0", source["isa"], "ilp32"
):
    raise SystemExit("Firmware ISA or compiler differs from the release profile")
if manifest["elf_metadata"]["ElfClass"] != "ELF32" or "no RVC" not in manifest["elf_metadata"]["Flags"]:
    raise SystemExit("Firmware ELF is not proven ELF32 without RVC")
if "RV32IMA mnemonic/width whitelist" not in manifest["code_validation"]["Result"]:
    raise SystemExit("Firmware has no whole-code RV32IMA check")
cpu_display = ".".join(source["cpu_version"].split(".")[:2])
if (f"CoreMark v1.0: CPU V{cpu_display} RV32IMA" not in text or
        f"SoC V{soc_version} bootloader" not in text):
    raise SystemExit("Production console banner or CoreMark command missing")
if int(require_one(r"(?m)^SYS_HZ=(\d+)$", text, "SYS clock")) != sys_hz:
    raise SystemExit("SYS clock register disagrees with configuration")
if int(require_one(r"(?m)^CPU_HZ=(\d+)$", text, "firmware clock")) != hz:
    raise SystemExit("Firmware clock disagrees with candidate frequency")
if int(require_one(r"(?m)^TIMEBASE_HZ=(\d+)$", text, "timer clock")) != timebase_hz:
    raise SystemExit("Timer clock register disagrees with configuration")
if require_one(r"^COREMARK_MODE=(\w+)$", text, "seed mode") != args.mode:
    raise SystemExit("Wrong CoreMark seed mode")
if int(require_one(r"^CoreMark Size\s*:\s*(\d+)$", text, "CoreMark size")) != 666:
    raise SystemExit("Wrong CoreMark workload size")
if require_one(r"^Compiler version\s*:\s*(.+)$", text, "compiler") != "riscv32-unknown-elf-gcc 16.2.0":
    raise SystemExit("Wrong compiler reported by firmware")
if require_one(r"^Compiler flags\s*:\s*(.+)$", text, "compiler flags") != (
    "-O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32"
):
    raise SystemExit("Wrong CoreMark compiler flags")
expected = ("e9f5", "e714", "1fd7", "8e3a") if args.mode == "performance" else (
    "18f2", "e3c1", "0747", "8d84"
)
labels = ("seedcrc", "[0]crclist", "[0]crcmatrix", "[0]crcstate")
crc = {}
for label, value in zip(labels, expected):
    actual = require_one(r"^" + re.escape(label) + r"\s*:\s*0x([0-9a-f]{4})$", text, label)
    if actual != value:
        raise SystemExit(f"Wrong {label}: {actual}")
    crc[label] = actual
crc["[0]crcfinal"] = require_one(r"^\[0\]crcfinal\s*:\s*0x([0-9a-f]{4})$", text, "final CRC")
iterations = int(require_one(r"^Iterations\s*:\s*(\d+)$", text, "iterations"))
if args.expected_iterations and iterations != args.expected_iterations:
    raise SystemExit("Reported iterations disagree with the released firmware recipe")
ticks = int(require_one(r"^PORT_TICKS64\s*:\s*(\d+)$", text, "64-bit ticks"))
official_ticks = int(require_one(r"^Total ticks\s*:\s*(\d+)$", text, "official ticks"))
if ticks <= 0 or official_ticks != ticks % (1 << 32):
    raise SystemExit("Official and 64-bit timer fields disagree")
seconds = float(require_one(r"^Total time \(secs\):\s*([0-9.]+)$", text, "seconds"))
if abs(seconds - ticks / timebase_hz) > 0.000002:
    raise SystemExit("Reported duration disagrees with CLINT ticks")
footer = require_one(
    r"^CPU_PRODUCTION_COREMARK_DONE mode=(\w+) pilot=(\d+) cycles=(\d+) "
    r"real_timer_cycles=(\d+) cpu_hz=(\d+) timer_stimulus_scale=(\d+) "
    r"observed_cpu_cycles_timer_release_to_prompt=(\d+)$",
    text,
    "unaccelerated production simulation footer",
)
foot_mode, pilot, total_cycles, real_cycles, foot_hz, scale, observed_cpu_cycles = footer
if (foot_mode, int(pilot), int(foot_hz), int(scale)) != (
    args.mode, int(args.kind == "pilot"), hz, 1
):
    raise SystemExit("Simulation mode or timer interpretation disagrees")
if int(real_cycles) <= ticks or int(total_cycles) < int(real_cycles):
    raise SystemExit("Timer-check coverage does not include the measured interval")
if (int(observed_cpu_cycles) <= 0 or
        abs(int(observed_cpu_cycles) * cpu_half_fs - int(real_cycles) * sys_half_fs)
        > 6 * cpu_half_fs):
    raise SystemExit("Observed CPU console-window cycles disagree with real CPU/SYS clocks")
if "COREMARK_DONE" not in text or "%Error" in text or "FATAL" in text:
    raise SystemExit("Simulation or CoreMark did not finish cleanly")
if args.kind == "pilot":
    final_expected = "fcaf" if args.mode == "performance" else "c64e"
    if iterations != 10 or ticks >= timebase_hz * 10 or crc["[0]crcfinal"] != final_expected:
        raise SystemExit("Unexpected fixed-ten pilot result")
    if "ERROR! Must execute for at least 10 secs for a valid result!" not in text or "COREMARK_FAIL" not in text:
        raise SystemExit("Production port did not reject the short pilot")
    if "COREMARK_PASS" in text or "Correct operation validated." in text:
        raise SystemExit("Pilot was incorrectly accepted as an official score")
else:
    if iterations < 1 or ticks < timebase_hz * 10 or seconds < 10:
        raise SystemExit("Timed CoreMark interval is shorter than ten target seconds")
    if "Correct operation validated." not in text or "COREMARK_PASS" not in text:
        raise SystemExit("Official CoreMark validation did not pass")
    if "ERROR!" in text or "Errors detected" in text or "COREMARK_FAIL" in text:
        raise SystemExit("CoreMark reported an error")
result = {
    "status": "PILOT_PASS_NOT_A_SCORE" if args.kind == "pilot" else "RTL_TIMED_PASS_NOT_BOARD",
    "kind": args.kind,
    "seed_mode": args.mode,
    "iterations": iterations,
    "iteration_policy": "production_automatic_calibration" if args.expected_iterations == 0 else "fixed_iterations",
    "build_manifest_fixed_iterations": manifest_iterations,
    "ticks": ticks,
    "cpu_hz": hz,
    "sys_hz": sys_hz,
    "timebase_hz": timebase_hz,
    "sim_clock_quantization": {
        "cpu_half_fs": cpu_half_fs,
        "sys_half_fs": sys_half_fs,
        "cpu_waveform_hz": 500_000_000_000_000 / cpu_half_fs,
        "sys_waveform_hz": 500_000_000_000_000 / sys_half_fs,
    },
    "timer_seconds": ticks / timebase_hz,
    "iterations_per_second": iterations * timebase_hz / ticks,
    "coremark_per_mhz": iterations * timebase_hz * 1_000_000 / (ticks * hz),
    "crc": crc,
    "simulator_total_cycles": int(total_cycles),
    "real_clint_checked_cycles": int(real_cycles),
    "observed_cpu_cycles_timer_release_to_prompt": int(observed_cpu_cycles),
    "timer_stimulus_scale_during_command": 1,
    "boot_only_acceleration": True,
    "cpu_rtl_sha256": sha(args.cpu_rtl),
    "firmware_binary_sha256": sha(args.binary),
    "rom_sha256": sha(args.rom),
    "log_sha256": sha(args.log),
    "scope": "Production-source bootloader and UART console in RTL simulation; no real-board frequency or peripheral acceptance",
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
