"""Verify the entire read-only r08 archive before extracting private inputs to build/."""
import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def receive(archive, out, delivery='training_side_20261020_r08'):
    repo = Path(__file__).resolve().parents[2]
    out = out.resolve()
    if not out.is_relative_to(repo / 'build') or out.exists():
        raise ValueError('use a new build/ directory')
    with zipfile.ZipFile(archive) as source:
        members = {}
        seen = set()
        for entry in source.infolist():
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                    or ':' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('unsafe ZIP path')
            if entry.filename.casefold() in seen:
                raise ValueError('duplicate/case-colliding ZIP path')
            seen.add(entry.filename.casefold())
            if not entry.is_dir():
                members[entry.filename] = entry
        schemas = {'training_side_20261020_r08': 'training-side-delivery/20261020-r08',
                   'training_side_20261021_r09': 'training-side-delivery/20261021-r09'}
        root = delivery + '/'
        raw_manifest = source.read(root + 'manifest.json')
        manifest = json.loads(raw_manifest, object_pairs_hook=unique_object)
        if delivery not in schemas or manifest['schema'] != schemas[delivery]:
            raise ValueError('unexpected delivery identity')
        files = manifest['files']
        if set(members) != {root + name for name in files} | {root + 'manifest.json'}:
            raise ValueError('manifest coverage mismatch')
        for name, expected in files.items():
            data = source.read(root + name)
            if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise ValueError('delivery hash/size mismatch: ' + name)
        # All checks precede extraction; every resolved target remains in build/.
        out.mkdir(parents=True)
        for name in members:
            target = out / name.removeprefix(root)
            if not target.resolve().is_relative_to(out):
                raise ValueError('extraction escape')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(name))
    return dict(schema_version=1, status='PASS', files_verified=len(files),
                archive_bytes=archive.stat().st_size,
                archive_sha256=hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(),
                manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(),
                private_material_location='build/ only', independent_acceptance=False,
                production_ready=False, hardware_used=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = receive(args.archive, args.out)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))
