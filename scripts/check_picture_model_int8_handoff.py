"""Independently export the INT8 handoff, reject corruption, run numeric smoke."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import zipfile

from picture_workspace import ROOT, workspace_path, wsl_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.output.absolute().is_relative_to(ROOT/'build'):
        parser.error('Use a fresh private build directory')
    out = workspace_path(args.output)
    if not out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()):
        parser.error('Model payloads must remain in the private E build directory')
    archive = workspace_path(args.archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert digest == args.expected_sha256
    out.mkdir(parents=True, exist_ok=False)
    exported = out/'exported';exported.mkdir()
    result = dict(status='FAILED_PRESERVED',archive_sha256=digest,hardware_used=False,
                  training_or_calibration_run=False,checks=[])

    def verify(name, okay=True):
        proc = subprocess.run([sys.executable,'-B',str(exported/'verify_handoff.py')],
            capture_output=True,timeout=30)
        (out/(name+'.log')).write_bytes(proc.stdout+proc.stderr)
        assert (proc.returncode == 0) == okay, (name, proc.returncode)
        result['checks'].append(dict(name=name,expected_rejection=not okay,pass_=True))

    try:
        with zipfile.ZipFile(archive) as z:
            assert len(z.namelist()) == len(set(z.namelist()))
            assert sum(i.file_size for i in z.infolist()) < 128*1024*1024
            for item in z.infolist():
                rel = PurePosixPath(item.filename)
                assert not item.is_dir() and not rel.is_absolute() and '..' not in rel.parts
                assert '\\' not in item.filename and (item.external_attr>>16)&0o170000 == 0o100000
                target = exported.joinpath(*rel.parts)
                assert target.resolve().is_relative_to(exported.resolve())
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as f:f.write(z.read(item))
        verify('exported-original')
        target = exported/'baseline-models/native_parameters.h'
        assert target.resolve().is_relative_to(out.resolve())
        saved = target.read_bytes()
        try:
            broken = bytearray(saved);broken[0] ^= 1;target.write_bytes(broken)
            verify('reject-corrupt-payload',False)
        finally:
            target.write_bytes(saved)
        try:
            target.unlink()
            verify('reject-missing-payload',False)
        finally:
            target.write_bytes(saved)
        unexpected = exported/'unexpected-test-file.txt'
        try:
            with unexpected.open('xb') as f:f.write(b'owned negative control\n')
            verify('reject-unlisted-payload',False)
        finally:
            unexpected.unlink()
        verify('exported-restored')
        command = ['python3','-B',wsl_path(exported/'numeric_smoke.py'),
                   '--output',wsl_path(out/'numeric-smoke')]
        with (out/'numeric-smoke.log').open('xb') as log:
            proc = subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                'ulimit -c 0\nexec timeout --kill-after=5 180 '+shlex.join(command)],
                stdout=log,stderr=subprocess.STDOUT,timeout=200)
        assert proc.returncode == 0, (out/'numeric-smoke.log').read_text(errors='replace')[-2000:]
        numeric = json.loads((out/'numeric-smoke/result.json').read_text())
        assert numeric['status'] == 'EXPORTED_MODEL_INT8_NUMERIC_SMOKE_PASS_NOT_BOARD'
        verify('exported-after-numeric')
        manifest = json.loads((exported/'manifest.json').read_text(encoding='utf-8'))
        for name,expected in manifest['current_source_sha256'].items():
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
        result.update(status='MODEL_INT8_EXPORTED_HASHES_NEGATIVE_CONTROLS_NUMERIC_SMOKE_PASS',
            archive_members=len(manifest['payloads'])+2,all_current_source_bindings_match=True,
            negative_controls_rejected=3,numeric_smoke=numeric,
            original_kit_complete_graph_rebenchmark=False,private_images_or_requests_used=False)
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
