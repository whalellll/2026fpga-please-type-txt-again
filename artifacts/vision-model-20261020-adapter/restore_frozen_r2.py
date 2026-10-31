"""Restore absent R2 payloads from the original ZIP, preserving every existing byte."""
import argparse
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
PREFIX = 'artifacts/vision-model-20261020/'
ZIP_SHA = '7b41a943e09fdd92763a72fff6c2bc2c73b200f5f00dea5c1014ddb8cb4ab16b'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    assert not args.receipt.exists(), 'preserve earlier receipts'
    assert sha(args.zip) == ZIP_SHA, 'original archive identity mismatch'
    root = (REPO / PREFIX).resolve()
    manifest_path = root / 'manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)['files']
    expected = {name: item if isinstance(item, str) else item['sha256']
                for name, item in manifest.items()}
    missing = []
    with zipfile.ZipFile(args.zip) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        assert len(names) == len(set(name.casefold() for name in names)), 'duplicate ZIP entries'
        assert set(names) == {PREFIX + name for name in expected} | {PREFIX + 'manifest.json'}
        assert archive.read(PREFIX + 'manifest.json') == manifest_bytes
        for name, digest in expected.items():
            relative = PurePosixPath(name)
            assert not relative.is_absolute() and '..' not in relative.parts
            assert '\\' not in name and ':' not in name
            target = root / name
            assert target.resolve().is_relative_to(root)
            entry = archive.getinfo(PREFIX + name)
            assert not entry.is_dir() and (entry.external_attr >> 16) & 0o170000 != 0o120000
            assert hashlib.sha256(archive.read(entry)).hexdigest() == digest, 'ZIP payload mismatch'
            if target.exists():
                assert target.is_file() and sha(target) == digest, 'existing frozen payload mismatch'
            else:
                missing.append((name, entry.file_size))
        missing_bytes = sum(size for _, size in missing)
        assert shutil.disk_usage(root).free > missing_bytes + 32 * 1024 * 1024, 'insufficient free space'
        # All archive and existing payload hashes have passed before the first write.
        for name, _ in missing:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.restore-part')
            with temporary.open('xb') as stream:
                stream.write(archive.read(PREFIX + name))
            assert sha(temporary) == expected[name]
            # Hard-link creation fails if target appeared; existing files cannot be replaced.
            os.link(temporary, target)
            temporary.unlink()
    assert manifest_path.read_bytes() == manifest_bytes
    for name, digest in expected.items():
        assert sha(root / name) == digest, 'post-restoration mismatch'
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    assert actual == set(expected) | {'manifest.json'}, 'unexpected frozen-tree file coverage'
    report = dict(status='PASS', original_zip_sha256=ZIP_SHA,
                  manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                  manifest_payloads=len(expected), zip_entries=len(entries),
                  restored_missing_payloads=len(missing), restored_bytes=missing_bytes,
                  existing_payloads_preserved=len(expected)-len(missing),
                  complete_manifest_and_coverage_verified=True, missing_payloads_after=0,
                  frozen_manifest_unchanged=True, default_profile_unchanged=True,
                  models={name: sha(root/'golden/software/weights'/f'{name}.pt')
                          for name in ('board', 'detector', 'classifier')},
                  image_decodes=0, inference_runs=0, hardware_used=False,
                  photos_or_model_binaries_added_to_git=False)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(f'FROZEN_R2_RESTORE_PASS payloads={len(expected)} restored={len(missing)} missing=0')


if __name__ == '__main__':
    main()
