"""Small synthetic regression-contract tests; never run RTL or vendor tools."""
import copy
import base64
from datetime import timedelta
from pathlib import Path
import tempfile
from verify_board_release import (CAMPAIGN_START, regression_test_paths, sha, validate_regression,
                                  git_object_hash, validate_implementation)


def synthetic_git_identity(files):
    """Build an explicitly synthetic Git object proof for isolated fixtures."""
    hierarchy, trees, blobs = {}, {}, {}
    for relative, content in files.items():
        parts = relative.split("/")
        cursor = hierarchy
        for name in parts[:-1]:
            cursor = cursor.setdefault(name, {})
        blobs[relative] = git_object_hash("blob", content)
        cursor[parts[-1]] = blobs[relative]
    def encode_tree(items):
        payload = b""
        for name, item in sorted(items.items(), key=lambda pair: pair[0] + ("/" if isinstance(pair[1], dict) else "")):
            mode, oid = (b"40000", encode_tree(item)) if isinstance(item, dict) else (b"100644", item)
            payload += mode + b" " + name.encode() + b"\0" + bytes.fromhex(oid)
        oid = git_object_hash("tree", payload)
        trees[oid] = base64.b64encode(payload).decode()
        return oid
    tree = encode_tree(hierarchy)
    commit = (f"tree {tree}\nauthor Synthetic Fixture <fixture@invalid> 0 +0000\n"
              "committer Synthetic Fixture <fixture@invalid> 0 +0000\n\nSYNTHETIC ONLY\n").encode()
    return dict(schema=1, object_format="sha1", commit_sha1=git_object_hash("commit", commit),
                commit_object_base64=base64.b64encode(commit).decode(), tree_objects_base64=trees,
                input_blob_sha1=blobs, all_frozen_inputs_match_commit=True)


