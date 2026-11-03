"""Read-only M0 manifest gate. Does not train, change or execute package files."""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate manifest key: " + key)
        value[key] = item
    return value


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("missing/invalid integer: " + name)
    return value


def number(value, name, minimum=0, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or value < minimum or
            (maximum is not None and value > maximum)):
        raise ValueError("missing/invalid number: " + name)
    return value


def object_field(parent, name):
    value = parent.get(name)
    if not isinstance(value, dict):
        raise ValueError("missing/invalid object: " + name)
    return value


def reject_link(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("package links/reparse points are forbidden")


def verify_board_sections(manifest, files, delivery_round):
    """Receiver field names are documented in docs/PICTURE_NEW_MODEL_CONTRACT.md.

    Metadata is checked here; C semantics, QC parity and vector execution are
    deliberately left pending until the delivered references are run.
    """
    def payload(section, key, prefixes, suffix=None):
        path = section.get(key)
        if (not isinstance(path, str) or path not in files or
                not any(path.startswith(prefix) for prefix in prefixes) or
                files[path]["bytes"] == 0 or (suffix and not path.endswith(suffix))):
            raise ValueError("missing/invalid registered payload: " + key)

    board = object_field(manifest, "board_model")
    if integer(board.get("version"), "board_model.version", 1, 2) != delivery_round:
        raise ValueError("board_model.version must match delivery_round")
    for dimension in ("input_width", "input_height"):
        integer(board.get(dimension), "board_model." + dimension, 1, 192)
    integer(board.get("parameter_count"), "board_model.parameter_count", 1, 1000000)
    for key in ("fp32", "int8", "preprocessing", "qc"):
        payload(board, key, ("board_model/",))
    if board["fp32"] == board["int8"]:
        raise ValueError("board FP32 and W8A8 payloads must be distinct")

    geometry = object_field(manifest, "geometry")

    def references(section, prefixes, minimum_vectors):
        for key, suffix in (("algorithm", None), ("c_reference", ".c"),
                            ("python_reference", ".py"), ("test_vectors", None)):
            payload(section, key, prefixes, suffix)
        integer(section.get("test_vector_count"), "geometry.test_vector_count", minimum_vectors, 1000000)

    references(geometry, ("geometry/",), 20)
    if delivery_round == 2 or "fallback" in geometry:
        references(object_field(geometry, "fallback"),
                   ("geometry/geometry_fallback/", "geometry_fallback/"), 1)
    if "golden/README.md" not in files:
        raise ValueError("verified golden/README.md required before smoke")
    if delivery_round == 1 and not any(name.startswith("relabel_candidate/") for name in files):
        raise ValueError("Round1 relabel_candidate payload missing")


def verify(directory, purpose="m0", adapter=None):
    if purpose not in ("m0", "geometry-smoke"):
        raise ValueError("purpose must be m0 or geometry-smoke")
    reject_link(directory)
    directory = directory.resolve(strict=True)
    manifest_path = directory / "manifest.json"
    reject_link(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    if manifest.get("format_profile") == "training-handoff-current-three-model-v1":
        from verify_picture_three_model import verify_current
        try:
            return verify_current(directory, manifest, purpose, adapter)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid three-model metadata: " + str(exc)) from exc
    if adapter is not None:
        raise ValueError("adapter is only supported for the explicit three-model profile")
    version = integer(manifest.get("contract_version"), "contract_version", 1, 2)
    scheme = manifest.get("scheme")
    board_detect = scheme == "board-detect-v2"
    if not board_detect and (version != 1 or "scheme" in manifest):
        raise ValueError("unknown scheme/version; return package for an explicit schema adaptation")
    if not board_detect and purpose != "m0":
        raise ValueError("geometry-smoke requires scheme board-detect-v2")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("files must be a nonempty relative-path -> {sha256, bytes} object")
    seen = set()
    for name, record in files.items():
        relative = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or relative.is_absolute() or
                any(part in ("", ".", "..") for part in name.split("/")) or name == "manifest.json"):
            raise ValueError("unsafe manifest path: " + name)
        folded = name.casefold()
        if folded in seen:
            raise ValueError("case-colliding package paths")
        seen.add(folded)
        path = directory / name
        for parent in (path,) + tuple(path.parents):
            if parent == directory:
                break
            reject_link(parent)
        if directory not in path.resolve().parents or not path.is_file():
            raise ValueError("missing/escaping package file: " + name)
        if not isinstance(record, dict) or type(record.get("bytes")) is not int or record["bytes"] < 0:
            raise ValueError("missing file size: " + name)
        expected = record.get("sha256", "")
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("invalid SHA-256: " + name)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if path.stat().st_size != record["bytes"] or digest.hexdigest() != expected:
            raise ValueError("file identity mismatch; return entire package: " + name)
    actual = set()
    for path in directory.rglob("*"):
        reject_link(path)
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(directory).as_posix().casefold())
    if actual != seen:
        raise ValueError("unlisted files in package")
    if not all(any(name.startswith(prefix) for name in files)
               for prefix in ("int8/", "golden/", "tools/", "report/")):
        raise ValueError("missing int8/golden/tools/report payloads")
    if "training_manifest.json" not in files or not any(name in files for name in ("best.pt", "best.onnx")):
        raise ValueError("missing training/environment/model provenance")
    delivery_round = None
    if board_detect:
        delivery_round = integer(manifest.get("delivery_round"), "delivery_round", 1, 2)
        if delivery_round == 1 and purpose != "geometry-smoke":
            raise ValueError("Round1 is geometry smoke only; use --purpose geometry-smoke; M0 requires Round2")
        verify_board_sections(manifest, files, delivery_round)
    metrics = object_field(manifest, "metrics")
    preview = delivery_round == 1
    if board_detect:
        p50 = number(metrics.get("board_corner_error_p50_px"), "board_corner_error_p50_px")
        p95 = number(metrics.get("board_corner_error_p95_px"), "board_corner_error_p95_px")
        if p50 > p95:
            raise ValueError("board corner error P50 exceeds P95")
        if not preview:
            assignment = number(metrics.get("board_grid_assignment_accuracy"),
                                "board_grid_assignment_accuracy", 0, 1)
            drift = number(metrics.get("board_quantization_drift_px"), "board_quantization_drift_px")
            if p50 > 8 or p95 > 15 or assignment < .99 or drift > 2:
                raise ValueError("reported board geometry metrics fail Round2 gates at 1280x720")
    result = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "files_verified": len(files), "contract_version": version,
              "scheme": scheme if board_detect else "legacy-piece-fit-v1",
              "delivery_round": delivery_round, "purpose": purpose,
              "reported_metrics_pass": False, "golden_smoke_pass": False,
              "m0_eligible": False, "m0_accepted": False,
              "main_chain_switch_allowed": False,
              "geometry_vectors_pass": False,
              "next": "Read verified golden/README and run its documented smoke; record exact command/output."}
    if preview:
        result["next"] = "Round1 geometry smoke only; record command/output. Main chain stays P19; M0 requires Round2."
        return result

    def fraction(name):
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("missing/invalid fraction: " + name)
        return value

    fp, quantized = fraction("fp32_board_exact_accuracy"), fraction("w8a8_board_exact_accuracy")
    if quantized < .85 or fp - quantized > .0200000001:
        raise ValueError("reported board accuracy or quantization drop fails M0")
    maps = metrics.get("class_map50", {})
    if not isinstance(maps, dict) or len(maps) != 14:
        raise ValueError("14-class mAP summary required")
    for name, value in maps.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("invalid class mAP: " + name)
    for name in ("black_pao", "black_ma", "red_ma"):
        if maps.get(name, -1) < .5:
            raise ValueError("reported weak-class gate fails: " + name)
    split = object_field(manifest, "split_games")
    if set(split) != {"train", "val", "test"} or any(not isinstance(v, list) or len(v) != 1 for v in split.values()):
        raise ValueError("each existing game must belong to exactly one split")
    gap = integer(manifest.get("boundary_gap_frames"), "boundary_gap_frames", 20, 1000000)
    if (any(type(v[0]) not in (int, str) for v in split.values()) or
            {str(v[0]) for v in split.values()} != {"1", "2", "3"} or gap < 20):
        raise ValueError("game split or 20-frame isolation missing")
    threshold = manifest.get("board_confidence_threshold_permille")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 1000:
        raise ValueError("frozen L1 threshold missing")
    result.update(reported_metrics_pass=True, m0_eligible=purpose == "m0")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--purpose", choices=("m0", "geometry-smoke"), default="m0")
    parser.add_argument("--adapter", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.directory, args.purpose, args.adapter)
        print(json.dumps(result, indent=2))
        if args.purpose == "geometry-smoke":
            print("PICTURE_GEOMETRY_MANIFEST_PASS geometry_smoke=PENDING M0=INELIGIBLE main_chain_switch=false")
        else:
            print("PICTURE_MODEL_MANIFEST_PASS golden_smoke=PENDING M0=PENDING main_chain_switch=false")
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, "PICTURE_MODEL_REJECT %s\n" % exc)
