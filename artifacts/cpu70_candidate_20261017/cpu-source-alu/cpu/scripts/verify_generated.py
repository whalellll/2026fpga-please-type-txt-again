"""Bind generated CPU RTL to its source inputs, including a fresh Emit run."""
import argparse
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'generated/manifest.json'
RTL_OUTPUTS = ('generated/core/CoreTop.sv', 'generated/sim/CoreTop.sv')
CONFIG_OUTPUTS = ('generated/core/emit-config.json', 'generated/sim/emit-config.json')
OUTPUTS = RTL_OUTPUTS + CONFIG_OUTPUTS
ARCH_KEYS = ('aluEntries', 'memEntries', 'fallbackSets', 'fallbackHash', 'rasDepth')
CACHE_KEYS = ('lineBytes', 'l1Sets', 'iWays', 'dWays', 'l2Sets', 'l2Ways')
PURPOSE = 'CPU source to generated RTL binding'


def load_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise SystemExit('Duplicate JSON key: ' + key)
            value[key] = item
        return value
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def keys(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        raise SystemExit(label + ' has missing or unsupported fields.')


def architecture(value):
    keys(value, ARCH_KEYS, 'Architecture configuration')
    for name in ARCH_KEYS:
        item = value[name]
        if name == 'fallbackHash':
            if type(item) is not bool:
                raise SystemExit('fallbackHash must be a JSON boolean.')
        elif type(item) is not int or not 1 <= item <= 2147483647:
            raise SystemExit(name + ' must be a positive JSON integer.')


def config(path, synthesis):
    value = load_json(path)
    keys(value, ('schema_version', 'isa', 'supervisor', 'architecture', 'cache', 'mode'), 'Emit configuration')
    if (type(value['schema_version']) is not int or value['schema_version'] != 1 or
            value['isa'] != 'rv32ima_zicsr_zifencei' or type(value['supervisor']) is not bool):
        raise SystemExit('Unsupported emit ISA/profile/schema.')
    architecture(value['architecture'])
    keys(value['cache'], CACHE_KEYS, 'Cache configuration')
    for name, item in value['cache'].items():
        if type(item) is not int or not 1 <= item <= 2147483647:
            raise SystemExit('Invalid cache configuration: ' + name)
    keys(value['mode'], ('synthesis', 'socProbes'), 'Emit mode')
    if value['mode']['synthesis'] is not synthesis or value['mode']['socProbes'] is not (not synthesis):
        raise SystemExit('Wrong synthesis/simulation probe mode in ' + str(path))
    return value


def configurations():
    core = config(ROOT / CONFIG_OUTPUTS[0], True)
    sim = config(ROOT / CONFIG_OUTPUTS[1], False)
    for name in ('isa', 'supervisor', 'architecture', 'cache'):
        if core[name] != sim[name]:
            raise SystemExit('Synthesis and simulation configurations differ: ' + name)
    return core, sim


def generation(arch, supervisor=False):
    # Every allowed architecture override is explicit, including default values.
    flags = ' '.join('-De91c.' + name + '=' + str(arch[name]).lower() for name in ARCH_KEYS)
    profile = ' -De91c.supervisor=true' if supervisor else ''
    return [flags + profile + ' -De91c.socProbes=false runMain e91c.core.EmitCore generated/core --synthesis',
            flags + profile + ' -De91c.socProbes=true runMain e91c.core.EmitCore work/handoff-probes']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs():
    files = [ROOT / 'build.sbt']
    files += list((ROOT / 'project').glob('*.sbt'))
    files += list((ROOT / 'project').glob('*.properties'))
    files += [p for p in (ROOT / 'src/main').rglob('*') if p.is_file()]
    files += list((ROOT / 'scripts/meminit').glob('*.hex'))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(files))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('capture', 'record', 'check'))
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--simulation', type=Path)
    args = parser.parse_args()
    current = inputs()
    if args.action == 'capture':
        if args.snapshot is None:
            parser.error('capture requires --snapshot')
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps({'started_epoch': time.time(),
            'source_files': current}, indent=2) + '\n', encoding='utf-8')
        print('EMIT_INPUTS_CAPTURED')
        return
    if args.action == 'record':
        if args.snapshot is None:
            parser.error('record requires --snapshot from before Emit')
        before = load_json(args.snapshot)
        if before['source_files'] != current:
            raise SystemExit('CPU inputs changed during Emit; generate both outputs again.')
        outputs = {}
        for name in OUTPUTS:
            path = ROOT / name
            if not path.is_file() or path.stat().st_mtime < before['started_epoch']:
                raise SystemExit('Emit did not refresh ' + name)
            outputs[name] = sha(path)
        core, _ = configurations()
        for name in ('CoreTop.sv', 'emit-config.json'):
            probe = ROOT / 'work/handoff-probes' / name
            if not probe.is_file() or sha(probe) != outputs['generated/sim/' + name]:
                raise SystemExit('The work probe and delivered simulation export differ: ' + name)
        record = {'schema_version': 2, 'purpose': PURPOSE,
            'generation': generation(core['architecture'], core['supervisor']), 'architecture': core['architecture'],
            'source_files': current, 'outputs': outputs}
        MANIFEST.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print('GENERATED_RTL_RECORDED')
        return
    if not MANIFEST.is_file():
        raise SystemExit('Missing generated/manifest.json; run newpc.ps1 -Stage Emit.')
    record = load_json(MANIFEST)
    keys(record, ('schema_version', 'purpose', 'generation', 'architecture', 'source_files', 'outputs'), 'Generated CPU manifest')
    if (type(record['schema_version']) is not int or record['schema_version'] != 2 or
            record['purpose'] != PURPOSE or record['source_files'] != current):
        raise SystemExit('CPU source/config/init files changed; run Emit before testing.')
    keys(record['outputs'], OUTPUTS, 'Generated RTL output map')
    for name, expected in record['outputs'].items():
        if type(expected) is not str or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise SystemExit('Invalid output SHA256: ' + name)
        if not (ROOT / name).is_file() or sha(ROOT / name) != expected:
            raise SystemExit('Generated RTL changed: ' + name + '; run Emit.')
    core, _ = configurations()
    architecture(record['architecture'])
    if record['architecture'] != core['architecture'] or record['generation'] != generation(core['architecture'], core['supervisor']):
        raise SystemExit('Recorded architecture or reproduction arguments differ from the exports.')
    if args.simulation:
        for name in ('CoreTop.sv', 'emit-config.json'):
            selected = args.simulation if name == 'CoreTop.sv' else args.simulation.with_name(name)
            if not selected.is_file() or sha(selected) != record['outputs']['generated/sim/' + name]:
                raise SystemExit('Selected simulation export is stale or from a different Emit: ' + name)
    print('GENERATED_RTL_PASS')


if __name__ == '__main__':
    main()
