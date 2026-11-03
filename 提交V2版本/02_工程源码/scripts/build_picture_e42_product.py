"""Rebuild the e42 GUI and matching strict NNUE service, off-board only."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import uuid
from picture_workspace import ROOT, workspace_path, wsl_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--prepared-source', required=True, help='Prepared engine src under /mnt/g/fpga')
    ap.add_argument('--distribution',default='pikafish-verify')
    a = ap.parse_args()
    logical = a.output.absolute()
    assert logical.is_relative_to(ROOT / 'build')
    out = workspace_path(logical)
    assert not out.exists()
    out.mkdir(parents=True)
    paths = ['linux/xinyi_board/build_engine_service.sh', 'linux/xinyi_board/engine_service.cpp',
             'linux/xinyi_board/build.sh', 'linux/pikafish/pikafish_mac_runtime.cpp',
             'linux/pikafish/pikafish_mac_runtime.h', 'linux/pikafish/pikafish_mac_backend_policy.h',
             'linux/mac_accel/pango_mac_uapi.h', 'scripts/build_picture_e42_product.py']
    before = {name: sha(ROOT / name) for name in paths}
    source = a.prepared_source
    assert source.startswith('/mnt/g/fpga/') and source.endswith('/src') and '/..' not in source
    private = wsl_path(out/'private-source')
    commands = []

    def output_path(path):
        # Builders enforce their lexical repo/build boundary. Keep the owned
        # junction path in argv; workspace_path above checks its final target.
        value = path.absolute().as_posix()
        assert path.absolute().is_relative_to(ROOT / 'build')
        return '/mnt/' + value[0].lower() + value[2:]

    def run(name, command, seconds=600):
        commands.append({'name': name, 'argv': command, 'timeout_seconds': seconds})
        with (out / (name + '.log')).open('xb') as log:
            r = subprocess.run(['wsl.exe', '-d', a.distribution, '--', 'timeout', '--kill-after=5',
                                str(seconds), *command], stdout=log, stderr=subprocess.STDOUT, timeout=seconds+20)
        assert r.returncode == 0, (name, (out / (name + '.log')).read_text(errors='replace')[-3000:])

    run('gui', ['sh', wsl_path(ROOT / 'linux/xinyi_board/build.sh'), output_path(logical / 'product')], 180)
    run('gui-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '-o',
                     wsl_path(logical / 'product/xinyi-one-stripped'), wsl_path(logical / 'product/xinyi-one')], 30)
    run('source-copy', ['cp', '-a', source[:-4], private], 60)
    for rel in paths[3:7]:
        run('port-' + Path(rel).name, ['cp', wsl_path(ROOT / rel), private + '/src/' + Path(rel).name], 10)
    for name in ['pikafish_stagea_accel.cpp','pikafish_stagea_accel.h','pikafish_feature_updates.h']:
        run('port-'+name,['cp',wsl_path(ROOT/'linux/pikafish'/name),private+'/src/'+name],10)
    run('feature-updates',['python3',wsl_path(ROOT/'linux/pikafish/apply_feature_updates.py'),private,wsl_path(out/'feature-updates-integration.json')],30)
    run('clean-private-objects', ['make', '-s', '-C', private + '/src', 'clean'], 30)
    # Keep the already reviewed patches to main/network/affine objects, while
    # recompiling every object with the new runtime and matching UAPI.
    # The service builder checks that a prepared main.o exists. Make compiles
    # it from the retained source before the full engine service build.
    cross = '/opt/toolchain/bin/riscv32-linux-musl-g++'
    flags = '-DPIKAFISH_PFF1_DIRECT_VIEW -DPIKAFISH_EMBEDDED_SINGLE_THREAD -DPIKAFISH_STAGEA_ACCEL -DPIKAFISH_STAGEB_ACCEL -DPIKAFISH_EMBEDDED_GUI'
    run('prepared-main', ['make', '-s', '-C', private + '/src', '-j2', 'ARCH=riscv32', 'COMP=gcc',
                          'CXX=' + cross, 'EXTRACXXFLAGS=' + flags, 'main.o'], 180)
    run('engine', ['sh', wsl_path(ROOT / 'linux/xinyi_board/build_engine_service.sh'),
                   wsl_path(ROOT), private + '/src', output_path(logical / 'engine')], 600)
    from prepare_xinyi_cpu60_kit import elf32
    for file in ['product/xinyi-one-stripped', 'engine/xinyi-engine']:
        elf32((out / file).read_bytes(), file)
    from verify_xinyi_elf import inspect
    assert inspect(out / 'product/xinyi-one-stripped')['allocated'] == inspect(out / 'product/xinyi-one')['allocated']
    assert all(sha(ROOT / name) == value for name, value in before.items())
    result = {'status': 'E42_GUI_STRICT_NNUE_FULL_REBUILD_PASS_NOT_BOARD', 'source_sha256': before,
              'source_stable': True, 'prepared_source': source, 'retained_private_source': private,
              'private_source_copy_preserves_p3_objects': True, 'commands': commands,
              'outputs_sha256': {p: sha(out / p) for p in ['product/xinyi-one-stripped', 'engine/xinyi-engine']},
              'hardware_used': False, 'production_ready': False}
    (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'])


if __name__ == '__main__':
    main()
