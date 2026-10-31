#!/usr/bin/env python3
"""Run nine synthetic export-configuration gate cases; no RTL is compiled.

Requires Python 3 and Windows PowerShell. Run from any working directory:
  python scripts/test_emit_config.py --output work/emit-config-fixtures.json
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--powershell', default='powershell.exe', help='PowerShell executable or PATH command')
    parser.add_argument('--output', type=Path, help='Optional compact JSON result')
    args = parser.parse_args()
    powershell = shutil.which(args.powershell)
    if not powershell:
        parser.error('Windows PowerShell is required; pass --powershell with its executable path.')
    root = Path(__file__).resolve().parent.parent
    checks = []
    tested = {name: digest(root / 'scripts' / name) for name in ('verify_generated.py', 'verify_build_inputs.ps1')}
    # This newly allocated directory is the only tree the test mutates/cleans.
    with tempfile.TemporaryDirectory(prefix='cpu-emit-config-fixture-') as directory:
        fixture = Path(directory).resolve()

        def write(name, text):
            path = fixture / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode('utf-8'))

        def run(command, passed, label):
            value = subprocess.run(command, cwd=str(fixture), capture_output=True, text=True, timeout=30)
            if (value.returncode == 0) != passed:
                raise AssertionError(label + '\n' + value.stdout + '\n' + value.stderr)

        def verify(passed, label):
            run([sys.executable, str(fixture / 'scripts/verify_generated.py'), 'check'], passed, label + ' Python')
            run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                 str(fixture / 'scripts/verify_build_inputs.ps1'), '-GeneratedCpu'], passed, label + ' PowerShell')
            checks.append(label)

        for name in tested:
            destination = fixture / 'scripts' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / 'scripts' / name, destination)
            if digest(destination) != tested[name]:
                raise AssertionError('Verifier changed while preparing the fixture: ' + name)
        for name in ('build.sbt', 'project/build.properties', 'project/plugins.sbt', 'src/main/scala/Fixture.scala'):
            write(name, 'synthetic fixture\n')
        for depth in (1024, 2048, 4096):
            write('scripts/meminit/zero_' + str(depth) + '.hex', '00\n')
        core = {'schema_version': 1, 'isa': 'rv32ima_zicsr_zifencei', 'supervisor': False,
                'architecture': {'aluEntries': 3, 'memEntries': 2, 'fallbackSets': 32, 'fallbackHash': False, 'rasDepth': 2},
                'cache': {'lineBytes': 32, 'l1Sets': 128, 'iWays': 2, 'dWays': 2, 'l2Sets': 512, 'l2Ways': 1},
                'mode': {'synthesis': True, 'socProbes': False}}
        sim = copy.deepcopy(core)
        sim['mode'] = {'synthesis': False, 'socProbes': True}
        command = [sys.executable, str(fixture / 'scripts/verify_generated.py')]

        def emit(core_config, sim_config):
            run(command + ['capture', '--snapshot', 'work/emit-inputs.json'], True, 'capture')
            for name, config in (('generated/core', core_config), ('generated/sim', sim_config), ('work/handoff-probes', sim_config)):
                write(name + '/CoreTop.sv', 'Synthetic RTL; never compiled.\n')
                write(name + '/emit-config.json', json.dumps(config, indent=2) + '\n')
            run(command + ['record', '--snapshot', 'work/emit-inputs.json'], True, 'record')

        emit(core, sim)
        verify(True, 'matching_schema2_configuration')
        original = {name: (fixture / name).read_bytes() for name in
                    ('generated/manifest.json', 'generated/core/emit-config.json', 'generated/sim/emit-config.json')}

        def restore():
            for name, data in original.items():
                (fixture / name).write_bytes(data)

        def edit_config(name, change):
            value = json.loads((fixture / name).read_text(encoding='utf-8'))
            change(value)
            write(name, json.dumps(value) + '\n')
            manifest = json.loads((fixture / 'generated/manifest.json').read_text(encoding='utf-8'))
            manifest['outputs'][name] = digest(fixture / name)
            write('generated/manifest.json', json.dumps(manifest) + '\n')

        cases = [
            ('architecture_difference', 'generated/sim/emit-config.json', lambda x: x['architecture'].__setitem__('rasDepth', 4)),
            ('wrong_probe_mode', 'generated/core/emit-config.json', lambda x: x['mode'].__setitem__('socProbes', True)),
            ('unknown_override_key', 'generated/core/emit-config.json', lambda x: x['architecture'].__setitem__('unknown', 1)),
            ('boolean_disguised_as_number', 'generated/core/emit-config.json', lambda x: x['architecture'].__setitem__('fallbackHash', 0)),
            ('missing_required_cache_key', 'generated/core/emit-config.json', lambda x: x['cache'].pop('lineBytes')),
        ]
        for label, name, change in cases:
            restore()
            edit_config(name, change)
            verify(False, label)
        restore()
        (fixture / 'generated/sim/emit-config.json').unlink()
        verify(False, 'missing_sidecar')
        restore()
        manifest = json.loads((fixture / 'generated/manifest.json').read_text(encoding='utf-8'))
        manifest['schema_version'] = 1
        write('generated/manifest.json', json.dumps(manifest) + '\n')
        verify(False, 'historical_schema1_rejected_as_current')
        core['architecture']['aluEntries'] = sim['architecture']['aluEntries'] = 4
        emit(core, sim)
        verify(True, 'consistent_nondefault_override_recorded')
    result = {
        'schema_version': 1, 'kind': 'PORTABLE_SYNTHETIC_EMIT_CONFIGURATION_SCHEMA2_FIXTURES', 'status': 'PASS',
        'completed_utc': datetime.now(timezone.utc).isoformat(), 'source_generated_manifest_schema': 2,
        'test_count': len(checks), 'checks': checks, 'runner': 'scripts/test_emit_config.py',
        'runner_sha256': digest(Path(__file__)), 'tested_input_scripts_sha256': tested,
        'reproduction_command': 'python scripts/test_emit_config.py --output work/emit-config-fixtures.json',
        'child_timeout_seconds': 30, 'hardware_compilation_or_execution': False,
        'fixture_changes_hardware_behavior': False, 'historical_schema1_results_are_separate': True,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes((json.dumps(result, indent=2) + '\n').encode('utf-8'))
    print('EMIT_CONFIG_SCHEMA2_FIXTURES_PASS checks=' + str(len(checks)))


if __name__ == '__main__':
    main()
