"""Run the existing first-layer SoC bench with isolated trained candidate vectors."""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--distro", default="chiplab_sim")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    vectors = args.vectors.resolve()
    relative = vectors.relative_to(root).as_posix()
    if "build" not in vectors.relative_to(root).parts:
        raise ValueError("candidate vectors must be isolated under build")
    manifest = json.loads((vectors / "manifest.json").read_text())
    if manifest["traffic"] != dict(input_bytes=1024, weight_bytes=3456, output_bytes=1024, tap_count=2304):
        raise ValueError("this existing testbench requires the 16x16 first-layer tile")
    for name in ("input.hex", "weights.hex", "expected.hex", "bias.vh"):
        if not (vectors / name).is_file():
            raise ValueError(f"candidate vector missing: {name}")
    source = root / "sim/tb_soc_mac_conv_trained_tile.sv"
    original = source.read_text()
    text = original.replace("sim/vectors/trained_conv_tile", relative)
    text = text.replace("32'h8ff15d34", "32'h" + manifest["model_sha256"][:8])
    text = text.replace("32'h885fe98e", "32'h" + manifest["model_sha256"][8:16])
    bench = vectors / "candidate_testbench.sv"
    bench.write_text(text, encoding="utf-8", newline="\n")
    sources = ["rtl/mac_accel/mac_accel_dma_kernel.v", "rtl/mac_accel/mac_accel_axi_master32.v",
               "rtl/mac_accel/xiangqi_sparse_eval.v", "rtl/mac_accel/mac_accel_ddr_kernel_top.v"]
    sources += [p.relative_to(root).as_posix() for p in sorted((root / "rtl/mac_accel").glob("mac_conv_*.v"))]
    sources += ["rtl/mac_accel/mac_weight_double_buffer.v", "rtl/mac_accel/MacAccelCore.v",
                "sim/gtp_apm_e2_perf_sim.v", "sim/axi_shared_ram.sv", relative + "/candidate_testbench.sv"]
    executable = relative + "/candidate_testbench.vvp"
    if os.name == "nt":
        root_posix = "/mnt/" + root.drive[0].lower() + root.as_posix()[2:]
    else:
        root_posix = root.as_posix()
    script = vectors / "run_simulation.sh"
    script.write_text("#!/usr/bin/env bash\nset -euo pipefail\ncd " + shlex.quote(root_posix) + "\n" +
                      "iverilog -g2012 -s tb_soc_mac_conv_trained_tile -o " + shlex.quote(executable) + " " +
                      " ".join(shlex.quote(p) for p in sources) + "\n" +
                      "vvp " + shlex.quote(executable) + "\n", encoding="utf-8", newline="\n")
    evidence = {"model_sha256": manifest["model_sha256"], "tile_manifest": manifest,
                "testbench_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "simulation_sources": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources},
                "board_acceptance": False}
    if os.name == "nt":
        command = ["wsl", "-d", args.distro, "--", "bash", root_posix + "/" + relative + "/run_simulation.sh"]
    else:
        command = ["bash", str(script)]
    result = subprocess.run(command, cwd=root)
    evidence["native_exit"] = result.returncode
    (vectors / "simulation_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
