"""Rebuild and check the explicit software overlay without changing frozen P3 inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LAYER = 'linux/picture_new/vision32_layer.c'
OVERLAY = 'linux/picture_new/whole_layer_fast/vision32_layer.c'
BASE_SHA = 'd7ac5d84f12c96f684edac6e7135c6512afb50a01efca7f4077ce48d727ed301'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--assets', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--expected-binary-sha256')
    ap.add_argument('--layer-source', type=Path, default=ROOT/OVERLAY)
    a = ap.parse_args()
    selected = a.layer_source.resolve()
    assert selected.is_relative_to((ROOT/'linux/picture_new').resolve())
    overlay = selected.relative_to(ROOT.resolve()).as_posix()
    out = a.output.resolve()
    workspace = Path('G:/fpga').resolve()
    assert ROOT.resolve().is_relative_to(workspace)
    assert out.is_relative_to((ROOT/'build').resolve()), 'New build must stay in candidate build/'
    assert a.assets.resolve().is_relative_to(workspace), 'Model inputs must resolve inside workspace'
    for name in ['manifest.json', 'timing-assets.tar.gz']:
        assert (a.assets/name).resolve().is_relative_to(workspace), 'Model file resolves outside workspace'
    assert not out.exists(), 'Preserve prior build and test receipts'
    assert sha(ROOT/LAYER) == BASE_SHA, 'Frozen base source differs'
    receipt = json.loads((a.assets/'manifest.json').read_text(encoding='utf-8-sig'))
    assert receipt['synthetic_weights'] is False
    sources = [LAYER, 'linux/picture_new/vision32_backend.c',
               'linux/picture_new/picture_new_bench.c', 'linux/picture_new/picture_new_infer.c',
               'linux/picture_new/upstream/adapter/runtime/xq_native_graph.c',
               'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
               'sw/bootloader/crc32_fast.c', 'sim/picture_new_graph_mock.c',
               'sim/test_picture_new_vision32.c']
    recipes = ['build_picture_timing_bench.py', 'test_picture_spatial_graphs.py',
               'build_picture_new_interface.py']
    sources += ['scripts/'+name for name in recipes]
    for folder in ['linux/picture_new/upstream/adapter/runtime',
                   'linux/picture_new/upstream/linux/vision', 'linux/mac_accel', 'sw/bootloader']:
        sources += [p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*.h')]
    inputs = {n: sha(ROOT/n) for n in sorted(set(sources+[overlay]))}
    assert all((ROOT/n).resolve().is_relative_to(workspace) for n in inputs), 'Source link escapes workspace'
    out.mkdir(parents=True)
    (out/'tmp').mkdir()
    (out/'wsl').mkdir()
    native_base = '/mnt/g'+out.as_posix()[2:]+'/wsl/'
    assert re.fullmatch(r'[A-Za-z0-9_./-]+', native_base), 'Recipes require shell-safe workspace paths'
    for name in ['TEMP', 'TMP', 'TMPDIR']:
        os.environ[name] = str(out/'tmp')
    record = dict(status='BUILDING_NOT_BOARD', frozen_base_sha256=BASE_SHA,
                  selected_overlay=overlay, source_sha256=inputs,
                  asset_manifest_sha256=sha(a.assets/'manifest.json'),
                  workspace_root=str(workspace), native_build_parent=native_base,
                  temporary_directory=str(out/'tmp'), staged_recipe_sha256={},
                  hardware_modified=False, physical_media_written=False, board_tested=False)
    save = lambda: (out/'result.json').write_text(json.dumps(record, indent=2)+'\n')
    save()
    try:
        stage = out/'src'
        for rel in sources:
            dest = stage/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/(overlay if rel == LAYER else rel), dest)
            if rel.startswith('scripts/'):
                text = dest.read_text(encoding='utf-8')
                assert text.count('/var/tmp/') == 1, 'Review changed child recipe before staging'
                assert text.count('export PATH=') == 1
                text = text.replace('/var/tmp/', native_base)
                text = text.replace('export PATH=',
                    f'mkdir -p {native_base}tmp\\nexport TMPDIR={native_base}tmp\\nexport PATH=', 1)
                dest.write_text(text, encoding='utf-8', newline='\n')
                record['staged_recipe_sha256'][rel] = sha(dest)
        save()
        for recipe, folder in zip(recipes, ['bin', 'oracle', 'interface']):
            command = [sys.executable, '-X', 'utf8', str(stage/'scripts'/recipe),
                       '--output', str(out/folder)]
            if folder != 'interface':
                command += ['--assets', str(a.assets.resolve())]
            with (out/(folder+'-owner.log')).open('xb') as log:
                child = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       timeout=400)
            assert child.returncode == 0, folder+' test failed; inspect preserved log'
        binary = out/'bin/picture-new-bench'
        record['binary_sha256'] = sha(binary)
        if a.expected_binary_sha256:
            assert sha(binary) == a.expected_binary_sha256, 'Rebuild differs from deployed candidate'
        assert all(sha(ROOT/n) == h for n, h in inputs.items()), 'Source changed during build'
        record['checks_sha256'] = {name: sha(out/name/'result.json')
                                  for name in ['bin', 'oracle', 'interface']}
        record['status'] = 'PICTURE_WHOLE_FAST_REBUILD_ORIGINAL_GRAPHS_AND_HOST_RV32_INTERFACE_PASS_NOT_BOARD'
    except Exception as error:
        record.update(status='FAILED_PRESERVED_NOT_BOARD', error=repr(error))
        raise
    finally:
        save(); print(record['status'])


if __name__ == '__main__':
    main()
