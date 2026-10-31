"""r11 integrity intake only; game 2 contents are never parsed or evaluated."""
import argparse
import json
import hashlib
import stat
import zipfile
from pathlib import PurePosixPath
from pathlib import Path
from receive_r08 import unique_object


def receive(archive, out):
    repo = Path(__file__).resolve().parents[2]
    out = out.resolve()
    if not out.is_relative_to(repo/'build') or out.exists():
        raise ValueError('choose a fresh build/ directory')
    root = 'training_side_20261022_r11_新局接入/'
    with zipfile.ZipFile(archive) as z:
        members = {}; seen = set()
        for info in z.infolist():
            path = PurePosixPath(info.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename
                    or stat.S_ISLNK(info.external_attr >> 16) or info.filename.casefold() in seen):
                raise ValueError('unsafe/duplicate archive path')
            seen.add(info.filename.casefold())
            if not info.is_dir():members[info.filename] = info
        raw = z.read(root+'manifest.json')
        manifest = json.loads(raw, object_pairs_hook=unique_object)
        assert manifest['schema']=='training-side-delivery/20261022-r11'
        expected = {root+n for n in manifest['files']} | {root+'manifest.json'}
        missing = expected-set(members); extra = set(members)-expected
        if missing or extra-{root+'acceptance_game2_v3c.json'}:
            raise ValueError('unexpected manifest coverage mismatch')
        for name,item in manifest['files'].items():
            data=z.read(root+name)
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
                raise ValueError('manifest payload mismatch')
        out.mkdir(parents=True)
        # Unmanifested game-2 appendix stays inside the original ZIP; not read,
        # extracted, scored or treated as verified acceptance evidence.
        for name in expected:
            dest=out/name.removeprefix(root)
            assert dest.resolve().is_relative_to(out)
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
    with archive.open('rb') as f:archive_sha=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(status='MANIFEST_PAYLOADS_PASS_COVERAGE_INCOMPLETE' if extra else 'PASS',
                files_verified=len(manifest['files']), manifest_sha256=hashlib.sha256(raw).hexdigest(),
                archive_sha256=archive_sha, archive_bytes=archive.stat().st_size,
                full_manifest_coverage=not extra, unmanifested_appendix_count=len(extra),
                unmanifested_appendix_read=False, unmanifested_appendix_extracted=False,
                training_reissue_required=bool(extra), private_material_location='build/ only',
                production_ready=False, independent_acceptance=False, hardware_used=False)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    result = receive(a.archive, a.out)
    result.update(game2_content_parsed=False, game2_formal_results='pending human review and training reissue')
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('R11_INTAKE', result['status'], 'verified_payloads='+str(result['files_verified']))
