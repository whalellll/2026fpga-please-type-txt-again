"""Read-only receiver for the delivered three-model profile; no inference/imports."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

PROFILE = "training-handoff-current-three-model-v1"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe(root, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or any(
            p in ("", ".", "..") for p in name.split("/")) or PurePosixPath(name).is_absolute():
        raise ValueError("unsafe package path: " + str(name))
    path = root / name
    for p in (path,) + tuple(path.parents):
        if p == root:
            break
        info = p.lstat()
        if p.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("package link/reparse point")
    if root not in path.resolve().parents or not path.is_file():
        raise ValueError("missing package file: " + name)
    return path


def registry(root, files, extra_aliases=None):
    if not isinstance(files, dict) or not files:
        raise ValueError("nonempty hash registry required")
    folded = set()
    for name, expected in files.items():
        if name == "manifest.json" or name.casefold() in folded:
            raise ValueError("manifest self-reference/case collision")
        folded.add(name.casefold())
        if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected):
            raise ValueError("invalid SHA256: " + name)
        if sha(safe(root, name)) != expected:
            raise ValueError("file identity mismatch: " + name)
    for alias,target in (extra_aliases or {}).items():
        if target not in files or sha(safe(root,alias)) != files[target]:
            raise ValueError("explicit source alias mismatch: " + alias)
        folded.add(alias.casefold())
    actual = set()
    for p in root.rglob("*"):
        info = p.lstat()
        if p.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("package link/reparse point")
        if p.is_file() and p != root / "manifest.json":
            actual.add(p.relative_to(root).as_posix().casefold())
    if actual != folded:
        raise ValueError("unlisted or missing package files")


def read(root, name):
    return json.loads(safe(root, name).read_text(encoding="utf-8"))


def verify_adapter(adapter, r2):
    adapter = Path(adapter).resolve(strict=True)
    m = read(adapter, "adapter_manifest.json")
    if m.get("schema_version") != 1 or m.get("piece_fit_enabled") is not False:
        raise ValueError("adapter schema or premature piece_fit enable")
    sources = {}
    for key, item in m["sources"].items():
        directory = (adapter / item["directory"]).resolve(strict=True)
        if sha(safe(directory, "manifest.json")) != item["manifest_sha256"]:
            raise ValueError("adapter source manifest mismatch")
        if key == "r2" and directory != r2:
            raise ValueError("adapter R2 source mismatch")
        source = read(directory, "manifest.json")
        registry(directory, source["files"] if key == "r2" else source["files_sha256"],
                 None if key == "r2" else {"dataset_corrections.json":"report/dataset_corrections.json"})
        sources[key] = directory
    entries = m["files"]
    for name, item in entries.items():
        path = safe(adapter, name)
        source = safe(sources[item["source_package"]], item["source_path"])
        if path.stat().st_size != item["bytes"] or sha(path) != item["sha256"] or sha(source) != item["sha256"]:
            raise ValueError("adapter copy provenance mismatch: " + name)
    corrections = read(adapter, "dataset_corrections.json")
    truth = read(adapter, "fen_gt.json")
    if len(corrections["corrections"]) != 81 or len(truth) != 1042:
        raise ValueError("adapter requires R1 81 corrections and 1042 FEN frames")
    for required in ("geometry_fallback/piece_fit.py", "geometry_fallback/c_ref/geometry_ref.c",
                     "geometry_fallback/c_ref/geometry_ref.h", "geometry_fallback/test_vectors/vectors.json"):
        if required not in entries:
            raise ValueError("adapter fallback payload missing: " + required)
    return dict(files_verified=len(entries), corrections=81, fen_records=1042, piece_fit_enabled=False,
                r1_verified_extra_alias="dataset_corrections.json == report/dataset_corrections.json")


def verify_current(directory, m, purpose="m0", adapter=None):
    if m.get("format_profile") != PROFILE or m.get("scheme") != "board-detect-v2":
        raise ValueError("unknown three-model profile/scheme")
    if m.get("implementation") != "board192-roi640-rgb32-refined":
        raise ValueError("unknown three-model implementation")
    files = m.get("files")
    registry(directory, files)
    for required in ("training_manifest.json", "requirements.txt", "golden/recognize.py",
                     "geometry/geometry_reference.c", "geometry/board_geometry.py",
                     "golden/quantization/candidate_v1/integer_graph.json"):
        if required not in files:
            raise ValueError("missing required payload: " + required)
    models = m.get("models", {})
    if set(models) != {"detector", "board", "classifier"}:
        raise ValueError("exactly three model sections required")
    combined = read(directory, "golden/quantization/candidate_v1/integer_graph.json")
    if combined.get("layer_count") != 80 or len(combined.get("layers", [])) != 80:
        raise ValueError("80-layer integer graph required")
    combined_layers = {layer["layer_id"]:layer for layer in combined["layers"]}
    dumps = read(directory, "golden/quantization/candidate_v1/golden_dump_manifest.json")
    if not isinstance(dumps,list) or len(dumps)!=80 or len({r["path"] for r in dumps})!=80:
        raise ValueError("80 distinct golden layer dumps required")
    for record in dumps:
        name="golden/quantization/candidate_v1/"+record["path"]
        if not record["path"].startswith("golden_layer_dumps/") or files.get(name)!=record["sha256"]:
            raise ValueError("golden dump identity mismatch")
    all_ids = set()
    for name, size, count in (("detector", 640, 60), ("board", 192, 12), ("classifier", 32, 8)):
        model = models[name]
        for part in ("checkpoint", "onnx"):
            record = model[part]
            if files.get(record["path"]) != record["sha256"]:
                raise ValueError("model identity mismatch: " + name)
        if model["onnx"].get("fixed_input") != [1, 3, size, size]:
            raise ValueError("model input mismatch: " + name)
        if combined["model_SHA256"].get(name) != model["checkpoint"]["sha256"]:
            raise ValueError("integer/source model mismatch: " + name)
        graph = read(directory, model["int8_dir"] + "/integer_graph.json")
        if graph.get("layer_count") != count or len(graph.get("layers", [])) != count:
            raise ValueError("component integer layer count: " + name)
        for layer in graph["layers"]:
            ident = layer["layer_id"]
            if ident in all_ids or not ident.startswith(name + "__"):
                raise ValueError("duplicate/incorrect integer layer identity")
            all_ids.add(ident)
            if layer["activation"] not in ("SiLU", "ReLU", "Identity"):
                raise ValueError("unsupported activation: " + ident)
            for key, expected in (("input_dtype", "int8"), ("weight_dtype", "int8"),
                                  ("accumulator_dtype", "int32"), ("preactivation_dtype", "int16"),
                                  ("output_dtype", "int16" if layer["activation"] == "Identity" else "int8")):
                if layer.get(key) != expected:
                    raise ValueError("integer dtype mismatch: " + ident)
            if type(layer["max_INT32_absolute_bound"]) is not int or not 0 <= layer["max_INT32_absolute_bound"] <= 2147483647:
                raise ValueError("integer accumulator bound: " + ident)
            if model["int8_dir"] + "/" + ident + ".npz" not in files:
                raise ValueError("integer layer data missing: " + ident)
            if layer["activation"] in ("SiLU", "ReLU") and model["int8_dir"] + "/" + ident + ".lut" not in files:
                raise ValueError("activation LUT missing: " + ident)
            if layer!=combined_layers.get(ident):
                raise ValueError("combined/component integer metadata mismatch: " + ident)
    if {v["layer_id"] for v in combined["layers"]} != all_ids:
        raise ValueError("combined/component layer inventory differs")
    for alias, target in m.get("runtime_aliases", {}).items():
        if alias not in files or target not in files or files[alias] != files[target]:
            raise ValueError("runtime alias identity mismatch")
    acceptance = m.get("acceptance", {})
    if m.get("production_ready") is not False or acceptance.get("full_integer_pipeline") is not False:
        raise ValueError("unsupported production/full-integer claim")
    training = read(directory, "training_manifest.json")
    geometry = m["metrics"]["board_geometry"]
    coarse = geometry["coarse_board_model"]
    return dict(format_profile=PROFILE, scheme=m["scheme"], files_verified=len(files), models=3,
                integer_layers=80, purpose=purpose, manifest_sha256=sha(directory / "manifest.json"),
                reported_corner_metrics_pass=coarse["P50_px"] <= 8 and coarse["P95_px"] <= 15,
                independent_test=training.get("independent_test") is True,
                production_ready=False, full_integer_pipeline=False, golden_smoke_pass=False,
                m0_eligible=False, m0_accepted=False, main_chain_switch_allowed=False,
                adapter=verify_adapter(adapter, directory) if adapter else None,
                next="Run both golden backends on the requested 135 frames; report provenance and strict uncertainty separately.")
