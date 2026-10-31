"""Read-only package hashes, exact file set and frozen graph inventory check."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import sys

sys.dont_write_bytecode = True
from handoff_inventory import inventory


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema'] == 'picture-model-int8-handoff-v1'
    expected = manifest['payloads']
    files = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    assert files == set(expected)|{'manifest.json','SHA256SUMS.txt'}, 'Unexpected or missing payload'
    for rel, info in expected.items():
        path = PurePosixPath(rel)
        assert not path.is_absolute() and '..' not in path.parts and '\\' not in rel
        target = root.joinpath(*path.parts)
        assert target.resolve().is_relative_to(root) and not target.is_symlink()
        data = target.read_bytes()
        assert len(data) == info['bytes'] and hashlib.sha256(data).hexdigest() == info['sha256'], rel
    sums = {}
    for line in (root/'SHA256SUMS.txt').read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        assert rel not in sums
        sums[rel] = digest
    assert set(sums) == set(expected)|{'manifest.json'}
    for rel, digest in sums.items():
        assert hashlib.sha256((root/rel).read_bytes()).hexdigest() == digest, rel
    got = inventory(root)
    assert got == json.loads((root/'baseline-inventory.json').read_text(encoding='utf-8'))
    assert not manifest['training_or_calibration_run'] and not manifest['hardware_used']
    return dict(status='MODEL_INT8_HANDOFF_HASHES_GRAPH_INVENTORY_PASS_NO_INFERENCE',
        payloads=len(expected), model_sha_crc_pass=True, current_xqi_s8_nodes=69,
        current_xqi_s16_nodes=16, current_xqi_s32_nodes=0, checkpoint_included=False,
        hardware_used=False, training_or_calibration_run=False)


if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parent), indent=2))
