#!/usr/bin/env python3
"""Exercise CPU configuration synchronization using only disposable fixtures.

Requires Python 3, Windows PowerShell and an explicitly selected src checkout
for its real generated-input verifiers. No CPU is generated or simulated.
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
    parser.add_argument('--source-repo', type=Path, required=True, help='src repository directory; no sibling-repository default')
    parser.add_argument('--powershell', default='powershell.exe', help='PowerShell executable or PATH command')
    parser.add_argument('--output', type=Path, help='Optional compact JSON result')
    args = parser.parse_args()
    powershell = shutil.which(args.powershell)
    if not powershell:
        parser.error('Windows PowerShell is required; pass --powershell with its executable path.')
    root = Path(__file__).resolve().parent.parent
    source_project = args.source_repo.resolve() / 'cpu'
    inputs = {'scripts/sync_cpu.ps1': root / 'scripts/sync_cpu.ps1',
              'source/scripts/verify_generated.py': source_project / 'scripts/verify_generated.py',
              'source/scripts/verify_build_inputs.ps1': source_project / 'scripts/verify_build_inputs.ps1'}
    for path in inputs.values():
        if not path.is_file():
            parser.error('Required sync/source verifier is missing: ' + str(path))
    tested = {name: digest(path) for name, path in inputs.items()}
    checks = []
    with tempfile.TemporaryDirectory(prefix='cpu-sync-config-fixture-') as directory:
        fixture = Path(directory).resolve()
        source = fixture / 'source'
        project = source / 'cpu'
        target = fixture / 'integration'
        sync_script = target / 'scripts/sync_cpu.ps1'

        def write(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            text = value if isinstance(value, str) else json.dumps(value, indent=2) + '\n'
            path.write_bytes(text.encode('utf-8'))

        for name, path in inputs.items():
            destination = (project / name[len('source/'):]) if name.startswith('source/') else target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            if digest(destination) != tested[name]:
                raise AssertionError('Verifier changed while preparing the fixture: ' + name)
        for name in ('build.sbt', 'project/build.properties', 'project/plugins.sbt', 'src/main/scala/Fixture.scala'):
            write(project / name, 'Synthetic input; never compiled.\n')
        write(source / 'VERSION', '3.1.0\n')
        for depth in (1024, 2048, 4096):
            write(project / ('scripts/meminit/zero_' + str(depth) + '.hex'), '00\n')
        core = {'schema_version': 1, 'isa': 'rv32ima_zicsr_zifencei', 'supervisor': False,
                'architecture': {'aluEntries': 3, 'memEntries': 2, 'fallbackSets': 32, 'fallbackHash': False, 'rasDepth': 2},
                'cache': {'lineBytes': 32, 'l1Sets': 128, 'iWays': 2, 'dWays': 2, 'l2Sets': 512, 'l2Ways': 1},
                'mode': {'synthesis': True, 'socProbes': False}}
        sim = copy.deepcopy(core)
        sim['mode'] = {'synthesis': False, 'socProbes': True}

        def run(command, passed, label, pattern=''):
            result = subprocess.run(command, cwd=str(project), text=True, capture_output=True, timeout=30)
            if (result.returncode == 0) != passed or (pattern and pattern not in result.stdout + result.stderr):
                raise AssertionError(label + '\n' + result.stdout + '\n' + result.stderr)

        def emit(core_config, sim_config):
            command = [sys.executable, str(project / 'scripts/verify_generated.py')]
            run(command + ['capture', '--snapshot', 'work/emit-inputs.json'], True, 'capture')
            misa = "40141101" if core_config['supervisor'] else "40001101"
            rtl = "module CoreTop(input io_resetVector);\nlocalparam MISA = 32'h" + misa + ";\nendmodule\n"
            for name, config in (('generated/core', core_config), ('generated/sim', sim_config), ('work/handoff-probes', sim_config)):
                write(project / name / 'CoreTop.sv', rtl)
                write(project / name / 'emit-config.json', config)
            run(command + ['record', '--snapshot', 'work/emit-inputs.json'], True, 'record')

        def sync(*arguments, passed=True, label='', pattern=''):
            run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(sync_script)] + list(arguments), passed, label, pattern)
            checks.append(label)

        emit(core, sim)
        sync('-SourceRepo', str(source), label='valid_schema2_exported_directory_import')
        config_path = target / 'rtl/cpu/emit-config.json'
        manifest_path = target / 'rtl/cpu/source.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['source_kind'] == 'exported_directory'
        assert manifest['source_reference_commit'] is None and manifest['source_worktree_dirty'] is None
        assert manifest['cpu_version'] == '3.1.0'
        assert config_path.read_bytes() == (project / 'generated/core/emit-config.json').read_bytes()
        assert manifest['config_sha256'] == digest(config_path)
        checks.append('configuration_copied_byte_for_byte_with_hash_and_null_git_metadata')
        sync('-SourceRepo', str(source), '-Check', label='valid_explicit_source_check')
        config_bytes = config_path.read_bytes()
        config_path.write_bytes(config_bytes + b'\n')
        sync('-Check', passed=False, label='modified_local_configuration_rejected', pattern='configuration hash differs')
        config_path.write_bytes(config_bytes)
        bad = copy.deepcopy(core)
        bad['mode']['socProbes'] = True
        write(config_path, bad)
        changed_manifest = copy.deepcopy(manifest)
        changed_manifest['config_sha256'] = digest(config_path)
        write(manifest_path, changed_manifest)
        sync('-Check', passed=False, label='rehash_cannot_hide_wrong_synthesis_mode', pattern='without simulation probes')
        config_path.write_bytes(config_bytes)
        write(manifest_path, manifest)
        config_path.rename(config_path.with_suffix('.disabled'))
        sync('-Check', passed=False, label='missing_configuration_rejected', pattern='emit-config.json is missing')
        config_path.with_suffix('.disabled').rename(config_path)
        old = copy.deepcopy(manifest)
        del old['config_sha256']
        write(manifest_path, old)
        sync('-Check', passed=False, label='old_provenance_requires_resync', pattern='run sync_cpu.ps1 -SourceRepo again')
        write(manifest_path, manifest)
        source_config = project / 'generated/core/emit-config.json'
        original = source_config.read_bytes()
        source_config.write_bytes(original + b'\n')
        sync('-SourceRepo', str(source), '-Check', passed=False, label='source_generation_gate_precedes_metadata_comparison', pattern='Generated CPU output changed')
        source_config.write_bytes(original)
        new_core, new_sim = copy.deepcopy(core), copy.deepcopy(sim)
        new_core['architecture']['aluEntries'] = new_sim['architecture']['aluEntries'] = 6
        emit(new_core, new_sim)
        sync('-SourceRepo', str(source), '-Check', passed=False, label='fresh_different_source_configuration_rejected', pattern='emit configuration differs from the selected')
        s_core, s_sim = copy.deepcopy(core), copy.deepcopy(sim)
        s_core['supervisor'] = s_sim['supervisor'] = True
        emit(s_core, s_sim)
        sync('-SourceRepo', str(source), passed=False, label='supervisor_import_requires_explicit_candidate_switch', pattern='selected RV32IMA synthesis profile')
        sync('-SourceRepo', str(source), '-AllowSupervisorCandidate', label='supervisor_candidate_import')
        sync('-SourceRepo', str(source), '-Check', label='supervisor_candidate_provenance_check')
        emit(core, sim)
        sync('-SourceRepo', str(source), label='baseline_profile_restored')
        verify = project / 'scripts/verify_build_inputs.ps1'
        verify.rename(verify.with_suffix('.disabled'))
        sync('-Check', label='standalone_local_check_needs_no_source_verifier')
        sync('-SourceRepo', str(source), '-Check', passed=False, label='explicit_source_check_requires_source_verifier', pattern='lacks its generated RTL input verifier')
    result = {
        'schema_version': 1, 'kind': 'PORTABLE_SYNTHETIC_CPU_CONFIGURATION_SYNC_SCHEMA2_FIXTURES', 'status': 'PASS',
        'completed_utc': datetime.now(timezone.utc).isoformat(), 'source_generated_manifest_schema': 2,
        'test_count': len(checks), 'checks': checks, 'runner': 'scripts/test_cpu_sync.py',
        'runner_sha256': digest(Path(__file__)), 'tested_input_scripts_sha256': tested,
        'reproduction_command': 'python scripts/test_cpu_sync.py --source-repo <src-repository> --output artifacts/selftest/cpu-config-sync-fixtures.json',
        'child_timeout_seconds': 30, 'hardware_compilation_or_execution': False,
        'fixture_changes_hardware_behavior': False, 'historical_schema1_results_are_separate': True,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes((json.dumps(result, indent=2) + '\n').encode('utf-8'))
    print('CPU_SYNC_SCHEMA2_FIXTURES_PASS checks=' + str(len(checks)))


if __name__ == '__main__':
    main()
