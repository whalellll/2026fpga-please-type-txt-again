"""Verify published CPU60 bytes and evidence without asserting formal delivery."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify(root=ROOT):
    m = read(root/'artifacts/INTEGRATED_OPT60_MAIN.json')
    assert m['status'] == 'USER_AUTHORIZED_MAIN_PUBLICATION_WITH_RECORDED_LIMITATIONS'
    for flag in ('mixed_audio_pass', 'formal_delivery', 'zip_created',
                 'voice_preview_persisted', 'automatic_voice_moves_included',
                 'image_interactive_gui_included'):
        assert m[flag] is False, flag
    assert m['mixed_audio_overflows'] == 177
    for name, expected in m['files_sha256'].items():
        assert sha(root/name) == expected, name
    snap = read(root/'artifacts/build_snapshot.json')
    assert snap['run_id'] == m['run_id']
    for name, expected in snap['inputs'].items():
        assert sha(root/name) == expected, 'Frozen input: '+name
    assert len(snap['inputs']) == 495
    evidence = root/Path(m['portable_board_evidence']).parent
    sources = read(evidence/'source-map.json')['files']
    for name, entry in sources.items():
        p = evidence/name
        assert sha(p) == entry['sha256'], name
        if 'decompressed_sha256' in entry:
            assert hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest() == entry['decompressed_sha256']
    assessment = read(evidence/'opt60-board-assessment-02/result.json')
    assert assessment['bitstream_sha256'] == m['bitstream_sha256'] == sha(root/'artifacts/soc_top.sbit')
    assert assessment['sd_manifest_sha256'] == m['sd_source_manifest_sha256'] == sha(root/'linux/boot/INTEGRATED_OPT60_SD.json')
    assert assessment['mixed']['pass_all'] is False
    assert assessment['mixed']['audio_overflows'] == 177
    assert assessment['mixed']['audio_wav_published'] is False
    binding = read(evidence/'opt60-board-assessment-02/report-binding.json')
    assert binding['result_sha256'] == sha(evidence/'opt60-board-assessment-02/result.json')
    assert binding['report_sha256'] == sha(root/'docs/Integrated_CPU60_Board_Results_20261025.md')
    coremark = read(evidence/'opt60-coremark-abab-04/result.json')
    assert coremark['total_score_gate'] is False
    for label in ('control', 'candidate'):
        samples = coremark['comparisons'][label]['coremark_per_mhz']
        assert len(samples['all_values']) == 6
        assert abs(sum(samples['all_values'])/6-samples['mean']) < 1e-12
    decrease = coremark['comparisons']['control']['coremark_per_mhz']['mean']-coremark['comparisons']['candidate']['coremark_per_mhz']['mean']
    assert abs(decrease-coremark['coremark_per_mhz_absolute_decrease']) < 1e-12
    assert decrease <= .05
    assert all(b['status'] == 'PASS' for b in coremark['batches'])
    assert read(evidence/'native/physical-launch.json')['status'] == 'ROUTED_FULL_STA_PASS_NOT_BOARD'
    assert read(evidence/'regression/result.json')['status'] == 'SOC_ALL_TESTS_PASS_NOT_BOARD'
    assert sha(root/'linux/picture_new/whole_layer_fast/vision32_layer.c') == '6303036b6f3fdffdc63b6b0d6f4fb2ac2c73f946ae0815d9ff72b6fb4d52d649'
    return dict(status='CPU60_MAIN_BYTES_AND_EVIDENCE_PASS_NOT_FORMAL_DELIVERY',
                frozen_inputs=len(snap['inputs']), evidence_files=len(sources),
                bitstream_sha256=m['bitstream_sha256'], mixed_audio_pass=False,
                voice_preview_persisted=False, formal_delivery=False)


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
