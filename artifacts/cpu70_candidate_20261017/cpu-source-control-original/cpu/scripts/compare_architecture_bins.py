#!/usr/bin/env python3
"""Compare seven deterministic architecture programs without rebuilding RTL models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
FLAGS = ['-march=rv32ima_zicsr_zifencei', '-mabi=ilp32', '-mno-relax',
         '-nostdlib', '-nostartfiles', '-Wl,--build-id=none']
TESTS = ['cpu', 'atomic', 'machine', 'memory_order', 'bus_error', 'write-bresp', 'write-fill']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def executable(prefix, name):
    path = Path(prefix + name)
    if not path.is_file() and os.name == 'nt':
        path = Path(str(path) + '.exe')
    if not path.is_file():
        raise ValueError('Missing compiler tool ' + str(path))
    return path.resolve()


def run(command, cwd, log, env=None):
    result = subprocess.run([str(item) for item in command], cwd=cwd, env=env,
                            capture_output=True, text=True, errors='replace', timeout=30)
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Command failed with exit {}: see {}'.format(result.returncode, log))
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-prefix', required=True)
    parser.add_argument('--candidate-prefix', required=True)
    parser.add_argument('--reference-version', default='13.2.0')
    parser.add_argument('--candidate-version', default='14.2.0')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--simulation-record', type=Path,
                        default=ROOT / 'handoff/validation/architecture-gcc13_2/result.json')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    historical = json.loads(args.simulation_record.read_text(encoding='utf-8-sig'))
    if historical['status'] != 'PASS':
        raise ValueError('Reference simulation record is not PASS')
    if not re.search(r'(?<![0-9.])' + re.escape(args.reference_version) +
                     r'(?![0-9.])', historical.get('compiler', '')):
        raise ValueError('Reference version does not match the simulation record')
    sources = ['scripts/generate_' + name + '_test.py' for name in
               ['cpu', 'atomic', 'machine', 'memory_order', 'bus_error', 'write_error']]
    sources += ['coremark_test_soc/sw/link.ld', 'coremark_test_soc/rtl/coremark_soc_top.v',
                'coremark_test_soc/sim/tb_coremark_soc.v']
    hashes = {name: sha(ROOT / name) for name in sources}
    for name in sources[:6]:
        if hashes[name] != historical['script_sha256'][Path(name).name]:
            raise ValueError('Generator differs from the recorded old-compiler simulation: ' + name)
    report = dict(schema_version=1, status='RUNNING', simulation_rerun=False,
                  scope='recompile identical assembly/linker inputs and compare raw BIN bytes; no RTL model or simulation rerun',
                  simulation_record_sha256=sha(args.simulation_record),
                  simulation_rtl_sha256=historical['rtl_sha256'],
                  synthesis_rtl_sha256=historical['synthesis_rtl_sha256'],
                  runner_sha256=sha(Path(__file__)),
                  flags=FLAGS, source_sha256=hashes, compilers={}, tests={})
    try:
        compiler_info = {}
        for label, prefix in [('reference', args.reference_prefix), ('candidate', args.candidate_prefix)]:
            gcc, objcopy = executable(prefix, 'gcc'), executable(prefix, 'objcopy')
            env = dict(os.environ, PYTHONUTF8='1')
            env['PATH'] = str(gcc.parent) + os.pathsep + env.get('PATH', '')
            target = run([gcc, '-dumpmachine'], out, out / (label + '-target.txt'), env)
            version = run([gcc, '-dumpfullversion'], out, out / (label + '-version.txt'), env)
            report['compilers'][label] = dict(target=target, version=version,
                                              gcc_sha256=sha(gcc), objcopy_sha256=sha(objcopy))
            compiler_info[label] = (gcc, objcopy, env)
        if report['compilers']['reference']['version'] != args.reference_version:
            raise ValueError('Expected GCC ' + args.reference_version + ' reference')
        if (args.reference_version != '13.2.0' and
                report['compilers']['reference']['target'] != 'riscv32-unknown-elf'):
            raise ValueError('The contest reference must target riscv32-unknown-elf')
        if (report['compilers']['candidate']['target'], report['compilers']['candidate']['version']) != ('riscv32-unknown-elf', args.candidate_version):
            raise ValueError('Expected real riscv32-unknown-elf GCC ' + args.candidate_version + ' candidate')
        for name in TESTS:
            tree = out / name
            for relative in sources:
                target = tree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            env = dict(os.environ, PYTHONUTF8='1')
            if name.startswith('write-'):
                env['WRITE_ERROR_KIND'] = name.split('-')[1]
                generator = 'generate_write_error_test.py'
            else:
                env.pop('WRITE_ERROR_KIND', None)
                generator = 'generate_' + name + '_test.py'
            run([sys.executable, tree / 'scripts' / generator], tree, tree / 'generator.log', env)
            assembly = tree / 'work/cpu-test/test.S'
            test = dict(assembly_sha256=sha(assembly), reference_pass_marker=historical['tests'][name]['pass_marker'])
            binaries = {}
            for label, (gcc, objcopy, compiler_env) in compiler_info.items():
                build = tree / label
                build.mkdir()
                elf, binary = build / 'test.elf', build / 'test.bin'
                run([gcc] + FLAGS + ['-T', tree / 'coremark_test_soc/sw/link.ld', assembly, '-o', elf],
                    tree, build / 'compile.log', compiler_env)
                run([objcopy, '-O', 'binary', elf, binary], tree, build / 'objcopy.log', compiler_env)
                binaries[label] = binary.read_bytes()
                test[label] = dict(bin_sha256=sha(binary), bin_bytes=len(binaries[label]), elf_sha256=sha(elf))
            test['bin_byte_identical'] = binaries['reference'] == binaries['candidate']
            if not test['bin_byte_identical']:
                test['first_differing_byte'] = next((i for i, (a, b) in enumerate(zip(binaries['reference'], binaries['candidate'])) if a != b), min(map(len, binaries.values())))
            report['tests'][name] = test
            print(name + ': ' + ('BIN_IDENTICAL' if test['bin_byte_identical'] else 'BIN_DIFFERS'), flush=True)
        report['requires_new_simulation'] = [name for name, test in report['tests'].items() if not test['bin_byte_identical']]
        report['status'] = 'BIN_IDENTICAL' if not report['requires_new_simulation'] else 'BIN_DIFFERS'
        report['interpretation'] = ('Recorded GCC ' + args.reference_version +
            ' simulation logs apply to these same program bytes only where '
            'bin_byte_identical=true; no new simulation was run.')
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('ARCHITECTURE_BIN_COMPARISON_' + report['status'])
    if report['requires_new_simulation']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