def main():
    with tempfile.TemporaryDirectory(prefix="regression-contract-") as temporary:
        root = Path(temporary)
        for name in ("run_all_tests.ps1", "run_release_regression.ps1", "bounded_process.cs", "verify_board_release.py", "riscv_toolchain.ps1", "pds_scan_chain.tcl"):
            path = root / "scripts" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("SYNTHETIC ONLY", encoding="utf-8")
        (root / "sim").mkdir()
        (root / "sim/tb.sv").write_text("// SYNTHETIC ONLY", encoding="utf-8")
        scan_run = root / "scripts/pds_scan_chain_run.tcl"
        capability = root / "sim/linux_capability.hex"
        scan_run.write_text("generated scan arguments", encoding="utf-8")
        capability.write_text("generated capability ROM", encoding="utf-8")
        out, err = root / "stdout.txt", root / "stderr.txt"
        out.write_text("SOC_ALL_TESTS_PASS\n", encoding="utf-8")
        err.write_text("", encoding="utf-8")
        cpu = "a" * 64
        snapshot = {"started_utc": (CAMPAIGN_START + timedelta(minutes=3)).isoformat(),
                    "inputs": {"rtl/cpu/CoreTop.sv": cpu, "rtl/cpu/source.json": "b" * 64,
                               "config/clocks.json": "c" * 64, "ip/vendor.v": "d" * 64,
                               "artifacts/bootloader.bin": "e" * 64}}
        record = dict(schema_version=1, status="PASS", exit_code=0, marker="SOC_ALL_TESTS_PASS", cpu_rtl_sha256=cpu,
                      started_utc=CAMPAIGN_START.isoformat(), completed_utc=(CAMPAIGN_START + timedelta(minutes=2)).isoformat(),
                      source_files_sha256={key: val for key, val in snapshot["inputs"].items() if not key.startswith("artifacts/")},
                      test_files_sha256={name: sha(root / name) for name in regression_test_paths(root)},
                      transcript={"sha256": sha(out)}, stderr={"sha256": sha(err)})
        validate_regression(record, snapshot, cpu, out, err, root)
        checks = 1
        def reject(changed, pattern):
            try:
                validate_regression(changed, snapshot, cpu, out, err, root)
            except ValueError as error:
                assert pattern in str(error), str(error)
            else:
                raise AssertionError("Accepted invalid regression evidence")
        for mutation, expected in (
            (lambda r: r.pop("test_files_sha256"), "inventory"),
            (lambda r: r["test_files_sha256"].pop("scripts/riscv_toolchain.ps1"), "inventory"),
            (lambda r: r["source_files_sha256"].pop("config/clocks.json"), "source/configuration"),
            (lambda r: r["source_files_sha256"].update({"rtl/cpu/source.json": "f" * 64}), "source/configuration"),
            (lambda r: r.update(completed_utc=(CAMPAIGN_START + timedelta(minutes=4)).isoformat()), "before the final snapshot"),
            (lambda r: r.update(exit_code=False), "complete RTL regression"),
        ):
            changed = copy.deepcopy(record)
            mutation(changed)
            reject(changed, expected)
            checks += 1
        dependency = root / "scripts/riscv_toolchain.ps1"
        original = dependency.read_bytes()
        dependency.write_text("changed", encoding="utf-8")
        reject(record, "implementation changed")
        dependency.write_bytes(original)
        checks += 1
        added = root / "sim/new_case.py"
        added.write_text("# added during regression", encoding="utf-8")
        reject(record, "inventory")
        added.unlink()
        checks += 1
        for marker in ("NOT_SOC_ALL_TESTS_PASS\n", "SOC_ALL_TESTS_PASS\nSOC_ALL_TESTS_PASS\n"):
            out.write_text(marker, encoding="utf-8")
            changed = copy.deepcopy(record)
            changed["transcript"]["sha256"] = sha(out)
            reject(changed, "one complete success marker")
            checks += 1
        out.write_text("SOC_ALL_TESTS_PASS\n", encoding="utf-8")
        err.write_text("changed stderr", encoding="utf-8")
        reject(record, "stdout/stderr hash changed")
        checks += 1
        # Documentation-only edits and runtime output are not test implementation.
        err.write_text("", encoding="utf-8")
        (root / "sim/README.md").write_text("documentation update", encoding="utf-8")
        (root / "sim/temporary.vvp").write_text("generated output", encoding="utf-8")
        validate_regression(record, snapshot, cpu, out, err, root)
        checks += 1
        scan_run.write_text("regenerated for another scan", encoding="utf-8")
        capability.write_text("regenerated ROM", encoding="utf-8")
        validate_regression(record, snapshot, cpu, out, err, root)
        checks += 1
        scan_source = root / "scripts/pds_scan_chain.tcl"
        original_scan = scan_source.read_bytes()
        scan_source.write_text("changed real scan implementation", encoding="utf-8")
        reject(record, "implementation changed")
        scan_source.write_bytes(original_scan)
        checks += 1
        git_files = {"scripts/run_all_tests.ps1": (root / "scripts/run_all_tests.ps1").read_bytes()}
        proof_snapshot = {"inputs": {name: sha(root / name) for name in git_files},
                          "implementation_git": synthetic_git_identity(git_files)}
        commit = proof_snapshot["implementation_git"]["commit_sha1"]
        validate_implementation(proof_snapshot, commit, root)
        checks += 1
        for mutated, expected in ((copy.deepcopy(proof_snapshot), "mismatched"), (copy.deepcopy(proof_snapshot), "tree proof hash")):
            if expected == "mismatched":
                mutated["implementation_git"]["commit_sha1"] = "0" * 40
            else:
                trees = mutated["implementation_git"]["tree_objects_base64"]
                first = next(iter(trees))
                trees[first] = base64.b64encode(b"changed tree").decode()
            try:
                validate_implementation(mutated, commit, root)
            except ValueError as error:
                assert expected in str(error), str(error)
            else:
                raise AssertionError("Accepted changed implementation proof")
            checks += 1
        (root / "scripts/run_all_tests.ps1").write_text("uncommitted input", encoding="utf-8")
        try:
            validate_implementation(proof_snapshot, commit, root)
        except ValueError as error:
            assert "differs from Git" in str(error), str(error)
        else:
            raise AssertionError("Accepted uncommitted frozen input")
        checks += 1
    print(f"RELEASE_REGRESSION_CONTRACT_PASS checks={checks} SYNTHETIC_NO_RTL_NO_PDS_NO_JTAG")


if __name__ == "__main__":
    main()
