"""Actual battle renderer differential/quiet-write checks; no device access."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess

from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--source', type=Path, default=ROOT)
    ap.add_argument('--targets', default='host,sanitizer,rv32')
    ap.add_argument('--baseline-red', action='store_true')
    ap.add_argument('--audit-proof', type=Path, help='Audit actual compiler dependencies of an existing completed run without repeating pixels')
    ap.add_argument('--rebuild-audit',action='store_true',help='Require every current-source executable to reproduce a prior passed executable exactly')
    ap.add_argument('--voice4-label', action='store_true', help='Only select the isolated voice_4 UI label; no model is read')
    ap.add_argument('--metric-deltas',action='store_true',help='Exact idle metric/message overlays and reverse page commands')
    ap.add_argument('--preview-retry',action='store_true')
    ap.add_argument('--fast-nav',action='store_true')
    ap.add_argument('--spans',action='store_true')
    ap.add_argument('--span-oom',action='store_true')
    ap.add_argument('--linear',action='store_true')
    ap.add_argument('--linear-oom',action='store_true')
    ap.add_argument('--commands',action='store_true')
    ap.add_argument('--load8',action='store_true')
    ap.add_argument('--palette',action='store_true')
    ap.add_argument('--row-nav',action='store_true')
    ap.add_argument('--row-scalar',action='store_true')
    a = ap.parse_args()
    assert not a.row_scalar or (a.row_nav and a.fast_nav)
    assert not a.rebuild_audit or a.audit_proof
    source = workspace_path(a.source)
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    dirs = ['linux/xinyi_board', 'linux/xinyi', 'linux/pikafish', 'linux/pikafish/include',
            'linux/vision', 'linux/voice', 'linux/voice_ctc', 'linux/voice_speech',
            'linux/mac_accel', 'linux/picture_new', 'sw/xiangqi', 'sw/bootloader',
            'artifacts/vision-model-20261020-adapter/runtime']
    sources = ['linux/xinyi_board/battle_r17_test.c', 'linux/xinyi/xinyi_product.c',
               'linux/voice/xqvoice_protocol.c', 'sw/xiangqi/xiangqi_search.c',
               'sw/xiangqi/xiangqi_pikafish_link.c',
               'artifacts/vision-model-20261020-adapter/runtime/xq_sha256.c']
    names = set(sources + ['linux/xinyi/xinyi_fb.c', 'linux/pikafish/xiangqi_fb_gui_1080.c'])
    for directory in dirs:
        names.update(p.relative_to(source).as_posix() for p in (source / directory).rglob('*.h'))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {n: sha(source / n) for n in sorted(names)}
    result = dict(status='FAILED_PRESERVED', hardware_used=False,
                  baseline_red=a.baseline_red, source_root=str(source),
                  voice4_label=a.voice4_label,
                  metric_deltas=a.metric_deltas,
                  preview_retry=a.preview_retry,fast_nav=a.fast_nav,spans=a.spans,span_oom=a.span_oom,
                  linear=a.linear,linear_oom=a.linear_oom,
                  commands=a.commands,
                  load8=a.load8,
                  palette=a.palette,
                  row_nav=a.row_nav,
                  row_scalar=a.row_scalar,
                  production_page_pair_deltas=not a.baseline_red,
                  scalar_oracle_page_templates_disabled=not a.baseline_red,
                  source_sha256=before, checker_sha256=sha(Path(__file__)), runs=[])

    def run(name, args, limit=120, expected_failure=False):
        with (out / (name + '.log')).open('xb') as log:
            p = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                'ulimit -c 0\nexec timeout --kill-after=3 ' + str(limit) + ' ' + shlex.join(args)],
                stdout=log, stderr=subprocess.STDOUT, timeout=limit + 15)
        text = (out / (name + '.log')).read_text(errors='replace')
        assert (p.returncode != 0) if expected_failure else (p.returncode == 0), (name, p.returncode, text[-3000:])
        return text

    def command(target):
        cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
        extra = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
        if target == 'sanitizer':
            extra = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-no-pie']
        if target == 'scalar-oracle':
            extra = ['-DXINYI_SCALAR_GLYPH_ORACLE']
        return [cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wno-misleading-indentation', '-D_POSIX_C_SOURCE=200809L', '-D_DEFAULT_SOURCE',
            '-DXINYI_BATTLE_R17=' + str(int(not a.baseline_red)),
            '-DXINYI_ASR_VOICE4=' + str(int(a.voice4_label)),
            '-DXINYI_GUI_METRIC_DELTAS=' + str(int(a.metric_deltas and target!='scalar-oracle')),
            '-DXINYI_PREVIEW_RETRY_R19=' + str(int(a.preview_retry)),
            '-DXINYI_GUI_FAST_NAV_R21=' + str(int(a.fast_nav and target!='scalar-oracle')),
            '-DXINYI_GUI_SPANS_R21=' + str(int(a.spans and target!='scalar-oracle')),
            '-DXINYI_GUI_LINEAR_R21=' + str(int(a.linear and target!='scalar-oracle')),
            '-DXINYI_GUI_COMMANDS_R21=' + str(int(a.commands and target!='scalar-oracle')),
            '-DXINYI_GUI_LOAD8_R21=' + str(int(a.load8 and target!='scalar-oracle')),
            '-DXINYI_GUI_PALETTE_R21=' + str(int(a.palette and target!='scalar-oracle')),
            '-DXINYI_GUI_ROW_NAV_R22=' + str(int(a.row_nav and target!='scalar-oracle')),
            '-DXINYI_GUI_ROW_SCALAR_R23=' + str(int(a.row_scalar and target!='scalar-oracle')),
            *(['-DXINYI_GAME_SPANS_TEST_OOM=1'] if a.span_oom else []),
            *(['-DXINYI_GAME_LINEAR_TEST_OOM=1'] if a.linear_oom else []),
            '-DXINYI_HOME_R13=1', '-DXINYI_HOME_R15=1', '-DXINYI_CPU_HZ=60000000',
            '-DXINYI_GUI_DOUBLE_BUFFER=1', '-DXINYI_UI_FEEDBACK=1',
            '-DXINYI_COACH_MOVE_AUDIO=1',
            '-DXINYI_GUI_PAGE_DELTAS=' + str(int(not a.baseline_red and target != 'scalar-oracle')),
            '-DXINYI_GUI_PAIR_DELTAS=' + str(int(not a.baseline_red and target != 'scalar-oracle')),
            '-DVIDEO_FB_LINUX_MMAP', '-include', wsl_path(source / 'linux/pikafish/gui1080_config.h'),
            *extra, *['-I' + wsl_path(source / d) for d in dirs],
            *[wsl_path(source / n) for n in sources]]

    def dependencies(target):
        log = run(target + '-dependencies', [*command(target), '-MM'])
        prefix = wsl_path(source) + '/'
        found = set()
        for token in log.replace('\\\n', ' ').split():
            if token.startswith(prefix):
                path = (source / token[len(prefix):]).resolve()
                assert path.is_relative_to(source)
                found.add(path.relative_to(source).as_posix())
        assert set(sources).issubset(found) and 'linux/xinyi/xinyi_fb.c' in found
        return found

    try:
        oracle = None
        prior = None
        if a.audit_proof:
            data = workspace_path(a.audit_proof).read_bytes()
            prior = json.loads(data)
            assert not a.baseline_red and not prior['baseline_red']
            assert prior['voice4_label'] == a.voice4_label and workspace_path(prior['source_root']) == source
            assert prior.get('metric_deltas',False)==a.metric_deltas
            assert prior.get('preview_retry',False)==a.preview_retry
            result['original_proof'] = dict(path=str(workspace_path(a.audit_proof)), sha256=hashlib.sha256(data).hexdigest(),
                                            original_status=prior['status'], original_checker_sha256=prior['checker_sha256'])
        targets = ([r['target'] for r in prior['runs']] if prior else
                   ['host'] if a.baseline_red else [*a.targets.split(','), 'scalar-oracle'])
        compiled = set()
        for target in targets:
            compiled.update(dependencies(target))
        actual_before = {n: sha(source / n) for n in sorted(compiled)}
        if prior:
            for name, h in actual_before.items():
                if not a.rebuild_audit:assert prior['source_sha256'].get(name) == h, ('Compiled input drift', name)
        result['source_sha256'] = actual_before
        result['source_inventory_sha256'] = before
        for target in targets:
            if prior:
                folder = workspace_path(a.audit_proof).parent
                log = (folder / (target + '.log')).read_text(errors='replace')
                (out / (target + '.log')).write_text(log)
                row = next(r for r in prior['runs'] if r['target'] == target)
                assert sha(folder / target / 'test') == row['executable_sha256']
                if a.rebuild_audit:
                    current=out/target;current.mkdir()
                    run(target+'-current-source-build',[*command(target),'-lm','-o',wsl_path(current/'test')])
                    assert sha(current/'test')==row['executable_sha256'],('Current-source executable differs',target)
                    result.setdefault('current_source_exact_rebuilds',[]).append({'target':target,'sha256':sha(current/'test')})
                assert 'R17_HIDDEN_REAL_FRAMEBUFFER_QUIET_PASS_NOT_BOARD' in log
                assert 'R17_BATTLE_THREE_MODES_TWO_BANKS_FULL_PIXELS_GUARDS_PASS' in log
                hashes = [s for s in log.splitlines() if s.startswith('R17_FRAME ')]
                assert len(hashes) == row['full_pixel_hash_records'] == 300
                home_hashes = [s for s in log.splitlines() if s.startswith('R17_HOME_FRAME ')]
                if row.get('home_pixel_hash_records'):
                    assert len(home_hashes) == row['home_pixel_hash_records'] == 10
                    assert 'R17_NEW_HOME_CACHE_DIRECT_RENDER_AND_PAIR_TRANSITIONS_PASS' in log
                    hashes += home_hashes
                metric_hashes=[s for s in log.splitlines() if s.startswith('R19_METRIC_FRAME ')]
                if row.get('metric_pixel_hash_records'):
                    assert len(metric_hashes)==row['metric_pixel_hash_records']
                    hashes+=metric_hashes
                if oracle is None:
                    oracle = hashes
                assert hashes == oracle
                result['runs'].append(row)
                continue
            folder = out / target
            folder.mkdir()
            exe = folder / 'test'
            run(target + '-build', [*command(target), '-lm', '-o', wsl_path(exe)])
            log = run(target, [*(['qemu-riscv32'] if target == 'rv32' else []),
                              wsl_path(exe), wsl_path(folder)], 180, a.baseline_red)
            if a.baseline_red:
                assert 'R17_HIDDEN_REAL_RENDER write=1 signal=11' in log, log[-3000:]
            else:
                assert 'R17_HIDDEN_REAL_FRAMEBUFFER_QUIET_PASS_NOT_BOARD' in log
                assert 'R17_BATTLE_THREE_MODES_TWO_BANKS_FULL_PIXELS_GUARDS_PASS' in log
                hashes = [s for s in log.splitlines() if s.startswith('R17_FRAME ')]
                assert len(hashes) >= 250
                home_hashes = [s for s in log.splitlines() if s.startswith('R17_HOME_FRAME ')]
                assert len(home_hashes) == 10
                assert 'R17_NEW_HOME_CACHE_DIRECT_RENDER_AND_PAIR_TRANSITIONS_PASS' in log
                hashes += home_hashes
                metric_hashes=[s for s in log.splitlines() if s.startswith('R19_METRIC_FRAME ')]
                assert len(metric_hashes)==72
                hashes += metric_hashes
                if oracle is None:
                    oracle = hashes
                assert hashes == oracle, (target, 'full pixels differ')
            result['runs'].append(dict(target=target, expected_hidden_write=a.baseline_red,
                full_pixel_hash_records=0 if a.baseline_red else len(hashes)-82,
                home_pixel_hash_records=0 if a.baseline_red else 10,
                metric_pixel_hash_records=0 if a.baseline_red else 72,
                executable_sha256=sha(exe)))
        assert actual_before == {n: sha(source / n) for n in sorted(compiled)}, 'Compiled source changed during check'
        inventory = prior['source_sha256'] if prior else before
        result['uncompiled_inventory_drift'] = [dict(path=n, original_sha256=h, current_sha256=sha(source / n))
            for n, h in inventory.items() if n not in compiled and sha(source / n) != h]
        result['status'] = ('R16_BASELINE_REAL_HIDDEN_FIELD_RED_REPRODUCED' if a.baseline_red else
                            'R17_BATTLE_COMPILED_SOURCES_PIXELS_QUIET_WRITES_PASS_NOT_BOARD')
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])


if __name__ == '__main__':
    main()
