"""Collect current-board evidence for the user's decision; never declare delivery."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
kv = lambda s: dict(re.findall(r'(\w+)=([^\s]*)', s))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    out = a.output.resolve()
    assert out.is_relative_to((ROOT/'build').resolve())
    assert not out.exists()
    evidence = {}

    def capture(path, failed=False):
        path = ROOT/path
        receipt = path.with_suffix('.result.json')
        d = read(receipt)
        if not failed:
            assert d['status'] in ['BOARD_COMMAND_SPEC_PASS',
                                  'PRODUCTION_SD_BOOT_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING']
        assert d['uart_sha256'] == sha(path), str(path)
        for p in [path, receipt]:
            evidence[p.relative_to(ROOT).as_posix()] = sha(p)
        return path.read_text(encoding='utf-8', errors='replace').replace('\r', '')

    run = 'build/opt60-p3-fast-final-checks-01/'
    capture('build/opt60-p3-picture-fast-boot-01.uart')
    capture(run+'sanity.uart')
    picture = capture('build/opt60-p3-picture-fast-image-ab-01.uart')
    groups = {}
    current = None
    for line in picture.splitlines():
        m = re.fullmatch(r'IMAGE_AB_(control|candidate)-([ab])_(classifier|board)', line)
        if m:
            current = m[1]
        if not line.startswith('PICTURE_TIMING '):
            continue
        d = kv(line)
        key = d['model']+('-batch32' if d['batch'] == '32' else '')
        side = current if key in ['classifier', 'board'] else 'candidate'
        assert d['backend'] == 'vision32' and d['no_fallback'] == '1'
        assert int(d['jobs']) > 0 and int(d['cycles']) > 0
        groups.setdefault(key, {}).setdefault(side, []).append(d)
    images = {}
    for key, crc, count in [('classifier', '805678c7', 10), ('board', 'd830c1cd', 2),
                            ('classifier-batch32', '5c18a3d4', 1), ('detector', '97265de4', 1)]:
        g = groups[key]
        for side, rows in g.items():
            assert len(rows) == count and all(r['output_crc'] == crc for r in rows)
        summary = {}
        for side, rows in g.items():
            summary[side] = {k: statistics.mean(int(r[k]) for r in rows)
                             for k in ['infer_us', 'hardware_us', 'model_load_us', 'input_open_us', 'jobs']}
            summary[side]['load_input_and_infer_us'] = sum(summary[side][k]
                for k in ['infer_us', 'model_load_us', 'input_open_us'])
            summary[side]['samples'] = len(rows)
        images[key] = dict(output_crc=crc, results=summary)
        if 'control' in summary:
            images[key]['infer_change_percent'] = (summary['candidate']['infer_us']/summary['control']['infer_us']-1)*100

    voice = capture(run+'voice.uart')
    chunks = re.split(r'(?m)^VOICE_AB_(old|new|cpu)_(500|1000|2000)_([012])\n', voice)
    assert len(chunks) == 85
    voice_samples = []
    for i in range(1, len(chunks), 4):
        side, ms, repeat, t = chunks[i:i+4]
        c = re.findall(r'(?m)^backend=(?:mac|cpu) .*$', t)
        v = re.findall(r'(?m)^VOICE_STREAM_TIMING .*$', t)
        assert len(c) == len(v) == 1
        c, v = kv(c[0]), kv(v[0])
        assert v['streamed'] == v['paced'] == '1'
        assert c['backend'] == ('cpu' if side == 'cpu' else 'mac')
        assert (int(c['mac_jobs']) == 0) == (side == 'cpu')
        if side == 'new':
            assert 'quant_available=1' in t
        voice_samples.append(dict(mode=side, clip_ms=int(ms), repeat=int(repeat), cnn=c, timing=v))
    voices = {}
    for ms in [500, 1000, 2000]:
        rows = [x for x in voice_samples if x['clip_ms'] == ms]
        assert len({(x['cnn']['text'], x['cnn']['frames'], x['timing']['feature_crc'],
                     x['timing']['feature_frames']) for x in rows}) == 1
        groups = {}
        for mode in ['old', 'new', 'cpu']:
            values = [x for x in rows if x['mode'] == mode]
            if not values:
                continue
            assert len(values) == 3
            groups[mode] = {key: statistics.mean(int(x['cnn'][key]) for x in values)
                           for key in ['cnn_us', 'decode_us', 'total_us', 'mac_cycles']}
            groups[mode].update({key: statistics.mean(int(x['timing'][key]) for x in values)
                                for key in ['feature_tail_us', 'endpoint_to_result_us']})
            groups[mode]['hardware_us'] = groups[mode]['mac_cycles']/49.5
        voices[str(ms)] = dict(results=groups, exact_feature_crc_and_text=True,
                              feature_crc=rows[0]['timing']['feature_crc'])

    nnue_text = capture(run+'nnue.uart')
    chunks = re.split(r'(?m)^NNUE_AB_(cpu|pipeline|batch)\n', nnue_text)
    assert len(chunks) == 7
    nnue = {}
    for mode, t in zip(chunks[1::2], chunks[2::2]):
        assert t.count('NNUE_LATENCY_CORRECTNESS_PASS') == 1
        assert not re.search(r'(?m)^NNUE_LATENCY_FAIL', t)
        phases = {}
        for phase in ['cold', 'warm']:
            lines = re.findall(r'(?m)^NNUE_LATENCY phase='+phase+r' .*$', t)
            assert len(lines) == 1
            values = kv(lines[0]); assert values['samples'] == '40'
            phases[phase] = {k: int(v) for k, v in values.items() if k != 'phase'}
            if mode == 'batch':
                line = re.findall(r'(?m)^NNUE_BATCH_BREAKDOWN phase='+phase+r' .*$', t)
                assert len(line) == 1
                b = kv(line[0]); assert b['calls'] == '40' and b['updates'] == '160'
                phases[phase]['batch_hardware_us'] = int(b['cycles'])/40/49.5
                phases[phase]['batch_host_us'] = int(b['host_mean_us'])
        nnue[mode] = phases
    nnue['warm_speedup_cpu_over_batch'] = nnue['cpu']['warm']['mean_us']/nnue['batch']['warm']['mean_us']

    mixed = capture('build/opt60-p3-fast-concurrent-02/board.uart', failed=True)
    assert len(re.findall(r'(?m)^NNUE_LATENCY_CORRECTNESS_PASS$', mixed)) == 2
    assert 'output_crc=5c18a3d4 no_fallback=1' in mixed
    assert 'feature_crc=b438913c' in mixed
    overflow = re.findall(r'capture invalid: overflows=(\d+); no WAV published', mixed)
    assert len(overflow) == 1
    mix = dict(pass_all=False, audio_overflows=int(overflow[0]), audio_wav_published=False,
               nnue_integer_correctness_processes=2, vision_crc_pass=True, voice_feature_crc_pass=True,
               nnue_warm_rows=[kv(x) for x in re.findall(r'(?m)^NNUE_LATENCY phase=warm .*$', mixed)],
               voice_rows=[kv(x) for x in re.findall(r'(?m)^VOICE_STREAM_TIMING .*$', mixed)],
               note='Heavy stress: two NNUE processes, batch32 vision, voice2s and5s capture. Late interactive-shell wait returned127 for already-notified voice/audio jobs; do not reinterpret those as recorded child exit codes. The audio overflow failure is explicit in its own log.')

    idle = capture('build/opt60-p3-fast-apps-01/idle-audio.uart')
    assert 'PCM_TRANSPORT_PASS samples=80000' in idle and 'overflows=0' in idle
    worker = capture('build/opt60-p3-fast-apps-01/worker.uart')
    worker_rows = {}
    for req, data in re.findall(r'(?m)^XQW1 RESULT ([12]) 0 (.*)$', worker):
        values = kv(data)
        assert values['model_loads'] == values['model_checks'] == values['mac_opens'] == '1'
        worker_rows[req] = values
    assert set(worker_rows) == {'1', '2'} and 'XQW1 BYE' in worker
    search = capture('build/opt60-p3-fast-apps-01/search-hw.uart')
    search_rows = [kv(x) for x in re.findall(r'(?m)^PIKAFISH_PIPELINE_SEARCH .*$', search)]
    assert len(search_rows) == 3
    gui = capture('build/opt60-p3-fast-apps-01/gui.uart')
    move = re.findall(r'(?m)^XQ LINUX INJECT MOVE_PASS .*$', gui)
    assert len(move) == 1
    visual_path = ROOT/'build/opt60-p3-fast-apps-01/visual-user.json'
    visual = read(visual_path)
    assert visual['status'] == 'USER_CONFIRMED_CURRENT_GUI_DISPLAY_NORMAL'
    assert visual['gui_uart_sha256'] == sha(ROOT/'build/opt60-p3-fast-apps-01/gui.uart')
    evidence[visual_path.relative_to(ROOT).as_posix()] = sha(visual_path)

    core_path = ROOT/'build/opt60-coremark-abab-04/result.json'
    core = read(core_path)
    assert core['status'] == 'OPT60_COREMARK_ABAB_CRC_TIME_ALL_SAMPLES_PER_MHZ_PASS_LINUX_PENDING'
    evidence[core_path.relative_to(ROOT).as_posix()] = sha(core_path)
    for batch in core['batches']:
        assert batch['status'] == 'PASS'
        p = Path(batch['coremark_result'])
        assert sha(p) == batch['coremark_result_sha256']
        evidence[p.relative_to(ROOT).as_posix()] = sha(p)

    result = dict(status='CURRENT_BOARD_ASSESSMENT_COMPLETE_MIXED_AUDIO_FAIL_USER_ACCEPTANCE_PENDING',
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  bitstream_sha256='6565ad378524f3e2a34f6cdba6fcc46b2f928eb3677c0fe80971e05e8ec2ebdd',
                  sd_manifest_sha256=sha(ROOT/'build/opt60-p3-picture-fast-bound-01/manifest.json'),
                  cpu_hz=60000000, sys_hz=49500000, display='1080p30',
                  picture=images, voice=voices, nnue=nnue, mixed=mix,
                  idle_capture_pass=True, resident_voice_requests=worker_rows,
                  search_hardware=search_rows, gui_move=kv(move[0]), gui_process_left_running=True,
                  gui_visual_user_confirmed=True,
                  coremark=core['comparisons'], per_mhz_decrease=core['coremark_per_mhz_absolute_decrease'],
                  known_issues=['Heavy concurrent audio overflow177/no WAV; combined test failed',
                                'Voice10ms and image30fps and NNUE10ms targets not met',
                                'Original CPU search acceptance helper exits134 after all3 rows; fixed helper remains uninstalled',
                                'Real utterance/VAD latency, recognition dataset accuracy and GUI voice integration not accepted by these synthetic-input tests'],
                  cpu_voice_reference='CPU path computes raw and packed dots for internal verification; not an optimized CPU-only baseline',
                  timing_scope='Image inference includes CPU graph and accelerator work; loading separately reported; camera/preprocess/geometry/NMS/FEN/display not included. Voice stream endpoint is paced WAV last sample to pre-print result, not measured real-microphone VAD endpoint. Worker W is complete file-to-result, not paced streaming. NNUE is full Network::evaluate, not full search.',
                  evidence_sha256=evidence, user_acceptance_pending=True, main_pushed=False, formal_delivery=False)
    out.mkdir(parents=True)
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], voice1s=voices['1000'], nnue=nnue,
                          picture=images, mixed_audio_overflows=mix['audio_overflows']), ensure_ascii=False))


if __name__ == '__main__':
    main()
