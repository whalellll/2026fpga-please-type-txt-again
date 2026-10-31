"""Package the offline CPU60 r16 GUI and reproduce both flags from ZIP sources.

Only GUI/source/synthetic-render evidence is exported. No board, media, model,
recognition frame/result, boot entry or installer is accessed or included.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
import zipfile

from picture_workspace import ROOT, workspace_path, wsl_path
from verify_xinyi_elf import inspect

PN15_GUI = 'c7f065985be253447028b6c4bf8a02aa27b86b43c3c6b9e5ce7643239c7dcf51'
OPTIONS = dict(gui_double_buffer='1', gui_ram_render='0', ui_feedback='1',
               coach_move_audio='1', home_r13='1', home_r15='1',
               gui_page_deltas='1', gui_pair_deltas='1', ui_nav_diag='0')
ENV = ['XINYI_CPU_HZ=60000000', 'XINYI_HOME_R13=1', 'XINYI_HOME_R15=1',
       'XINYI_GUI_DOUBLE_BUFFER=1', 'XINYI_GUI_RAM_RENDER=0',
       'XINYI_GUI_PAGE_DELTAS=1', 'XINYI_UI_FEEDBACK=1',
       'XINYI_COACH_MOVE_AUDIO=1', 'XINYI_UI_NAV_DIAG=0']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['output', 'gui-build', 'render-proof', 'direct-proof',
                 'oom-proof', 'cpu-proof', 'cpu-harness']:
        ap.add_argument('--' + name, required=True, type=Path)
    a = ap.parse_args()
    logical = a.output.absolute()
    assert logical.is_relative_to(ROOT / 'build')
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    sources, payload, programs = {}, {}, {}
    result = dict(status='FAILED_PRESERVED', hardware_used=False, installed=False)

    def bind(name, expected=None):
        name = name.replace('\\', '/')
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        data = (ROOT / name).read_bytes()
        h = sha(data)
        assert expected is None or h == expected, name
        assert name not in sources or sources[name] == h, name
        sources[name] = h

    def run(name, args, limit=120):
        with (out / (name + '.log')).open('xb') as log:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 ' + str(limit) + ' ' + shlex.join(args)],
                stdout=log, stderr=subprocess.STDOUT, timeout=limit + 15)
        assert p.returncode == 0, (name, (out / (name + '.log')).read_text(errors='replace')[-2400:])

    def hashes(path):
        return [s for s in path.read_text().splitlines() if s.startswith(('R13_FRAME', 'R13_GLYPH'))]

    try:
        proofs = {}
        for name in ['render', 'direct', 'oom', 'cpu']:
            path = workspace_path(getattr(a, name + '_proof'))
            data = path.read_bytes()
            proof = json.loads(data)
            assert 'PASS_NOT_BOARD' in proof['status'] or proof['status'] == 'CPU_ONLY_PAIR_CACHE_PIXELS_EQUAL_NOT_BOARD'
            for n, h in proof['source_sha256'].items():
                bind(n, h)
            proofs[name] = (path, proof)
            payload['evidence/' + name + '.json'] = data
        assert {r['target'] for r in proofs['render'][1]['runs']} == {'host', 'rv32', 'sanitizer', 'scalar-oracle'}
        assert proofs['render'][1]['pair_deltas'] and proofs['oom'][1]['pair_cache_oom']
        assert not proofs['direct'][1]['pair_deltas'] and not proofs['direct'][1]['page_deltas']
        oracle = hashes(proofs['direct'][0].parent / 'host.log')
        assert len(oracle) == 84
        for name in ['render', 'direct', 'oom']:
            path, proof = proofs[name]
            for row in proof['runs']:
                log = path.parent / (row['target'] + '.log')
                assert hashes(log) == oracle, (name, row['target'])
                payload['evidence/' + name + '-' + row['target'] + '.log'] = log.read_bytes()
        assert proofs['cpu'][1]['renders_per_sample'] == 64
        assert proofs['cpu'][1]['alternating_pairs'] == 4
        harness = workspace_path(a.cpu_harness).read_bytes()
        assert sha(harness) == proofs['cpu'][1]['harness_sha256']
        payload['support/pair-cache-cpu-bench.c'] = harness
        for target in ['host', 'rv32']:
            payload['evidence/cpu-' + target + '.log'] = (proofs['cpu'][0].parent / (target + '-run.log')).read_bytes()

        build = workspace_path(a.gui_build)
        before = (build / 'source-before.sha256').read_bytes()
        assert before == (build / 'source-after.sha256').read_bytes()
        prefix = wsl_path(ROOT) + '/'
        for line in before.decode().splitlines():
            h, name = line.split(None, 1)
            assert name.startswith(prefix)
            bind(name[len(prefix):], h)
        actual_options = dict(line.split('=', 1) for line in (build / 'gui-config.txt').read_text().splitlines())
        assert actual_options == OPTIONS
        assert (build / 'cpu-hz.txt').read_text().strip() == '60000000'
        candidate = (build / 'gui').read_bytes()
        assert b'XINYI_NAV_DIAG_' not in candidate
        old, new = inspect(build / 'xinyi-one'), inspect(build / 'gui')
        assert old['allocated'] == new['allocated'] and old['entry'] == new['entry']
        programs['r16'] = dict(bytes=len(candidate), sha256=sha(candidate), pair_deltas=1)
        payload['software/gui-r16.rv32.elf'] = candidate
        for n in ['scripts/prepare_xinyi_pair_cache.py', 'scripts/picture_workspace.py',
                  'scripts/verify_xinyi_elf.py', 'linux/xinyi/fonts/OFL.txt',
                  'linux/xinyi/fonts/source.json', 'linux/xinyi/fonts/glyphs.json',
                  'linux/xinyi/fonts/home-art-r15.json', 'linux/xinyi/fonts/home-background.json']:
            bind(n)
        payload['evidence/compiler.txt'] = (build / 'compiler.txt').read_bytes()
        payload['evidence/gui-config.txt'] = (build / 'gui-config.txt').read_bytes()
        payload['evidence/gui-original-inputs.sha256'] = before

        # Rebuild the default-off program once, and compare with the immutable
        # last PN15 production identity, independently of the new pixel tests.
        # The builder checks the lexical repo/build boundary. Keep that path
        # through the private junction rather than passing its resolved E path.
        off_logical = (logical / 'build/flag0').as_posix()
        off_build = '/mnt/' + off_logical[0].lower() + off_logical[2:]
        run('flag0-build', ['env', *ENV, 'XINYI_GUI_PAIR_DELTAS=0', 'sh',
                           wsl_path(ROOT / 'linux/xinyi_board/build.sh'), off_build])
        off = out / 'gui-pn15.rv32.elf'
        run('flag0-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
                            '-o', wsl_path(off), off_build + '/xinyi-one'], 30)
        baseline = off.read_bytes()
        assert sha(baseline) == PN15_GUI, 'Default-off ELF differs from PN15'
        programs['pn15'] = dict(bytes=len(baseline), sha256=sha(baseline), pair_deltas=0)
        payload['software/gui-pn15.rv32.elf'] = baseline
        for name, h in sources.items():
            data = (ROOT / name).read_bytes()
            assert sha(data) == h, name
            payload['source/' + name] = data
        payload['README.md'] = '''# r16 offline GUI candidate / CPU60 E42

Not installed or board-tested. The 1000 ms navigation target is still pending.
PN15 full SD remains the last physically tested package. This ZIP is a GUI and
source candidate, not a replacement SD image or a bootable xqboot file set.
Use with the existing PN15 matching speech helper / PCM / runtime resources.
No models, photos, raw frames, recognition packets, kernel or installer here.

XINYI_GUI_PAIR_DELTAS defaults to 0. Flag 0 exactly reproduces the PN15 GUI;
flag 1 builds ordinary-RAM commands once before the first rendered frame, for
home -> CoreMark/camera instruction pages only. Command data is 828332 bytes;
allocator overhead/RSS is unmeasured. Failed shrink retains the bounded initial
allocation. Startup and board latency are unmeasured.
Allocation failure uses the old RLE merge without retrying allocations. Other
transitions retain existing rendering.
Hidden photo/voice state no longer invalidates canonical home/menu pages;
displayed errors, measured values, preview/drain/cancel/job states keep their
actual rendering. Recognition, audio and recommendation algorithms stay as PN15.

Synthetic complete pixels: 84 records including both banks, feedback, measured
values, errors, preview draining and post-recognition state. Host/RV32/QEMU CPU
microbenchmarks use ordinary RAM only; their ratios cannot establish board,
DDR/MMIO, HDMI or physical click latency. Native game entry is not a 1 s claim.

Rebuild from source/ with /opt/toolchain/bin/riscv32-linux-musl-gcc:
```sh
env XINYI_CPU_HZ=60000000 XINYI_HOME_R13=1 XINYI_HOME_R15=1 XINYI_GUI_DOUBLE_BUFFER=1 XINYI_GUI_RAM_RENDER=0 XINYI_GUI_PAGE_DELTAS=1 XINYI_GUI_PAIR_DELTAS=1 XINYI_UI_FEEDBACK=1 XINYI_COACH_MOVE_AUDIO=1 XINYI_UI_NAV_DIAG=0 sh linux/xinyi_board/build.sh "$PWD/build/gui"
/opt/toolchain/bin/riscv32-linux-musl-strip --strip-all -o gui.elf build/gui/xinyi-one
```
Set XINYI_GUI_PAIR_DELTAS=0 for the PN15 baseline. No model/board is needed to build.
'''.encode()
        manifest = dict(schema='xinyi-pair-cache-r16/1', hardware_used=False,
                        installed=False, physical_1000ms_pass=False, programs=programs,
                        sources_sha256=sources,
                        members={n: dict(bytes=len(b), sha256=sha(b)) for n, b in payload.items()})
        payload['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
        archive = out / 'xinyi-gui-offline-r16-r01.zip'
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for n, b in sorted(payload.items()):
                z.writestr(n, b)
        exported = out / 'exported'
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and set(z.namelist()) == set(payload)
            for n, row in manifest['members'].items():
                assert len(z.read(n)) == row['bytes'] and sha(z.read(n)) == row['sha256']
            z.extractall(exported)
        native = wsl_path(exported / 'source')
        for flag, data in [(0, baseline), (1, candidate)]:
            destination = native + '/build/flag' + str(flag)
            name = 'zip-flag' + str(flag)
            run(name + '-build', ['env', *ENV, 'XINYI_GUI_PAIR_DELTAS=' + str(flag),
                                  'sh', native + '/linux/xinyi_board/build.sh', destination])
            elf = out / (name + '.elf')
            run(name + '-strip', ['/opt/toolchain/bin/riscv32-linux-musl-strip', '--strip-all',
                                  '-o', wsl_path(elf), destination + '/xinyi-one'], 30)
            assert elf.read_bytes() == data, name
        assert all(sha((ROOT / n).read_bytes()) == h for n, h in sources.items())
        result.update(status='R16_GUI_FLAG0_PN15_AND_ZIP_BOTH_FLAGS_EXACT_REBUILDS_PASS_NOT_BOARD',
                      programs=programs, source_sha256=sources, full_pixel_records=84,
                      archive=dict(path=str(archive), bytes=archive.stat().st_size,
                                   sha256=sha(archive.read_bytes()), members=len(payload),
                                   sha_crc_pass=True, both_flags_zip_rebuild_byte_equal=True))
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
