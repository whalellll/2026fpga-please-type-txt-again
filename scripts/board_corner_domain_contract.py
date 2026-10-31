"""Check retraining splits and score four-corner predictions without image access.

This is a training handoff tool, not a trainer, a native acceptance runner, or
permission to read sealed datasets. Actual image provenance needs a separate
audit. Keep real manifests and per-image reports in private storage.
"""
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


SPLITS = {"train", "dev", "blind"}
SEALED = re.compile(r"game[ _-]*2|camera[_-]*v2|camera[_-]*new[_-]*new|r20[_-]*truth", re.I)
SHA = re.compile(r"[0-9a-f]{64}\Z")


def validate_split(document):
    if document.get("schema") != "board-corner-domain-split/1":
        raise ValueError("Unexpected split schema")
    if not document.get("data_permission_reference"):
        raise ValueError("Record the actual data permission, not an inferred grant")
    records = document.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("A nonempty record list is required")
    seen, ownership = set(), {}
    counts = Counter()
    domains = defaultdict(Counter)
    for row in records:
        identity, split = row.get("id"), row.get("split")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Missing or duplicate sample id")
        seen.add(identity)
        if split not in SPLITS:
            raise ValueError("Use train, dev, or blind")
        if not isinstance(row.get("source"), str) or SEALED.search(row["source"]):
            raise ValueError("Missing source or explicitly excluded source")
        if row.get("regression_only") and split != "dev":
            raise ValueError("A diagnosed regression case is development data")
        for field in ("capture_group", "duplicate_cluster", "root_image_sha256", "image_sha256"):
            value = row.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError("Missing lineage field: " + field)
            if field.endswith("sha256") and not SHA.fullmatch(value):
                raise ValueError("Malformed image identity")
            key = field, value
            prior = ownership.setdefault(key, split)
            if prior != split:
                raise ValueError("Cross-split lineage leakage: " + field)
        for field in ("background", "exposure"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError("Missing domain field: " + field)
            domains[split + "/" + field][row[field]] += 1
        counts[split] += 1
    if set(counts) != SPLITS:
        raise ValueError("Training, development, and blind groups are all required")
    return {
        "status": "DECLARED_SPLIT_LINEAGE_PASS_NOT_IMAGE_PROVENANCE_ACCEPTANCE",
        "samples": dict(counts),
        "domains": {key: dict(value) for key, value in domains.items()},
        "images_read": False,
        "near_duplicates_independently_detected": False,
    }


def _quad(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Four ordered TL/TR/BR/BL points are required")
    result = []
    for point in value:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("A corner must have two coordinates")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point):
            raise ValueError("Finite numeric coordinates are required")
        result.append(point)
    return result


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * fraction
    low, high = math.floor(at), math.ceil(at)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def evaluate_predictions(document):
    if document.get("schema") != "board-corner-predictions/1":
        raise ValueError("Unexpected prediction schema")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("A nonempty prediction list is required")
    seen, scored = set(), []
    for row in rows:
        identity = row.get("id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Missing or duplicate prediction id")
        seen.add(identity)
        if row.get("split") not in SPLITS:
            raise ValueError("Every result must identify its split")
        width, height = row.get("width"), row.get("height")
        if any(type(n) is not int or n <= 1 for n in (width, height)):
            raise ValueError("Positive source image dimensions are required")
        truth = _quad(row.get("truth_pixel_centres"))
        if any(not (0 <= x < width and 0 <= y < height) for x, y in truth):
            raise ValueError("Truth is outside the source image")
        prediction = row.get("prediction")
        errors = None
        if prediction is not None:
            prediction = _quad(prediction)
            space = row.get("prediction_space")
            if space == "normalized_pixel_centres":
                prediction = [[x * width - 0.5, y * height - 0.5] for x, y in prediction]
            elif space != "pixel_centres":
                raise ValueError("Unknown prediction coordinate convention")
            errors = [math.hypot(x - tx, y - ty) for (x, y), (tx, ty) in zip(prediction, truth)]
        native = row.get("strict_native_status")
        if native is not None and (type(native) is not int or not 0 <= native <= 9):
            raise ValueError("Invalid declared native status")
        if native == 0 and prediction is None:
            raise ValueError("A missing prediction cannot claim native success")
        scored.append({
            "id": identity, "split": row["split"], "missing_prediction": prediction is None,
            "corner_error_px": errors,
            "max_corner_error_px": max(errors) if errors is not None else None,
            "mean_corner_error_px": sum(errors) / 4 if errors is not None else None,
            "declared_strict_native_status": native,
        })
    summaries = {}
    for split in sorted({row["split"] for row in scored}):
        selected = [row for row in scored if row["split"] == split]
        errors = [row["max_corner_error_px"] for row in selected if not row["missing_prediction"]]
        summaries[split] = {
            "samples": len(selected), "missing_predictions": len(selected) - len(errors),
            "max_error_px_p50_finite_only": _percentile(errors, 0.5),
            "max_error_px_p95_finite_only": _percentile(errors, 0.95),
            "native_status_reports": sum(row["declared_strict_native_status"] is not None for row in selected),
            "declared_native_geometry_passes": sum(row["declared_strict_native_status"] == 0 for row in selected),
        }
    return {
        "status": "CORNER_METRICS_ONLY_NOT_WHOLE_BOARD_ACCEPTANCE",
        "coordinate_conversion": "x=u*width-0.5; y=v*height-0.5",
        "native_status_independently_run": False,
        "whole_board_accuracy": None,
        "summary": summaries, "rows": scored,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("validate-split", "evaluate"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    result = validate_split(document) if args.operation == "validate-split" else evaluate_predictions(document)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
