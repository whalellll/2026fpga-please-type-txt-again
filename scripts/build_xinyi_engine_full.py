"""Rebuild every PN08-bound prepared Pikafish object with the V2 producer.

No old objects, hardware, model payloads or media are reused/changed. The
original123 source bindings are checked before copying into a fresh private
tree; the current service differs only by the explicit V2 timestamp overlay.
"""
import argparse
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

from picture_workspace import ROOT, workspace_path, wsl_path

SHA = lambda b: hashlib.sha256(b).hexdigest()
SOURCE = '/var/tmp/xinyi-nnue-source.e42-bfa0ff8f9dd948e4a117397b9382ea9d'
FLAGS = '-DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_EMBEDDED_GUI'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--bindings', type=Path, required=True)
    ap.add_argument('--resume-fresh-closeout', action='store_true',
                    help='Finish a preserved successful full compile after a closeout-only failure; never imports old objects')
    a = ap.parse_args()
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    if a.resume_fresh_closeout:
        assert out.is_dir()
        previous = (out / 'result.json').read_bytes()
        assert json.loads(previous)['status'] == 'FAILED_PRESERVED'
        assert (out / 'prepare-source.log').read_text().startswith('PN08_ALL123_SOURCES_EXACT_NEW_TREE_NO_OBJECTS')
        closeout_round = len(list(out.glob('builder-closeout*.py'))) + 1
        failed_name = out / ('result.failed-closeout-r%02d.json' % closeout_round)
        assert not failed_name.exists()
        failed_name.write_bytes(previous)
        (out / ('builder-closeout-r%02d.py' % closeout_round)).write_bytes(Path(__file__).read_bytes())
    else:
        out.mkdir(parents=True, exist_ok=False)
    bindings = workspace_path(a.bindings)
    rows = []
    for line in bindings.read_text().splitlines():
        h, name = line.split(None, 1)
        if name.startswith(SOURCE + '/src/'):
            rows.append((name[len(SOURCE) + 1:], h))
    assert len(rows) == 123
    service = (ROOT / 'linux/xinyi_board/engine_service.cpp').read_bytes()
    original = subprocess.check_output(['git', 'show',
        '776f217c68305ff8c074862c9b9c0d35bdfeaf81:linux/xinyi_board/engine_service.cpp'], cwd=ROOT, timeout=30)
    assert SHA(original) == '409d26bc5a456aaeb0607f1ebe5dca9d41a7841e6f7d89b7e270fb42a173bd95'
    assert b'XQ_ENGINE_RESULT_V2' in service and b'#if XINYI_BATTLE_R17' in service
    if a.resume_fresh_closeout:
        assert (out / 'service.cpp').read_bytes() == service
        assert (out / 'service-original.cpp').read_bytes() == original
        assert (out / 'pn08-original-source-bindings.sha256').read_bytes() == bindings.read_bytes()
    else:
        (out / 'service.cpp').write_bytes(service)
        (out / 'service-original.cpp').write_bytes(original)
        (out / 'pn08-original-source-bindings.sha256').write_bytes(bindings.read_bytes())
        (out / 'builder.py').write_bytes(Path(__file__).read_bytes())
    result = dict(status='FAILED_PRESERVED', hardware_used=False, installed=False,
                  original_core_bindings=123, old_objects_reused=False)

    def run(name, args, limit=120, env=None, rc=(0,)):
        cmd = ['env', *(f'{k}={v}' for k, v in (env or {}).items()), *args]
        with (out / (name + '.log')).open('xb') as log:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=5 ' + str(limit) + ' ' + shlex.join(cmd)],
                stdout=log, stderr=subprocess.STDOUT, timeout=limit + 20)
        assert p.returncode in rc, (name, p.returncode, (out / (name + '.log')).read_text(errors='replace')[-3000:])

    native = wsl_path(out)
    try:
        # Only source/assembly/build metadata/support scripts are copied. No
        # .o/.a/ELF/NNUE/PFF/model payload can enter this new source tree.
        code = '''from pathlib import Path
import hashlib,json,shutil
source=Path(%r);target=Path(%r)/'prepared';expected=dict(%r)
for n,h in expected.items():
 p=source/n;assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==h,n
target.mkdir();copied={}
for sub in ['src','scripts']:
 for p in (source/sub).rglob('*'):
  if not p.is_file() or p.is_symlink():continue
  keep=(sub=='scripts' and p.suffix=='.sh') or (sub=='src' and (p.suffix in ['.cpp','.h','.inc','.S'] or p.name in ['Makefile','.build_sha.txt','.build_date.txt','.build_diffindex.txt']))
  if not keep:continue
  n=p.relative_to(source).as_posix();q=target/n;q.parent.mkdir(parents=True,exist_ok=True);data=p.read_bytes();q.write_bytes(data);copied[n]=hashlib.sha256(data).hexdigest()
assert not list(target.rglob('*.o')) and not list(target.rglob('*.a'))
assert all(copied[n]==h for n,h in expected.items())
(target.parent/'prepared-source-inputs.json').write_text(json.dumps(copied,indent=2)+'\\n')
print('PN08_ALL123_SOURCES_EXACT_NEW_TREE_NO_OBJECTS',len(copied))
''' % (SOURCE, native, rows)
        if not a.resume_fresh_closeout:
            run('prepare-source', ['python3', '-c', code], 60)
        prepared = out / 'prepared'
        source_inputs = json.loads((out / 'prepared-source-inputs.json').read_text())
        assert all(SHA((prepared / n).read_bytes()) == h for n, h in source_inputs.items())
        if not a.resume_fresh_closeout:
            assert not list(prepared.rglob('*.o'))
        src = native + '/prepared/src'
        cross = '/opt/toolchain/bin/riscv32-linux-musl-g++'
        if not a.resume_fresh_closeout:
            run('service-v2-build', [cross, '-std=c++17', '-march=rv32ima', '-mabi=ilp32',
                '-O2', '-flto', '-Wall', '-Wextra', '-Werror', '-DXINYI_BATTLE_R17=1',
                '-iquote', src, '-c', native + '/service.cpp', '-o', native + '/service-v2.o'])
        # Pin only build metadata; search policy/flags remain the original
        # five prepared macros and original RV32 Makefile.
        epoch = int(datetime.datetime(2026, 10, 26, tzinfo=datetime.timezone.utc).timestamp())
        make_args = ['make', '-s', '-C', src, '-j2', 'ARCH=riscv32', 'COMP=gcc',
            'CXX=' + cross, 'EXTRACXXFLAGS=' + FLAGS, 'GIT_SHA=', 'GIT_DATE=',
            'GIT_DIFFINDEX=', 'COMPILER_DATE=20261026']
        if not a.resume_fresh_closeout:
            run('full-v2-engine-build', [*make_args, 'EXTRALDFLAGS=' + native + '/service-v2.o', 'pikafish'],
                900, env={'SOURCE_DATE_EPOCH': str(epoch)})
            (out / 'xinyi-engine-v2.debug').write_bytes((prepared / 'src/pikafish').read_bytes())
            run('strip-v2', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
                '-o', native + '/xinyi-engine-v2', native + '/xinyi-engine-v2.debug'], 30)
            run('v2-elf', ['/opt/toolchain/bin/riscv32-linux-musl-readelf', '-h', '-A', native + '/xinyi-engine-v2'], 30)
        assert all(SHA((prepared / n).read_bytes()) == h for n, h in source_inputs.items())
        objects = sorted(p.relative_to(prepared).as_posix() for p in prepared.rglob('*.o'))
        # Keep make syntax in a file, never in a shell-command argument where
        # Windows/WSL quoting could treat a make variable as shell substitution.
        (out / 'object-query.mk').write_text('include Makefile\n.PHONY: xinyi_list_objects\nxinyi_list_objects:\n\t$(file >' + native + '/expected-object-list.txt,$(OBJS))\n\t@:\n')
        run('expected-make-object-list', [*make_args, '-f', native + '/object-query.mk', 'xinyi_list_objects'], 30,
            env={'SOURCE_DATE_EPOCH': str(epoch)})
        expected_objects = {'src/' + n for n in (out / 'expected-object-list.txt').read_text().split()}
        assert set(objects) == expected_objects and 'src/main.o' in objects
        # This reuses only the just-built, independently fresh core, switching
        # the tiny producer to V1 to compare with the original PN08 identity.
        run('service-v1-build', [cross, '-std=c++17', '-march=rv32ima', '-mabi=ilp32',
            '-O2', '-flto', '-Wall', '-Wextra', '-Werror', '-DXINYI_BATTLE_R17=0',
            '-iquote', src, '-c', native + '/service.cpp', '-o', native + '/service-v1.o'])
        run('fresh-core-v1-link', [*make_args, 'EXTRALDFLAGS=' + native + '/service-v1.o',
            '--eval=.PHONY: force_producer_relink', '--eval=pikafish: force_producer_relink', 'pikafish'],
            180, env={'SOURCE_DATE_EPOCH': str(epoch)})
        (out / 'xinyi-engine-v1.debug').write_bytes((prepared / 'src/pikafish').read_bytes())
        run('strip-v1', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
            '-o', native + '/xinyi-engine-v1', native + '/xinyi-engine-v1.debug'], 30)
        v2 = (out / 'xinyi-engine-v2').read_bytes()
        v1 = (out / 'xinyi-engine-v1').read_bytes()
        (out / 'xinyi-engine-v2.gz').write_bytes(gzip.compress(v2, mtime=0))
        from verify_xinyi_elf import inspect
        identity = inspect(out / 'xinyi-engine-v2')
        assert identity['allocated'] == inspect(out / 'xinyi-engine-v2.debug')['allocated']
        run('compiler', [cross, '--version'], 30)
        assert (ROOT / 'linux/xinyi_board/engine_service.cpp').read_bytes() == service
        frozen = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:?fresh absolute output directory}
