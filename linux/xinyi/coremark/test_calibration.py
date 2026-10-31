"""Run the actual benchmark control flow with explicitly simulated timings."""
import argparse
import os
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='+')
    args = parser.parse_args()
    for scenario in ('seed-cost-and-warmup', 'stable', 'crc-fail',
                     'measurement-crc-fail', 'stalled-clock', 'retry-exhaustion'):
        result = subprocess.run(args.command + ['--target-ms', '45000'],
                                env=dict(os.environ, XY_CALIBRATION_FIXTURE=scenario),
                                capture_output=True, text=True, timeout=8)
        lines = result.stdout.splitlines()
        fields = [dict(re.findall(r'(\w+)=(\S+)', line)) for line in lines
                  if line.startswith('XY_CM_RESULT ')]
        runs = [dict(re.findall(r'(\w+)=(\d+)', line)) for line in lines
                if line.startswith('XY_FAKE_SEGMENT ')]
        expected_success = scenario in ('seed-cost-and-warmup', 'stable')
        if expected_success:
            assert result.returncode == 0 and len(fields) == 1, result.stdout + result.stderr
            report = fields[0]
            assert report['valid'] == '1'
            for seed, prefix in (('0', 'perf'), ('1', 'validation')):
                executed = [run for run in runs if run['validation'] == seed][-1]
                assert report[prefix+'_iterations'] == executed['iterations'], result.stdout
                assert report[prefix+'_ticks'] == executed['ticks'], result.stdout
                assert int(executed['ticks']) >= 10_000_000_000, result.stdout
        else:
            assert result.returncode != 0 and not any(f['valid'] == '1' for f in fields), result.stdout
            if scenario == 'retry-exhaustion':
                assert len(fields) == 1
                executed = [run for run in runs if run['validation'] == '1'][-1]
                assert fields[0]['validation_iterations'] == executed['iterations'], result.stdout
                assert fields[0]['validation_ticks'] == executed['ticks'], result.stdout
        print('CALIBRATION_CONTROL_PASS simulated_only=1 scenario='+scenario)
    print('CALIBRATION_FIXTURES_PASS_NOT_COREMARK_SCORE')


if __name__ == '__main__':
    main()
