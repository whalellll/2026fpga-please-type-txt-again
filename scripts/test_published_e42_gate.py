"""Finite negative controls for e42 identity; never opens JTAG/UART.

Fixtures use actual repository bytes and actual immutable Git blobs. Only the
Git object reader is routed to the real repository for the disposable fixture;
source/image/evidence SHA checks themselves execute unchanged.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    logical = a.output.absolute()
    assert logical.is_relative_to(ROOT / 'build') and not logical.exists()
    out = logical.resolve();out.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('e42_gate', ROOT / 'scripts/check_published_e42.py')
    gate = importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    real_blob = gate.blob
    pub = ROOT / gate.PUB
    manifest = json.loads((pub / 'manifest.json').read_text(encoding='utf-8-sig'))
    snap = json.loads((pub / 'native/build_snapshot.json').read_text(encoding='utf-8-sig'))
    baseline = json.loads(real_blob(ROOT, gate.MAIN, 'artifacts/build_snapshot.json'))
    names = set(baseline['inputs']) | (set(snap['inputs']) - gate.HELPERS)
    names |= set(manifest['hardware_source_sha256']) | set(manifest['build_artifact_inputs_sha256'])
    names |= {gate.PUB + '/' + n for n in manifest['files']}
    names |= {gate.PUB + '/manifest.json', gate.ARCHIVE + '/manifest.json'}
    names |= {gate.ARCHIVE + '/' + n for n in gate.HELPERS}
    names |= set(gate.PARSER_FILES)
    fixture = out / 'fixture'
    for name in sorted(names):
        target = fixture / name;target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    gate.blob = lambda root, ref, name: real_blob(ROOT, ref, name)
    image = fixture / gate.PUB / 'soc_top.sbit'
    positive = gate.check(fixture, image, out / 'positive-reports')
    assert positive['native_input_hashes'] == 498 and not positive['formal_release']
    cases = []

    def rejected(name, path=None, replacement=None, wrong_image=None):
        original = path.read_bytes() if path else None
        if path:path.write_bytes(replacement)
        try:
            gate.check(fixture, wrong_image or image, out / (name + '-reports'))
        except (ValueError, FileNotFoundError) as error:
            cases.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('Gate accepted ' + name)
        finally:
            if path:path.write_bytes(original)

    rejected('external-identical-image', wrong_image=ROOT / gate.PUB / 'soc_top.sbit')
    rejected('old-default-image-path', wrong_image=fixture / 'artifacts/soc_top.sbit')
    original = image.read_bytes()
    rejected('wrong-bitstream-bytes', image, bytes([original[0] ^ 1]) + original[1:])
    path = fixture / 'rtl/mac_accel/vision32_layer.v'
    rejected('changed-rtl', path, path.read_bytes() + b'\n// source change\n')
    path = fixture / 'config/clocks.json'
    rejected('changed-clock-source', path, path.read_bytes() + b'\n')
    path = fixture / gate.ARCHIVE / sorted(gate.HELPERS)[0]
    rejected('changed-archived-helper', path, path.read_bytes() + b'\n')
    path = fixture / gate.PUB / 'manifest.json'
    rejected('changed-publication-manifest', path, path.read_bytes() + b'\n')
    path = fixture / gate.PUB / 'native/report_timing/rtr.db.gz'
    original = path.read_bytes()
    rejected('changed-original-sta', path, original[:-1] + bytes([original[-1] ^ 1]))
    path = fixture / 'scripts/build_picture_new_interface.py'
    rejected('changed-live-main-build-helper', path, path.read_bytes() + b'\n')
    final = gate.check(fixture, image, out / 'restored-reports')
    assert final['bitstream_sha256'] == gate.IMAGE
    record = {'status': 'E42_REAL_GIT_BLOBS_498_INPUTS_AND_9_NEGATIVE_CONTROLS_PASS_NO_HARDWARE',
              'native_inputs': 498, 'live_inputs': 491, 'archived_build_helpers': 7,
              'cases': cases, 'real_git_object_reader_used': True,
              'sha_checks_mocked': False, 'hardware_used': False, 'formal_release': False}
    (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(record['status'])


if __name__ == '__main__':
    main()
