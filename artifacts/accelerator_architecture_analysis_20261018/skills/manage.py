#!/usr/bin/env python3
"""Review, validate, migrate and install this portable skills library (Python 3)."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import zipfile

LIBRARY_ID = 'fpga-soc-engineering-skills'
CORE_SKILLS = (
    'accelerator-performance', 'fpga-timing-optimization',
    'accelerator-model-compatibility', 'soc-hardware-software-codesign',
    'fpga-soc-board-debug',
)
DELIVERY_SOURCES = ('README.md', 'AGENTS.md', 'scripts/create_delivery.ps1',
                    'scripts/verify_delivery.ps1', 'scripts/invoke_project_skills.ps1',
                    'scripts/test_project_skills.py')
RECEIPT = '.fpga-soc-skills-install.json'


class SkillError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise SkillError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.skills-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, path)
    finally:
        temporary = Path(temporary)
        if temporary.exists():
            require(temporary.resolve().parent == path.parent.resolve(), 'Unsafe temporary file')
            temporary.unlink()


def child(root, relative):
    root = Path(root).resolve()
    require(isinstance(relative, str) and relative and '\\' not in relative,
            'Invalid relative path: %r' % relative)
    pure = PurePosixPath(relative)
    require(not pure.is_absolute() and not re.match(r'^[A-Za-z]:', relative)
            and all(p not in ('', '.', '..') for p in relative.split('/')),
            'Unsafe relative path: ' + relative)
    target = root.joinpath(*pure.parts)
    require(root in target.resolve().parents, 'Path escapes skills root: ' + relative)
    for component in (target, *target.parents):
        if component == root:
            break
        require(not component.is_symlink(), 'Symlink cannot be packaged: ' + str(component))
    return target


def content_files(root):
    root = Path(root).resolve()
    require(root.is_dir(), 'Missing skills directory: ' + str(root))
    entries = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if '__pycache__' in path.parts:
            continue
        child(root, relative)
        if not path.is_file() or relative == 'manifest.json':
            continue
        require(path.suffix.lower() not in ('.sbit', '.bit', '.bin', '.adf', '.log', '.zip', '.pyc'),
                'Build/debug artifact is not a skill: ' + relative)
        entries[relative] = digest(path)
    return entries


def structure(root):
    root = Path(root).resolve()
    names = sorted(p.name for p in root.iterdir()
                   if p.is_dir() and p.name != '__pycache__')
    require(set(CORE_SKILLS).issubset(names), 'Missing required skill')
    require((root/'README.md').is_file() and (root/'manage.py').is_file(), 'Missing library tools/index')
    for name in names:
        require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) and len(name) < 64,
                'Invalid skill directory: ' + name)
        directory = child(root, name)
        entry = directory/'SKILL.md'
        require(entry.is_file(), 'Missing SKILL.md: ' + name)
        text = entry.read_text(encoding='utf-8')
        front = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
        require(front is not None, 'Missing frontmatter: ' + name)
        require(re.search(r'^name:\s*' + re.escape(name) + r'\s*$', front[1], re.M),
                'Skill name mismatch: ' + name)
        require(re.search(r'^description:\s*\S.+$', front[1], re.M), 'Missing description: ' + name)
        require('[TODO:' not in text, 'Unfinished scaffold: ' + name)
        ui = directory/'agents/openai.yaml'
        require(ui.is_file() and '$'+name in ui.read_text(encoding='utf-8'),
                'Missing callable UI metadata: ' + name)
        for document in directory.rglob('*.md'):
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
                if target.startswith(('https://', 'http://', '#')):
                    continue
                target = target.split('#', 1)[0]
                require(not Path(target).is_absolute() and not re.match(r'^[A-Za-z]:', target),
                        'Nonportable resource: ' + target)
                referenced = (document.parent/target).resolve()
                require(directory in referenced.parents and referenced.is_file(),
                        'Missing or external skill resource: ' + name + '/' + target)
    return names


def review(root, note, reviewed_on=None, version=None):
    root = Path(root).resolve()
    require(bool(note.strip()), 'A specific review note is required')
    reviewed_on = reviewed_on or date.today().isoformat()
    date.fromisoformat(reviewed_on)
    previous = load(root/'manifest.json') if (root/'manifest.json').is_file() else {}
    require(not previous or previous.get('library_id') == LIBRARY_ID, 'Foreign library manifest')
    value = {'schema_version': 1, 'library_id': LIBRARY_ID,
             'version': version or previous.get('version', '1.0.0'),
             'revision': previous.get('revision', 0) + 1,
             'reviewed_on': reviewed_on, 'review_note': note.strip(),
             'skills': structure(root), 'files': content_files(root)}
    write_json(root/'manifest.json', value)
    return verify(root)


def verify(root):
    root = Path(root).resolve()
    manifest = root/'manifest.json'
    require(manifest.is_file(), 'Missing reviewed skills manifest; run review')
    value = load(manifest)
    require(value.get('schema_version') == 1 and value.get('library_id') == LIBRARY_ID,
            'Unknown skills manifest')
    require(isinstance(value.get('revision'), int) and value['revision'] > 0
            and bool(value.get('version')) and bool(value.get('review_note', '').strip()),
            'Missing skills revision/review')
    date.fromisoformat(value['reviewed_on'])
    for name, expected in value['files'].items():
        child(root, name)
        require(re.fullmatch(r'[0-9a-f]{64}', expected), 'Invalid SHA-256: ' + name)
    require(value['skills'] == structure(root), 'Skill inventory changed; run review')
    require(value['files'] == content_files(root), 'Skills modified, missing or untracked; run review')
    return value


def sync(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    value = verify(source)
    if source == destination:
        return value
    require(source not in destination.parents and destination not in source.parents,
            'Source/destination skills trees overlap')
    old = None
    if destination.exists() and any(destination.iterdir()):
        old = verify(destination)  # refuse to overwrite unreviewed local changes
        require(old['revision'] <= value['revision'], 'Destination is newer than source')
    destination.mkdir(parents=True, exist_ok=True)
    for name in value['files']:
        target = child(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(child(source, name), target)
    if old:
        for name in old['files'].keys() - value['files'].keys():
            child(destination, name).unlink()
        for path in sorted(destination.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                child(destination, path.relative_to(destination).as_posix()).rmdir()
    shutil.copy2(source/'manifest.json', destination/'manifest.json')
    return verify(destination)


def workspace_sync(project):
    project = Path(project).resolve()
    local, upstream = project/'skills', project.parent/'skills'
    if (upstream/'manifest.json').is_file() and load(upstream/'manifest.json').get('library_id') == LIBRARY_ID:
        return sync(upstream, local)
    return verify(local)


def installed_files(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def install(root, destination=None):
    root = Path(root).resolve()
    destination = Path(destination or Path.home()/'.agents/skills').resolve()
    value = verify(root)
    require(root != destination and root not in destination.parents and destination not in root.parents,
            'Installation destination overlaps source')
    receipt = load(destination/RECEIPT) if (destination/RECEIPT).is_file() else {}
    require(not receipt or receipt.get('library_id') == LIBRARY_ID, 'Foreign installation receipt')
    desired = {name: {path[len(name)+1:]: hash_value for path, hash_value in value['files'].items()
                     if path.startswith(name+'/')} for name in value['skills']}
    for name in value['skills']:
        target = child(destination, name)
        if target.exists():
            require(target.is_dir() and not target.is_symlink(), 'Invalid installed directory: ' + name)
            previous = receipt.get('skills', {}).get(name)
            require(previous is not None and installed_files(target) == previous,
                    'Unmanaged skill or local edits; refusing overwrite: ' + name)
            for path in previous:
                child(target, path)
    # All overwrite decisions are checked before copying any skill.
    destination.mkdir(parents=True, exist_ok=True)
    for name, files in desired.items():
        target = child(destination, name)
        target.mkdir(exist_ok=True)
        for path in files:
            output = child(target, path)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child(root, name+'/'+path), output)
        for path in receipt.get('skills', {}).get(name, {}).keys() - files.keys():
            child(target, path).unlink()
        require(installed_files(target) == files, 'Installed file verification failed: ' + name)
    write_json(destination/RECEIPT, {'library_id': LIBRARY_ID,
               'manifest_sha256': digest(root/'manifest.json'), 'skills': desired})
    return {'destination': str(destination), 'skills': value['skills']}


def stage(root, project, package):
    root, project, package = Path(root).resolve(), Path(project).resolve(), Path(package).resolve()
    require(project != package and package not in root.parents and package != root,
            'Delivery stage must be separate from source')
    value = sync(root, package/'skills')
    sources = {}
    for name in DELIVERY_SOURCES:
        source, delivered = child(project, name), child(package, name)
        require(source.is_file() and delivered.is_file() and digest(source) == digest(delivered),
                'Delivery source missing/mixed: ' + name)
        sources[name] = digest(delivered)
    write_json(package/'SKILLS_DELIVERY.json', {
        'schema_version': 1, 'library_id': LIBRARY_ID, 'version': value['version'],
        'revision': value['revision'], 'reviewed_on': value['reviewed_on'],
        'manifest_sha256': digest(package/'skills/manifest.json'),
        'packaged_at_utc': datetime.now(timezone.utc).isoformat(), 'source_files': sources})
    return verify_delivery(package, root)


def verify_delivery(package, expected=None):
    package = Path(package).resolve()
    value = verify(package/'skills')
    require((package/'SKILLS_DELIVERY.json').is_file(), 'Missing SKILLS_DELIVERY.json')
    snapshot = load(package/'SKILLS_DELIVERY.json')
    require(snapshot.get('schema_version') == 1 and snapshot.get('library_id') == LIBRARY_ID,
            'Invalid skills delivery metadata')
    for key in ('version', 'revision', 'reviewed_on'):
        require(snapshot.get(key) == value[key], 'Mixed skills delivery: ' + key)
    require(snapshot.get('manifest_sha256') == digest(package/'skills/manifest.json'), 'Skills snapshot mismatch')
    require(set(snapshot['source_files']) == set(DELIVERY_SOURCES), 'Missing source association')
    for name, expected_hash in snapshot['source_files'].items():
        path = child(package, name)
        require(path.is_file() and digest(path) == expected_hash, 'Missing/mixed delivery file: ' + name)
    if expected is not None:
        expected = Path(expected).resolve()
        verify(expected)
        require(digest(expected/'manifest.json') == snapshot['manifest_sha256'], 'Stale skills delivery')
    return snapshot


def pack(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    value = verify(root)
    require(output != root and root not in output.parents, 'Archive must be outside skills source')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name+'.tmp')
    require(not temporary.exists(), 'Archive temporary path already exists')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in [*value['files'], 'manifest.json']:
                archive.write(child(root, name), 'skills/'+name)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            require(temporary.resolve().parent == output.parent, 'Unsafe archive temporary path')
            temporary.unlink()
    output.with_name(output.name+'.sha256').write_text(digest(output)+'  '+output.name+'\n', encoding='utf-8')
    return {'archive': str(output), 'sha256': digest(output), 'skills': value['skills']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('review', 'verify', 'sync', 'install', 'stage', 'pack'):
        p = sub.add_parser(command)
        p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
        if command == 'review':
            p.add_argument('--note', required=True)
            p.add_argument('--date')
            p.add_argument('--version')
        if command in ('sync', 'install'):
            p.add_argument('--destination', type=Path, required=command == 'sync')
        if command == 'stage':
            p.add_argument('--project', type=Path, required=True)
            p.add_argument('--stage', type=Path, required=True)
        if command == 'pack':
            p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('workspace-sync')
    p.add_argument('--project', type=Path, required=True)
    p = sub.add_parser('verify-delivery')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--expected', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'review': result = review(args.root, args.note, args.date, args.version)
        elif args.command == 'verify': result = verify(args.root)
        elif args.command == 'sync': result = sync(args.root, args.destination)
        elif args.command == 'install': result = install(args.root, args.destination)
        elif args.command == 'workspace-sync': result = workspace_sync(args.project)
        elif args.command == 'stage': result = stage(args.root, args.project, args.stage)
        elif args.command == 'verify-delivery': result = verify_delivery(args.package, args.expected)
        else: result = pack(args.root, args.output)
    except (SkillError, OSError, KeyError, TypeError, ValueError) as error:
        print('SKILLS_FAIL: '+str(error), file=sys.stderr)
        return 1
    # ASCII JSON works on Windows consoles as well as UTF-8 terminals.
    print(json.dumps({'status': 'SKILLS_PASS', 'command': args.command,
                      **{k: v for k, v in result.items() if k not in ('files', 'source_files')}}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
