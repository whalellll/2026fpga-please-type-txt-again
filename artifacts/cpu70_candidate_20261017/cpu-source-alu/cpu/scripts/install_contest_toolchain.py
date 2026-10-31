#!/usr/bin/env python3
"""Download and extract the pinned standalone Windows RISC-V compiler.

Requires Python 3.8+ and an explicitly selected bsdtar with zstd support.
No pacman operation, system installation, PATH persistence or recursive deletion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = ROOT / 'handoff/toolchain/gcc14_2/packages.lock.json'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for data in iter(lambda: source.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def regular_path(path):
    """Reject linked existing components, including Windows junctions."""
    path = Path(os.path.abspath(path))
    for item in [path] + list(path.parents):
        if item.exists() or item.is_symlink():
            attrs = item.lstat()
            if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Linked destination/cache component: ' + str(item))
    return path


def command(argv, cwd, env, deadline, log=None, seconds=120):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Overall installation deadline reached')
    process = subprocess.Popen([str(item) for item in argv], cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        stdout, stderr = process.communicate(timeout=min(seconds, remaining))
    except BaseException:
        # Kill while the root process is still present so compiler children are included.
        try:
            subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'),
                            '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
        finally:
            process.kill()
            process.communicate(timeout=15)
        raise
    if log:
        log.write_text(stdout + stderr, encoding='utf-8')
    if process.returncode:
        raise RuntimeError('Command failed with exit {}: {}\n{}'.format(process.returncode, argv[0], stderr[-1500:]))
    return stdout.strip()


def download(package, cache, deadline):
    target = regular_path(cache / package['filename'])
    if target.exists():
        if not target.is_file() or digest(target) != package['sha256']:
            raise ValueError('Existing cache file differs from lock; inspect it before retrying: ' + str(target))
        return target
    part = regular_path(cache / (package['filename'] + '.partial'))
    if part.exists():
        raise ValueError('Previous partial download retained; inspect/remove it before retrying: ' + str(part))
    try:
        import ssl  # noqa: F401; urllib otherwise reports an opaque "unknown url type".
    except ImportError as error:
        raise RuntimeError('Python HTTPS/SSL support is unavailable; use a complete native Python installation or a verified offline package cache') from error
    limit = min(deadline, time.monotonic() + 300)
    request = urllib.request.Request(package['url'], headers={'User-Agent': 'cpu-toolchain-installer/1'})
    with urllib.request.urlopen(request, timeout=15) as response, part.open('xb') as output:
        if urllib.parse.urlparse(response.url).scheme != 'https':
            raise ValueError('Non-HTTPS download redirect')
        received = 0
        while True:
            if time.monotonic() > limit:
                raise TimeoutError('Package download deadline reached')
            block = response.read(1024 * 1024)
            if not block:
                break
            received += len(block)
            if received > package['compressed_bytes']:
                raise ValueError('Download exceeds locked package size')
            output.write(block)
    if received != package['compressed_bytes'] or digest(part) != package['sha256']:
        raise ValueError('Package size/SHA256 mismatch: ' + package['filename'])
    part.replace(target)
    return target


def archive_path(name, metadata=False):
    if metadata and name in ('.PKGINFO', '.BUILDINFO', '.MTREE', '.INSTALL'):
        return
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or any(c.isspace() for c in name)
            or path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'ucrt64'):
        raise ValueError('Unsafe/unexpected archive path: ' + repr(name))


def inspect_archive(tar, package_path, cwd, env, deadline):
    names = command([tar, '-tf', package_path], cwd, env, deadline, seconds=60).splitlines()
    for name in names:
        archive_path(name, metadata=True)
    verbose = command([tar, '-tvf', package_path], cwd, env, deadline, seconds=60).splitlines()
    if len(verbose) != len(names):
        raise ValueError('Archive listing count mismatch')
    for line in verbose:
        if not line or line[0] not in '-dh':
            raise ValueError('Archive contains symbolic links or unsupported entry types')
        if line[0] == 'h':
            if ' link to ' not in line:
                raise ValueError('Unrecognized hard-link listing')
            archive_path(line.split(' link to ', 1)[1])
    return len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True, help='New directory; never overwrite an existing installation')
    parser.add_argument('--tar', type=Path, required=True, help='bsdtar executable with built-in libzstd support')
    parser.add_argument('--cache', type=Path, help='Optional package cache; default <destination>/packages')
    parser.add_argument('--lock', type=Path, default=DEFAULT_LOCK)
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args()
    if os.name != 'nt':
        raise ValueError('This pinned UCRT64 toolchain installer targets Windows x86_64')
    if not 60 <= args.timeout_seconds <= 3600:
        raise ValueError('Overall timeout must be 60..3600 seconds')
    deadline = time.monotonic() + args.timeout_seconds
    args.lock = regular_path(args.lock)
    dest, tar = regular_path(args.destination), regular_path(args.tar)
    if dest.exists():
        raise ValueError('Destination must not already exist: ' + str(dest))
    if not tar.is_file():
        raise ValueError('Missing bsdtar executable')
    lock = json.loads(args.lock.read_text(encoding='utf-8'))
    packages = lock['packages']
    if len(packages) != 12 or len({p['name'] for p in packages}) != 12:
        raise ValueError('Expected the reviewed twelve-package dependency closure')
    names = {p['name'] for p in packages}
    for package in packages:
        if (not re.fullmatch(r'[A-Za-z0-9_.+-]+\.pkg\.tar\.zst', package['filename'])
                or not re.fullmatch('[0-9a-f]{64}', package['sha256'])
                or package['url'] != 'https://repo.msys2.org/mingw/ucrt64/' + package['filename']):
            raise ValueError('Invalid official package lock entry')
        for dependency in package['dependencies']:
            if lock['dependency_aliases'].get(dependency, dependency) not in names:
                raise ValueError('Unpinned dependency: ' + dependency)
    dest.mkdir(parents=True, exist_ok=False)
    cache = regular_path(args.cache or dest / 'packages')
    cache.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(dest).free < lock['installed_bytes'] + lock['compressed_bytes'] + 100 * 1024 * 1024:
        raise ValueError('Insufficient free space; reserve at least 2 GiB for this locked toolchain')
    system = Path(os.environ['SystemRoot'])
    base_path = str(system / 'System32') + os.pathsep + str(system)
    tar_env = dict(os.environ, PATH=str(tar.parent) + os.pathsep + base_path, LC_ALL='C')
    logdir = dest / 'validation'
    logdir.mkdir()
    report = dict(status='RUNNING', target=lock['target'], gcc_version=lock['gcc_version'],
                  lock_sha256=digest(args.lock), packages=[], system_modified=False,
                  downloaded_signature_reverified=False,
                  trust='Official HTTPS package downloads checked against committed SHA256 lock; original signature evidence is archived separately')
    try:
        version = command([tar, '--version'], dest, tar_env, deadline, seconds=15)
        if 'libzstd/' not in version:
            raise ValueError('Selected bsdtar lacks built-in libzstd; Windows inbox tar may be insufficient')
        report['archive_tool'] = version
        for i, package in enumerate(packages, 1):
            package_path = download(package, cache, deadline)
            count = inspect_archive(tar, package_path, dest, tar_env, deadline)
            # A single --include= argument prevents MSYS runtime wildcard
            # expansion when the caller is native Windows Python, not Bash.
            command([tar, '-x', '--no-same-owner', '--no-same-permissions', '--include=ucrt64/*', '-f', package_path, '-C', dest],
                    dest, tar_env, deadline, logdir / (package['name'] + '.extract.log'), seconds=180)
            regular_path(dest / 'ucrt64')
            report['packages'].append(dict(name=package['name'], sha256=package['sha256'], archive_entries=count))
            print('PACKAGE {}/{} VERIFIED_EXTRACTED {}'.format(i, len(packages), package['name']), flush=True)
        bindir = dest / 'ucrt64/bin'
        compiler_env = dict(os.environ, PATH=str(bindir) + os.pathsep + base_path)
        gcc = bindir / 'riscv32-unknown-elf-gcc.exe'
        target = command([gcc, '-dumpmachine'], dest, compiler_env, deadline, seconds=15)
        version = command([gcc, '-dumpfullversion'], dest, compiler_env, deadline, seconds=15)
        if (target, version) != (lock['target'], lock['gcc_version']):
            raise ValueError('Extracted compiler target/version differs from lock')
        library = command([gcc, '-march=' + lock['libgcc_query_march'], '-mabi=ilp32', '-print-libgcc-file-name'], dest, compiler_env, deadline, seconds=15)
        library = regular_path(Path(library))
        if dest not in library.parents or digest(library) != lock['libgcc_sha256']:
            raise ValueError('Selected libgcc lies outside the installation or differs from the audited library')
        probe = args.lock.parent / 'probe.c'
        command([gcc, '-O2', '-march=' + lock['march'], '-mabi=ilp32', '-ffreestanding', '-fno-builtin',
                 '-nostdlib', '-nostartfiles', '-Wl,-e,_start', '-Wl,-Ttext=0x1c000000', probe, library,
                 '-o', logdir / 'probe.elf'], dest, compiler_env, deadline, logdir / 'probe-build.log', seconds=30)
        attributes = command([bindir / 'riscv32-unknown-elf-readelf.exe', '-h', '-A', logdir / 'probe.elf'], dest, compiler_env,
                             deadline, logdir / 'probe-elf.txt', seconds=15)
        elf = (logdir / 'probe.elf').read_bytes()
        # Binutils 2.47 prints Flags: 0x0 without spelling out soft-float.
        # ELF32 e_flags bits 0 (RVC) and 2:1 (floating ABI) are authoritative.
        if (elf[:6] != b'\x7fELF\x01\x01' or int.from_bytes(elf[18:20], 'little') != 243
                or int.from_bytes(elf[36:40], 'little') & 7 or 'ELF32' not in attributes):
            raise ValueError('Probe ELF class/ABI/compression check failed')
        baseline = json.loads((args.lock.parent / 'baseline-result.json').read_text(encoding='utf-8-sig'))
        probe_hash = digest(logdir / 'probe.elf')
        if probe_hash != baseline['probe_elf_sha256']:
            raise ValueError('Probe ELF differs from the independently audited baseline')
        report.update(status='PASS', compiler_target=target, compiler_version=version,
                      libgcc_sha256=digest(library), probe_elf_sha256=probe_hash,
                      clean_path_probe_link='PASS: only new ucrt64/bin and Windows system directories', probe_executed=False,
                      scope='Package integrity, isolated extraction and target/ABI/probe reproduction; no CPU or board execution')
        shutil.copyfile(args.lock, dest / 'packages.lock.json')
    except BaseException as error:
        report.update(status='INCOMPLETE', error=str(error))
        raise
    finally:
        report['elapsed_seconds'] = round(args.timeout_seconds - (deadline - time.monotonic()), 3)
        (dest / 'install-result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('CONTEST_TOOLCHAIN_INSTALL_PASS ' + str(dest / 'ucrt64'))


if __name__ == '__main__':
    main()
