"""Validate fixed-iteration RTL CoreMark data; do not use host wall time."""
import argparse
import hashlib
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('run_dir', type=Path)
p.add_argument('--calibration', action='store_true')
args = p.parse_args()
root = args.run_dir
(root/'result.json').unlink(missing_ok=True)
log = (root/'run.log').read_text()
manifest = json.loads((root/'manifest.json').read_text())

def integer(label):
    match = re.search(r'^' + re.escape(label) + r'\s*:\s*(\d+)', log, re.M)
    if not match:
        raise SystemExit('Missing field: '+label)
    return int(match.group(1))

iterations, printed_ticks = integer('Iterations'), integer('Total ticks')
ticks = integer('PORT_TICKS64') if manifest.get('tick_report') == 'PORT_TICKS64' else printed_ticks
if printed_ticks != ticks & 0xffffffff:
    raise SystemExit('Official tick print does not match the full-width port timer')
mode = manifest.get('run_mode', 'performance')
if mode not in ('performance', 'validation'):
    raise SystemExit('Unexpected CoreMark run mode')
evidence_class = manifest.get('evidence_class')
if evidence_class not in ('calibration', 'formal_candidate') or \
        (args.calibration != (evidence_class == 'calibration')):
    raise SystemExit('Firmware evidence class does not match the requested check')
hz = manifest['cpu_hz']
tb_hz = re.search(r'TB_COREMARK_SOC_START cpu_hz=(\d+)', log)
if not tb_hz or int(tb_hz.group(1)) != hz:
    raise SystemExit('Testbench clock and firmware CPU frequency mismatch')
if iterations != manifest['iterations'] or manifest['coremark_sim']:
    raise SystemExit('Iteration or timing-mode mismatch')
macros = (root/'macros.txt').read_text()
if re.search(r'^#define COREMARK_SIM\b', macros, re.M):
    raise SystemExit('Timing check was disabled in the compiled firmware')
expected_seed = 'e9f5' if mode == 'performance' else '18f2'
if not re.search(r'^seedcrc\s*:\s*0x' + expected_seed + r'\b', log, re.M):
    raise SystemExit('Unexpected performance seed/data-size CRC')
if 'TB_COREMARK_SOC_PASS' not in log or 'COREMARK_DONE' not in log:
    raise SystemExit('SoC did not complete')
expected_crc = (('e714', '1fd7', '8e3a') if mode == 'performance' else ('e3c1', '0747', '8d84'))
for label, value in zip(('crclist', 'crcmatrix', 'crcstate'), expected_crc):
    if not re.search(r'\[0\]' + label + r'\s*:\s*0x'+value, log):
        raise SystemExit('CRC mismatch: '+label)
final_crc = re.search(r'\[0\]crcfinal\s*:\s*0x([0-9a-fA-F]+)', log)
if not final_crc:
    raise SystemExit('Missing final CRC')
if args.calibration and iterations == 10:
    expected_final_crc = {'performance': 'fcaf', 'validation': 'c64e'}[mode]
    if final_crc.group(1).lower() != expected_final_crc:
        raise SystemExit('CRC mismatch: crcfinal for fixed10 ' + mode)
errors = [line for line in log.splitlines() if 'ERROR!' in line or 'Errors detected' in line]
if args.calibration:
    if any('Must execute for at least 10 secs' not in x and x != 'Errors detected' for x in errors):
        raise SystemExit('Unexpected calibration error')
else:
    if ticks < hz * 10:
        raise SystemExit('Timed interval is below 10 seconds')
    if errors or 'Correct operation validated' not in log:
        raise SystemExit('CoreMark validation failed')
for name, expected in manifest['files'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
        raise SystemExit('Firmware changed: '+name)
result = {
    'status': 'CALIBRATION_ONLY' if args.calibration else 'PASS',
    'measurement': 'RTL simulation, not board measurement',
    'iterations': iterations, 'ticks': ticks, 'cpu_hz': hz,
    'run_mode': mode, 'seed_crc': expected_seed,
    'compiler': manifest['compiler'], 'compiler_flags': manifest['compiler_flags'],
    'official_source_commit': manifest.get('coremark_upstream'),
    'cpu_seconds': ticks/hz, 'at_least_10_seconds': ticks >= hz*10,
    'coremark_iterations_per_second': iterations*hz/ticks,
    'coremark_per_mhz': iterations*1000000/ticks,
    'cycles_per_iteration': ticks/iterations,
    'crc_list': expected_crc[0], 'crc_matrix': expected_crc[1], 'crc_state': expected_crc[2],
    'crc_final_reported': final_crc.group(1).lower(),
    'coremark_sim_defined': False,
    'formula': 'CoreMark/MHz = iterations / (CPU seconds * CPU MHz) = iterations * 1e6 / cycles',
}
(root/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