test ! -e "$out"
cd "$root"
sha256sum -c SOURCE_SHA256SUMS.txt
mkdir -p "$out"
cp -a prepared "$out/prepared"
test -z "$(find "$out/prepared" -name '*.o' -print)"
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
export SOURCE_DATE_EPOCH=1792972800
"$cross" -std=c++17 -march=rv32ima -mabi=ilp32 -O2 -flto -Wall -Wextra -Werror -DXINYI_BATTLE_R17=1 -iquote "$out/prepared/src" -c "$root/service.cpp" -o "$out/service-v2.o"
flags='-DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_EMBEDDED_GUI'
make -s -C "$out/prepared/src" -j2 ARCH=riscv32 COMP=gcc CXX="$cross" EXTRACXXFLAGS="$flags" EXTRALDFLAGS="$out/service-v2.o" GIT_SHA= GIT_DATE= GIT_DIFFINDEX= COMPILER_DATE=20261026 pikafish
/opt/toolchain/bin/riscv32-linux-musl-strip --strip-all -o "$out/xinyi-engine-v2" "$out/prepared/src/pikafish"
sha256sum "$out/xinyi-engine-v2"
'''
        objects_in_link_order = (out / 'expected-object-list.txt').read_text().split()
        frozen = frozen.replace("flags='", "objects='" + ' '.join(objects_in_link_order) + "'\nflags='", 1).replace('EXTRALDFLAGS="$out/service-v2.o" GIT_SHA=', 'EXTRALDFLAGS="$out/service-v2.o" OBJS="$objects" GIT_SHA=')
        (out / 'build-frozen.sh').write_bytes(frozen.encode('utf-8'))
        source_sums = {**{'prepared/' + n: h for n, h in source_inputs.items()},
                       'service.cpp': SHA(service), 'build-frozen.sh': SHA(frozen.encode())}
        (out / 'SOURCE_SHA256SUMS.txt').write_bytes(''.join(h + '  ' + n + '\n' for n, h in sorted(source_sums.items())).encode('utf-8'))
        # Complete source archive, all bindings, and no generated objects.
        archive = out / 'xinyi-engine-full-source-r18-r01.tar.gz'
        with tarfile.open(archive, 'x:gz') as t:
            for n in sorted(source_inputs):
                t.add(prepared / n, arcname='prepared/' + n, recursive=False)
            for n in ['service.cpp', 'service-original.cpp', 'builder.py', 'build-frozen.sh', 'SOURCE_SHA256SUMS.txt', 'prepared-source-inputs.json', 'pn08-original-source-bindings.sha256']:
                t.add(out / n, arcname=n, recursive=False)
        result.update(status='PN08_ALL123_CORE_SOURCES_CLEAN_FULL_BUILD_V2_PRODUCER_PASS_NOT_BOARD',
            original_core_exact=True, fresh_compiled_objects=objects,
            source_sha256=source_inputs, service_sha256=SHA(service),
            v2=dict(bytes=len(v2), sha256=SHA(v2), gzip_bytes=(out / 'xinyi-engine-v2.gz').stat().st_size,
                    gzip_sha256=SHA((out / 'xinyi-engine-v2.gz').read_bytes())),
            v1=dict(bytes=len(v1), sha256=SHA(v1), original_pn08_sha256='ed2d8ccbb099bfd3d524d550dc9622145de4e9c49f1096db1c446ad59d661b5a',
                    original_pn08_byte_equal=SHA(v1)=='ed2d8ccbb099bfd3d524d550dc9622145de4e9c49f1096db1c446ad59d661b5a'),
            source_archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=SHA(archive.read_bytes())),
            inference_models_or_policy_changed=False, production_hardware_executed=False)
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
