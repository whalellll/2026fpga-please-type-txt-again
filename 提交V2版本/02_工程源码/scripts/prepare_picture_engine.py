"""Linux handoff helper: prepare the same pinned/patched Pikafish as the
existing Windows builder. No training and no changes to release inputs.
Network operations are bounded; model SHA mismatch stops without fallback.
"""
import argparse
import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path

COMMIT = "56be6f65c21c6a3c7f9b884a976fc85d31d03287"
MODEL_SHA = "3cd15292bf8c979884262f57fc723959fc0dea43b4d8d544f88db5ceb2479e24"
RELEASE_PFF_SHA = "de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260"
PATCHES = ("rv32", "attacks", "stagea", "flat", "view", "embedded", "embedded-memory",
           "startup-memory", "zero-state-history", "stageb-position-accept", "stageb")
PORTS = ("portable_u128.h", "pikafish_attack_tables.h", "pikafish_attack_tables.cpp",
         "pikafish_mac_runtime.h", "pikafish_mac_runtime.cpp", "pikafish_mmio_shadow.h",
         "pikafish_mac_backend_policy.h",
         "pikafish_stagea_accel.h", "pikafish_stagea_accel.cpp", "pikafish_stageb_accel.h",
         "pikafish_stageb_accel.cpp", "pikafish_stageb_position_accept.cpp",
         "pikafish_pff1_view.h", "pikafish_embedded.h", "pikafish_embedded.cpp")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def run(*args, cwd, data=None):
    subprocess.run(args, cwd=cwd, input=data, check=True, timeout=180)


def prepare(repo, out, model, release_pff1=False):
    out = out.resolve()
    if (repo / "build").resolve() not in out.parents or out.exists():
        raise ValueError("choose a fresh output directory strictly under build/; existing trees are retained")
    provenance = {"commit": COMMIT, "compressed_model_verified": False}
    if release_pff1:
        if model is not None: raise ValueError("select a raw model or the release PFF1 path")
        pff = repo / "linux/boot/pikafish.pff"
        if pff.stat().st_size != 68122688 or sha(pff) != RELEASE_PFF_SHA:
            raise ValueError("frozen V2.1 release PFF1 identity mismatch")
        provenance.update(model_source="release-pff1", pff_sha256=RELEASE_PFF_SHA)
    elif model is None:
        model = out.parent / "pikafish.nnue"
        model.parent.mkdir(parents=True, exist_ok=True)
        if not model.exists():
            part = model.with_suffix(".nnue.part")
            owned_part = False
            try:
                url = "https://github.com/official-pikafish/Networks/releases/download/master-net/pikafish.nnue"
                with part.open("xb") as target:
                    owned_part = True
                    with urllib.request.urlopen(url, timeout=300) as response:
                        shutil.copyfileobj(response, target, 1024 * 1024)
                if sha(part) != MODEL_SHA:
                    raise ValueError("official current model differs from frozen model; obtain exact SHA, do not substitute")
                part.rename(model)
            finally:
                if owned_part and part.exists(): part.unlink()
    if not release_pff1:
        if sha(model) != MODEL_SHA: raise ValueError("frozen official NNUE SHA mismatch")
        provenance.update(model_source="compressed-nnue", compressed_model_verified=True, model_sha256=MODEL_SHA)
    out.mkdir(parents=True)
    run("git", "init", "-q", cwd=out)
    run("git", "config", "core.autocrlf", "false", cwd=out)
    run("git", "remote", "add", "origin", "https://github.com/official-pikafish/Pikafish.git", cwd=out)
    run("git", "fetch", "--depth", "1", "origin", COMMIT, cwd=out)
    run("git", "checkout", "--detach", "FETCH_HEAD", cwd=out)
    actual = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=out, text=True, timeout=10).strip()
    if actual != COMMIT: raise ValueError("Pikafish commit mismatch")
    port = repo / "linux/pikafish"
    for name in PORTS: shutil.copyfile(port / name, out / "src" / name)
    for source in ("linux/mac_accel/pango_mac_uapi.h", "sw/mac_accel/mac_accel_kernel.h",
                   "sw/pikafish_mlp_stage_b/pf_mlp_mac_pack.h", "sw/pikafish_mlp_stage_b/pf_mlp_stage_b.h",
                   "sw/pikafish_mlp_stage_b/pf_stageb_position_golden.h"):
        shutil.copyfile(repo / source, out / "src" / Path(source).name)
    shutil.copyfile(port / "pikafish_flat_nnue.inc", out / "src/nnue/pikafish_flat_nnue.inc")
    if not release_pff1: shutil.copyfile(model, out / "src/pikafish.nnue")
    for patch in PATCHES:
        content = (port / ("pikafish-" + patch + ".patch")).read_bytes().replace(b"\r\n", b"\n")
        run("git", "apply", "--ignore-space-change", "--ignore-whitespace", "-", cwd=out, data=content)
    import json
    (out / "picture_source_provenance.json").write_text(json.dumps(provenance,indent=2)+"\n",encoding="utf-8")
    print("PICTURE_ENGINE_SOURCE_READY commit=%s model_source=%s path=%s" % (COMMIT,provenance["model_source"],out))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    models=parser.add_mutually_exclusive_group()
    models.add_argument("--model", type=Path)
    models.add_argument("--release-pff1", action="store_true", help="build the existing direct-view runtime against the exact V2.1 PFF1; no compressed model is embedded or fabricated")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        prepare(root, args.output or root / "build/picture-engine/source", args.model, args.release_pff1)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, "PICTURE_ENGINE_PREPARE_FAIL %s\n" % exc)
