"""Bounded UART identity-pad regression; no FPGA tool or board access."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icarus-bin", type=Path, default=Path("D:/LJL/WORK/iverilog/bin"))
    parser.add_argument("--vendor-models", type=Path, default=Path(
        "D:/LJL/WORK/pango/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation"))
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    sources = [root / name for name in (
        "rtl/soc/uart_tx_fifo.v", "sim/tb_uart_tx_fifo_hold_pad.sv",
        "rtl/soc/axi_boot_periph.v", "sim/tb_axi_boot_periph.v", "pds/bootrom.hex",
        "sim/uart_tx_fifo_unpadded_reference.v")]
    models = [args.vendor_models / name for name in (
        "GTP_LUT6D.v", "GTP_LUT5.v", "GTP_MUX2LUT6.v",
        "INT_LUTMUX4_UDP.v", "INT_LUTMUX2_UDP.v")]
    inputs = sources + models + [Path(__file__).resolve()]
    hashes = {str(path): sha(path) for path in inputs}
    result = dict(schema=1, status="INCOMPLETE", scope="RTL and vendor primitive functional simulation only; not ADS retention, routed timing or board acceptance",
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  total_timeout_seconds=180, per_command_timeout_seconds=30,
                  input_sha256=hashes, commands=[])

    def run(name, argv, marker=None):
        remaining = 180 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("UART regression total deadline expired")
        timeout = min(30, remaining)
        begin = time.monotonic()
        with (output / (name + ".stdout.txt")).open("wb") as stdout, (output / (name + ".stderr.txt")).open("wb") as stderr:
            proc = subprocess.run([str(a) for a in argv], cwd=root, stdout=stdout, stderr=stderr, timeout=timeout)
        text = (output / (name + ".stdout.txt")).read_text("utf-8", errors="replace")
        errors = (output / (name + ".stderr.txt")).read_text("utf-8", errors="replace")
        result["commands"].append(dict(name=name, argv=[str(a) for a in argv], exit_code=proc.returncode,
            elapsed_seconds=time.monotonic()-begin, stdout_sha256=sha(output/(name+".stdout.txt")),
            stderr_sha256=sha(output/(name+".stderr.txt"))))
        if proc.returncode or re.search(r"(?m)^\s*(?:ERROR:|FATAL:)", text + "\n" + errors):
            raise RuntimeError("UART regression command failed: " + name)
        if marker and marker not in text:
            raise RuntimeError("UART regression marker missing: " + name)
        if marker:
            print(text.strip())

    try:
        for synthesis in (False, True):
            mode = "vendor_synthesis" if synthesis else "rtl"
            extra = ["-DSYNTHESIS", *models] if synthesis else []
            for width in (4, 3, 1):
                name = f"{mode}_ptr{width}"
                image = output / (name + ".vvp")
                run(name + "_compile", [args.icarus_bin / "iverilog.exe", "-g2012", "-s", "tb_uart_tx_fifo_hold_pad",
                    "-P", f"tb_uart_tx_fifo_hold_pad.PTR_W={width}", "-o", image, *extra, sources[0], sources[1], sources[5]])
                run(name + "_run", [args.icarus_bin / "vvp.exe", image], f"UART_TX_FIFO_HOLD_PAD_PASS ptr_w={width}")
            name = mode + "_axi_boot_periph"
            image = output / (name + ".vvp")
            run(name + "_compile", [args.icarus_bin / "iverilog.exe", "-g2012", "-s", "tb_axi_boot_periph",
                "-o", image, *extra, sources[0], sources[2], sources[3]])
            run(name + "_run", [args.icarus_bin / "vvp.exe", image], "PASS tb_axi_boot_periph")
        if any(sha(Path(path)) != expected for path, expected in hashes.items()):
            raise RuntimeError("UART regression input changed during execution")
        result["status"] = "PASS"
    except Exception as error:
        result["status"] = "FAIL"
        result["error"] = str(error)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        result["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("UART_TX_FIFO_PAD_REGRESSION_PASS cases=8 no_pds=true no_board=true")


if __name__ == "__main__":
    main()
