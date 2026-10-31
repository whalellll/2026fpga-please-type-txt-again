"""Check candidate ZIP bytes; deliberately makes no formal release claim."""
import hashlib
import json
from pathlib import PurePosixPath
import sys
from zipfile import ZipFile


def validate(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Duplicate candidate archive entries")
        for name in names:
            parts = PurePosixPath(name).parts
            if not name.startswith("SOC_CANDIDATE/") or "\\" in name or ":" in name or ".." in parts:
                raise ValueError("Unsafe candidate archive entry")
        record = json.loads(archive.read("SOC_CANDIDATE/candidate-delivery.json"))
        if record.get("status") != "CANDIDATE_NOT_RELEASE" or not record.get("incomplete_acceptance"):
            raise ValueError("Candidate must explicitly retain incomplete acceptance")
        expected = {"SOC_CANDIDATE/" + name for name in record["files_sha256"]}
        if set(names) != expected | {"SOC_CANDIDATE/candidate-delivery.json"}:
            raise ValueError("Candidate inventory differs")
        for name, value in record["files_sha256"].items():
            if hashlib.sha256(archive.read("SOC_CANDIDATE/" + name)).hexdigest() != value:
                raise ValueError("Candidate content hash differs: " + name)
        for name, field in (("rtl/cpu/source.json", "cpu_source_manifest_sha256"), ("rtl/cpu/CoreTop.sv", "cpu_rtl_sha256")):
            if record["files_sha256"][name] != record[field]:
                raise ValueError("Candidate CPU identity differs")
        return record


if __name__ == "__main__":
    try:
        record = validate(sys.argv[1])
        print("SOC_CANDIDATE_CONTENT_HASH_PASS formal_release=false")
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit("CANDIDATE_ZIP_REJECTED: " + str(error))
