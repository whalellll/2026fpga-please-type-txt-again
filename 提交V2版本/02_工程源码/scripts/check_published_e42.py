"""Authenticate the published e42 CRAM image for this integrated branch.

Every original native input is checked:491 current files and7 exact archived
software/build helpers. This proves portable identity, not native DB replay.
The selected image remains at its exact in-repository publication path.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import subprocess

REF = 'b24249d942ce19664582bf64aba60492942f08a2'
MAIN = 'e7288be9e49f348b37832a65415b6989c444384c'
ORIGIN = '85ed00197a199e06ecccb0bd0bc9c5184ea24c98'
RUN = 'c8282c991f494ddc8144e35245872c02'
IMAGE = 'e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b'
PUB = 'artifacts/validated_accelerators_20261025'
ARCHIVE = 'artifacts/picture-e42-integration-20261026/native-helpers'
HELPERS = {
    'scripts/build_image_hwc_physical.ps1', 'scripts/build_linux_mac_kernel.ps1',
    'scripts/build_pathopt_voice.py', 'scripts/build_picture_new_interface.py',
    'scripts/build_picture_timing_bench.py', 'scripts/build_vision_exact_physical.ps1',
    'scripts/vision32_cache_contract.py',
}
PARSER_FILES = ['scripts/build_snapshot.ps1', 'scripts/timing_scope.ps1',
                'scripts/timing_scope_pixel_grid.ps1', 'scripts/clock_policy.ps1']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def blob(root, ref, name):
    return subprocess.check_output(['git', '-C', str(root), 'show', ref + ':' + name], timeout=30)


def ordinary(root, path):
    require(path.is_file(), 'Missing input: ' + str(path))
    require(path.is_relative_to(root), 'Input outside repository')
    current = path
    while current != root:
        require(not current.is_symlink() and not current.is_junction(), 'Linked input: ' + str(path))
        current = current.parent
    return path.read_bytes()


def check(root, image, materialize):
    root = root.absolute()
    image = image.absolute()
    require(not root.is_symlink() and not root.is_junction(), 'Linked repository root')
    require(image == root / PUB / 'soc_top.sbit', 'Only exact in-repository e42 publication path is accepted')
    require(digest(ordinary(root, image)) == IMAGE, 'Wrong e42 image')
    manifest_data = ordinary(root, root / PUB / 'manifest.json')
    require(manifest_data == blob(root, REF, PUB + '/manifest.json'), 'Published manifest changed')
    m = json.loads(manifest_data)
    require(m['hardware_origin_commit'] == ORIGIN and m['native_run_id'] == RUN and
            m['bitstream_sha256'] == IMAGE and m['base_main_commit'] == MAIN, 'Foreign publication identity')
    require(m['cpu_hz'] == 60000000 and m['sys_hz'] == 49500000, 'Foreign clocks')
    for name, expected in {**m['hardware_source_sha256'], **m['build_artifact_inputs_sha256']}.items():
        require(digest(ordinary(root, root / name)) == expected, 'Published input changed: ' + name)
    for name, entry in m['files'].items():
        data = ordinary(root, root / PUB / name)
        require(digest(data) == entry['sha256'] and len(data) == entry['bytes'], 'Evidence changed: ' + name)
        raw = gzip.decompress(data) if entry['compressed'] else data
        require(digest(raw) == entry['source_sha256'], 'Original report bytes changed: ' + name)
    for name in PARSER_FILES:
        require(ordinary(root, root / name) == blob(root, REF, name), 'Reviewed parser changed: ' + name)
    snap_data = ordinary(root, root / PUB / 'native/build_snapshot.json')
    ev_data = ordinary(root, root / PUB / 'native/build_evidence.json')
    snap, evidence = json.loads(snap_data), json.loads(ev_data)
    require(snap['run_id'] == evidence['run_id'] == RUN and
            snap['inputs'] == evidence['inputs'] and len(snap['inputs']) == 498, 'Native input records disagree')
    archive = json.loads(ordinary(root, root / ARCHIVE / 'manifest.json'))
    require(archive['native_snapshot_sha256'] == digest(snap_data) and
            set(archive['files']) == HELPERS, 'Foreign archived helper set')
    for name, expected in snap['inputs'].items():
        path = root / ARCHIVE / name if name in HELPERS else root / name
        require(digest(ordinary(root, path)) == expected, 'Native input changed: ' + name)
        if name in HELPERS:
            require(archive['files'][name] == expected, 'Archived helper binding changed: ' + name)
    baseline = json.loads(blob(root, MAIN, 'artifacts/build_snapshot.json'))
    require(len(baseline['inputs']) == 495, 'Foreign main baseline')
    for name, expected in baseline['inputs'].items():
        if name == 'rtl/mac_accel/vision32_layer.v':
            expected = m['hardware_source_sha256'][name]
        require(digest(ordinary(root, root / name)) == expected, 'Unexpected base input change: ' + name)
    summary = json.loads(ordinary(root, root / PUB / 'offline/summary.json'))
    require(summary['source_commit'] == ORIGIN and summary['run_id'] == RUN and
            not summary['violations'] and not summary['native_max_skew_violations'], 'STA summary fails')
    require(summary['timing_scope']['summary_rows'] == 116 and
            sum(map(len, summary['native_max_skew_tables'].values())) == 20, 'Incomplete STA scope')
    rtr = gzip.decompress(ordinary(root, root / PUB / 'native/report_timing/soc_top.rtr.gz'))
    xml = gzip.decompress(ordinary(root, root / PUB / 'native/report_timing/rtr.db.gz'))
    require(b'Design Summary : All Constraints Met.' in rtr, 'Original routed STA is not passing')
    materialize = materialize.absolute()
    require(not materialize.exists(), 'Fresh audit material directory required')
    materialize.mkdir(parents=True)
    (materialize / 'routed.rtr').write_bytes(rtr)
    (materialize / 'routed.xml').write_bytes(xml)
    prefixes = ('rtl/', 'ip/', 'pds/', 'config/', 'sw/bootloader/')
    expected_paths = sorted(name for name in baseline['inputs'] if name.startswith(prefixes))
    return dict(status='EXACT_PUBLISHED_E42_IDENTITY_PASS_NOT_FORMAL_RELEASE',
                source_ref=REF, hardware_origin_commit=ORIGIN, run_id=RUN,
                bitstream_sha256=IMAGE, native_input_hashes=498,
                live_native_inputs=491, archived_build_helpers=7, main_input_hashes=495,
                hardware_inputs=len(m['hardware_source_sha256']),
                build_artifact_inputs=len(m['build_artifact_inputs_sha256']),
                evidence_payloads=len(m['files']), cpu_hz=60000000, sys_hz=49500000,
                firmware_binary_sha256=digest((root / 'artifacts/bootloader.bin').read_bytes()),
                cpu_rtl_sha256=digest((root / 'rtl/cpu/CoreTop.sv').read_bytes()),
                cpu_source_manifest_sha256=digest((root / 'rtl/cpu/source.json').read_bytes()),
                pds_snapshot_sha256=digest(snap_data), pds_build_evidence_sha256=digest(ev_data),
                upstream_sta_pass=True, native_database_replay_complete=False, formal_release=False,
                expected_hardware_paths=expected_paths,
                raw_rtr=str(materialize / 'routed.rtr'), raw_xml=str(materialize / 'routed.xml'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--image', required=True, type=Path)
    p.add_argument('--materialize', required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(check(args.root, args.image, args.materialize), separators=(',', ':')))
