"""Three bounded A/B pairs, with identical profiler/CPU-mock boundaries.

Run alone after correctness/build checks; other compiler/emulator jobs perturb
the host measurements. Medians describe these few samples, not board P50/P95.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import check_picture_integer_graph as check


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--verified', type=Path, required=True)
    a = ap.parse_args()
    assert not a.output.exists()
    verified = json.loads((a.verified/'result.json').read_text())
    assert verified['status'] == 'PASS'
    assert verified['targets']['qemu']['golden']['crc_and_sha_equal']
    production = {n:h for n,h in verified['source_sha256'].items() if n.endswith(('.c','.h','.sh'))}
    assert all(check.sha(check.ROOT/n) == h for n, h in production.items())
    assert all(check.sha(Path(n)) == h for n, h in verified['fixture_sha256'].items())
    models = check.ROOT/'build/picture-merge-20261023/native-models'
    inputs = check.ROOT/'build/picture-board-resume-20261023/synthetic-inputs-r01'
    a.output.mkdir(parents=True)
    sources = [check.ROOT/n for n in check.BASE]+[
        check.ROOT/'linux/picture_new/graph_tensor.c', check.ROOT/'linux/picture_new/graph_profile.c',
        check.ROOT/'linux/picture_new/test_graph_profile.c']
    classifier_s16=verified.get('classifier_s16',False)
    if classifier_s16:
        assert verified.get('legacy_profile_outputs'), 'Provide verified legacy profile outputs for the numerical boundary'
        sources.append(check.ROOT/'linux/picture_new/graph_ops.c')
    result = {'status': 'RUNNING', 'hardware_used': False, 'pairs': 3, 'targets': {},
              'verified_sha256': check.sha(a.verified/'result.json'),
              'classifier_s16':classifier_s16,
              'source_sha256': verified['source_sha256'],
              'production_sources_current': production,
              'current_helper_sha256': check.sha(Path(check.__file__)),
              'benchmark_script_sha256': check.sha(Path(__file__)),
              'limitations': 'Synthetic input, CPU V321 mock; CPU times exclude mock ioctl. '
                             'QEMU is not CPU60 cycle simulation. Three pairs are not clean board P50/P95.'}
    for target, cc, extra, prefix in [
        ('host', 'gcc', [], []), ('qemu', '/opt/toolchain/bin/riscv32-linux-musl-gcc',
                                ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'], ['qemu-riscv32'])]:
        binaries = {}
        for mode, enabled in [('baseline', 0), ('integer', 1)]:
            binary = a.output/(target+'-'+mode)
            check.run([cc, *check.FLAGS, *extra, '-DXQ_GRAPH_PROFILE', '-DXQ_NATIVE_COACH',
                       '-DXQ_INTEGER_CARRIER='+str(enabled), '-DXQ_FAST_REQUANT='+str(enabled),
                       '-DXQ_CLASSIFIER_S16='+str(int(classifier_s16 and enabled)),
                       *['-I'+str(check.ROOT/d) for d in check.INCLUDES], *sources,
                       '-Wl,--wrap=ioctl', '-Wl,--gc-sections', '-lm', '-o', binary],
                      a.output/(target+'-'+mode+'-compile.log'), 90)
            binaries[mode] = binary
        samples = {'baseline': [], 'integer': []}
        for pair in range(3):
            for mode in ['baseline', 'integer']:
                log = a.output/f'{target}-{pair}-{mode}.log'
                check.run([*prefix, binaries[mode], models, inputs], log, 180)
                profile = check.parse_profile(log)
                for name, entry in profile.items():
                    wanted=(verified['legacy_profile_outputs'][target][name] if classifier_s16 and mode=='baseline'
                            else verified['targets'][target]['profile'][name]['output_sha256'])
                    assert entry['output_sha256'] == wanted
                samples[mode].append(profile)
        summary = {}
        for model in ['board', 'detector', 'classifier']:
            summary[model] = {}
            for mode in samples:
                values = [row[model]['userspace_cpu_ns_excluding_mock'] for row in samples[mode]]
                summary[model][mode+'_cpu_ns'] = values
                summary[model][mode+'_median_ms'] = statistics.median(values)/1e6
            old, new = summary[model]['baseline_median_ms'], summary[model]['integer_median_ms']
            summary[model]['median_cpu_reduction_percent'] = 100*(1-new/old)
        result['targets'][target] = {'samples': samples, 'summary': summary,
                                     'binary_sha256': {k: check.sha(p) for k, p in binaries.items()}}
    assert all(check.sha(check.ROOT/n) == h for n, h in production.items())
    result['status'] = 'PASS'
    (a.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('BOUNDED_INTEGER_GRAPH_AB_PASS_NOT_BOARD')
    for target, entry in result['targets'].items():
        print(target, {m: round(v['median_cpu_reduction_percent'], 2) for m, v in entry['summary'].items()})


if __name__ == '__main__':
    main()
