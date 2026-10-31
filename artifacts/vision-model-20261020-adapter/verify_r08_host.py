"""Build native host variants and compare training RGB565 replay packets exactly.

All inputs/packets/logs stay in build/. The tracked receipt contains counts,
training frame names and timings, never a live capture or its identifiers.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out, models):
    sources = [HERE / 'runtime' / name for name in (
        'xq_native_worker.c', 'xq_native_graph.c', 'xq_native_post.c',
        'xq_native_geometry.c', 'xq_int8_layer.c', 'xq_resident_matrix.c')]
    sources += [HERE / 'geometry_fallback/c_ref/geometry_ref.c']
    sources += [REPO / name for name in (
        'linux/vision/xq_mac_linux.c', 'linux/vision/xq_roi.c', 'linux/vision/xq_grid.c',
        'linux/vision/xq_vision.c', 'sw/xiangqi/xiangqi_search.c',
        'sw/xiangqi/xiangqi_pikafish_link.c', 'sw/bootloader/crc32_fast.c')]
    audit = sources + list((HERE / 'runtime').glob('*.h')) + [
        HERE / 'geometry_fallback/c_ref/geometry_ref.h',
        REPO / 'artifacts/vision-model-20261020/geometry/geometry_reference.c',
        models / 'native_parameters.h', Path(__file__).resolve()]
    before = {p.relative_to(REPO).as_posix(): sha(p) for p in audit}
    (out / 'sources-before.json').write_text(json.dumps(before, indent=2) + '\n')
    base = ['cc', '-O3', '-ffp-contract=off', '-Dxqm_matrix=xqn_resident_matrix', '-std=c11', '-Wall', '-Wextra', '-Werror']
    base += ['-I' + str(p) for p in (models, REPO / 'linux/vision', REPO / 'linux/mac_accel', REPO / 'sw/xiangqi', REPO / 'sw/bootloader')]
    base += list(map(str, sources))
    for name, flags in (('before', ['-DXQ_DISABLE_CANDIDATE_FILTER']), ('after', [])):
        subprocess.run(base + flags + ['-lm', '-o', str(out / name)], check=True, timeout=120)
    # Shared geometry test library calls the identical delivered producer.
    subprocess.run(['cc', '-O2', '-ffp-contract=off', '-shared', '-fPIC', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I' + str(REPO / 'linux/vision'), '-I' + str(REPO / 'sw/xiangqi'),
                    str(HERE / 'runtime/xq_native_geometry.c'), str(HERE / 'runtime/xq_native_post.c'),
                    str(HERE / 'geometry_fallback/c_ref/geometry_ref.c'), str(REPO / 'sw/bootloader/crc32_fast.c'),
                    '-I' + str(REPO / 'sw/bootloader'), '-lm', '-o', str(out / 'geometry.so')], check=True, timeout=120)
    return audit, before


def replay(out, models, first, last):
    rows = []
    for i in range(first, last + 1):
        stem = f'IMG{i:05d}'
        old = REPO / 'build/picture-p21-native/pipeline-135-r02'
        raw = old / (stem + '.rgb565')
        request = old / (stem + '.request')
        assert raw.is_file() and request.is_file()
        row = dict(frame=stem)
        # Alternate ordering to reduce systematic warm-cache/turbo bias.
        for name in (('before', 'after') if i % 2 else ('after', 'before')):
            packet = out / (stem + '.' + name + '.packet')
            start = time.monotonic()
            run = subprocess.run([str(out / name), '--models', str(models), '--cpu-reference',
                                  '--input', str(raw), '--request', str(request), '--output', str(packet)],
                                 text=True, capture_output=True, timeout=120)
            (out / (stem + '.' + name + '.log')).write_text(run.stdout + run.stderr)
            assert packet.is_file(), (stem, name, run.returncode, run.stderr)
            assert run.returncode in (0, 1), (stem, name, run.returncode)
            fields = dict(re.findall(r'(\w+)=(\d+)', run.stdout))
            row[name] = {key: int(fields[key]) for key in ('classifier_batch', 'classifier_ms', 'board_ms', 'detector_ms', 'refine_ms', 'assign_ms', 'total_ms')}
            row[name]['wall_s'] = time.monotonic() - start
        assert (out / (stem + '.before.packet')).read_bytes() == (out / (stem + '.after.packet')).read_bytes(), stem
        row['packet_byte_identical'] = True
        rows.append(row)
        (out / 'progress.json').write_text(json.dumps(rows, indent=2) + '\n')
        if len(rows) % 15 == 0:
            print('R08_NATIVE_REPLAY', len(rows), '/', last - first + 1, flush=True)
    return rows


def geometry_tests(out):
    # A deterministic moved grid drives the real C producer, not a mock.
    class Box(C.Structure):
        _fields_ = [(n, C.c_float) for n in ('x0', 'y0', 'x1', 'y1', 'score')] + [('class_id', C.c_uint)]
    Quad = (C.c_double * 2) * 4
    class Geometry(C.Structure):
        _fields_ = [('corners', Quad), ('token', C.c_uint64), ('frame', C.c_uint32), ('crc', C.c_uint32),
                    ('source', C.c_int), ('kept', C.c_uint), ('p95', C.c_double)]
    class State(C.Structure):
        _fields_ = [('token', C.c_uint64), ('frame', C.c_uint32), ('crc', C.c_uint32),
                    ('failures', C.c_uint), ('active', C.c_uint), ('resolved', C.c_uint),
                    ('has_cached', C.c_uint), ('cached', Geometry)]
    lib = C.CDLL(str(out / 'geometry.so'))
    lib.xng_begin.argtypes = [C.POINTER(State), C.c_uint64, C.c_uint32, C.c_uint32]
    lib.xng_resolve.argtypes = [C.POINTER(State), C.c_void_p, C.c_int, C.POINTER(Box), C.c_uint, C.c_void_p, C.POINTER(Geometry)]
    lib.xng_manual.argtypes = [C.POINTER(State), C.c_uint64, C.c_uint32, C.c_uint32, C.c_void_p, C.POINTER(Geometry)]
    lib.xng_cached.argtypes = [C.POINTER(State), C.POINTER(Geometry)]
    lib.xnp_filter_candidates.argtypes = [C.POINTER(Box), C.POINTER(C.c_uint)]
    lib.xng_read_manual.argtypes = [C.c_char_p, C.c_uint64, C.c_uint32, C.c_uint32, C.c_void_p]
    state = State(); result = Geometry(); cached = Geometry()
    seed = Quad(*[(C.c_double * 2)(x, y) for x, y in ((120, 70), (840, 70), (840, 610), (120, 610))])
    boxes = (Box * 90)(*[Box(116 + r * 80, 66 + f * 67.5, 124 + r * 80, 74 + f * 67.5, .9, 1) for r in range(10) for f in range(9)])
    events = []
    for token in (1, 2, 3):
        assert lib.xng_begin(C.byref(state), token, token, 123) == 1
        event = lib.xng_resolve(C.byref(state), None, 0, boxes, 90, seed, C.byref(result)); events.append(event)
        assert event == (1 if token < 3 else 0)
        if token < 3:
            assert result.source == 0
            assert lib.xng_resolve(C.byref(state), None, 0, boxes, 90, seed, C.byref(result)) == 3
    assert result.source == 2 and result.kept >= 6
    assert lib.xng_cached(C.byref(state), C.byref(cached)) == 1 and cached.source == 4 and cached.token == 3
    assert lib.xng_begin(C.byref(state), 3, 3, 123) == 0
    # A moved board cannot reuse the cached geometry; too few centers -> manual.
    assert lib.xng_begin(C.byref(state), 4, 4, 123) == 1
    assert lib.xng_resolve(C.byref(state), None, 0, boxes, 5, None, C.byref(result)) == 2 and result.source == 0
    for token, frame, crc in ((3, 4, 123), (4, 3, 123), (4, 4, 124)):
        assert lib.xng_manual(C.byref(state), token, frame, crc, seed, C.byref(result)) == 3
    invalid = Quad(*[(C.c_double * 2)(0, 0) for _ in range(4)])
    assert lib.xng_manual(C.byref(state), 4, 4, 123, invalid, C.byref(result)) == 2
    assert lib.xng_manual(C.byref(state), 4, 4, 123, seed, C.byref(result)) == 0 and result.source == 3
    assert lib.xng_begin(C.byref(state), 5, 5, 123) == 1
    assert lib.xng_resolve(C.byref(state), seed, 1, boxes, 90, None, C.byref(result)) == 0
    assert state.failures == 0 and result.source == 1
    boundary = (Box * 5)(*[Box(1, 1, 2, 2, score, i) for i, score in enumerate((.049, .05, .051, 0, 1))])
    n = C.c_uint(5)
    assert lib.xnp_filter_candidates(boundary, C.byref(n)) == 1 and n.value == 3
    assert [boundary[i].class_id for i in range(n.value)] == [1, 2, 4]
    manual_path = out / 'manual-synthetic.txt'
    text = 'XQ_MANUAL_CORNERS_V1 5 5 123\n120 70\n840 70\n840 610\n120 610\n'
    manual_path.write_text(text)
    assert lib.xng_read_manual(str(manual_path).encode(), 5, 5, 0x123, seed) == 1
    assert lib.xng_read_manual(str(manual_path).encode(), 5, 5, 0x124, seed) == 0
    manual_path.write_text(text + 'trailing')
    assert lib.xng_read_manual(str(manual_path).encode(), 5, 5, 0x123, seed) == 0
    manual_path.unlink()
    # Inject board-model failures against actual stored training replay boxes.
    # This verifies dispatch with real detector data, independently of fit
    # success: after failure 3, a failed fit must ask for manual, never cache.
    replay_events = []
    for stem in ('IMG00908', 'IMG00917', 'IMG00926'):
        reference = json.loads((REPO / 'build/picture-p21-native/pipeline-135-r02' / (stem + '.reference.json')).read_text())
        replay_boxes = (Box * len(reference['pieces']))(*[Box(*p['bbox_original'], p['score'], p['class_id']) for p in reference['pieces']])
        replay_seed = Quad(*[(C.c_double * 2)(*q) for q in reference['geometry']['corners_image_TL_TR_BR_BL']])
        replay_state = State(); dispatch = []
        for token in (1, 2, 3):
            assert lib.xng_begin(C.byref(replay_state), token, token, 123) == 1
            event = lib.xng_resolve(C.byref(replay_state), None, 0, replay_boxes, len(replay_boxes), replay_seed, C.byref(result))
            assert event == 1 if token < 3 else event in (0, 2)
            dispatch.append(event)
        replay_events.append(dict(frame=stem, events=dispatch, source=result.source))
    return dict(status='PASS', producer='unchanged R1 geom_piece_fit binary64 C',
                events=events, real_training_replay_failure_injection=replay_events, same_capture_cannot_increment_failures=True,
                stale_manual_token_frame_crc_rejected=True, degenerate_manual_rejected=True,
                cached_diagnostic_only=True, board_success_resets_failures=True,
                candidate_filter_preserves_threshold_and_order=True, board_validation='pending')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--range', nargs=2, type=int, default=(908, 1042))
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    models = args.models.resolve()
    sources, before = build(out, models)
    geometry = geometry_tests(out)
    print('R08_GEOMETRY_HOST_PASS', flush=True)
    rows = replay(out, models, *args.range)
    after = {p.relative_to(REPO).as_posix(): sha(p) for p in sources}
    assert before == after, 'source changed during native build/replay'
    report = dict(status='PASS', scope='PC native training RGB565 replay; no hardware/accuracy/performance acceptance',
                  hardware_used=False, production_ready=False, geometry=geometry, frames=rows,
                  frame_count=len(rows), packet_byte_identical=all(r['packet_byte_identical'] for r in rows),
                  sources=before, source_stable_during_run=True,
                  executables={name: sha(out / name) for name in ('before', 'after', 'geometry.so')},
                  models={p.name: sha(p) for p in models.glob('*.xqm')})
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2) + '\n')
    print('R08_HOST_RUNTIME_PASS', len(rows), flush=True)


if __name__ == '__main__':
    main()
