"""Validate private clean-shot records and write a redacted latency summary."""
import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

FIELDS = re.compile(r'(\w+)=([^\s]+)')


def fields(line):
    return {k: int(v) if v.isdigit() else v for k, v in FIELDS.findall(line)}


def lines(raw):
    # Background GUI messages may begin after one or more shell prompts.
    # Strip only those known prefixes; retain strict record names/identities.
    for line in raw.splitlines():
        while line.startswith('/ # '):
            line = line[4:]
        yield line


def parse_sample(directory):
    meta = json.loads((directory / 'sample.json').read_text(encoding='utf-8'))
    raw = (directory / 'completed.txt').read_text(encoding='utf-8')
    records = list(lines(raw))
    gui = [fields(s) for s in records if s.startswith('XQ_PICTURE_LATENCY ')]
    requests = [fields(s) for s in records if s.startswith('XQ_MODEL_REQUEST ')]
    assert len(gui) == len(requests) == 1, 'Not exactly one fresh capture/request/outcome'
    gui = gui[0]
    assert gui['valid'] == 1 and gui['token'] == requests[0]['token'], 'GUI timer/identity mismatch'
    assert requests[0]['backend'] == 'rv32-driver-quantized-mac', 'Wrong backend'
    recognition = None
    selected = []
    for line in records:
        if line.startswith('XQ_NATIVE_RECOGNITION '):
            recognition = fields(line)
        elif line.startswith('XQ_NATIVE_TIMING '):
            timing = fields(line)
            if timing['token'] == gui['token']:
                assert recognition is not None
                selected.append((recognition, timing))
    assert len(selected) == 1, 'Missing or duplicate matching worker timing'
    rec, timing = selected[0]
    assert timing['valid'] == 1 and timing['observer_checks'] == 0
    assert rec['cpu_reference'] == 0 and rec['executed_mask'] == 7, 'Not a complete native three-model run'
    assert timing['ioctl_errors'] == 0
    assert timing['jobs'] == rec['jobs'] and timing['cycles'] == rec['cycles']
    phases = ('prepare', 'graph', 'post', 'refine', 'assign')
    phase_sum = sum(timing[p + '_us'] for p in phases)
    assert 0 <= timing['worker_us'] - phase_sum <= 5, 'Worker phases do not close'
    busy_ms = timing['cycles'] / 49500
    assert busy_ms <= timing['driver_us'] / 1000 <= timing['graph_us'] / 1000
    ipc_exclusive = gui['ipc_inclusive_ms'] - timing['worker_us'] / 1000
    gui_other = gui['total_ms'] - gui['capture_ms'] - gui['ipc_inclusive_ms']
    assert ipc_exclusive >= -1 and gui_other >= 0
    if rec['status']:
        assert gui['terminal'] == 'model_rejected'
    else:
        assert gui['terminal'] == 'model_validated'
    # Deliberate allowlist: no photo IDs, tokens, CRCs, corners, FEN or raw IPC.
    return dict(pair=meta['pair'], group=meta['group'], status=rec['status'],
                terminal=gui['terminal'], jobs=timing['jobs'], cycles=timing['cycles'],
                registrations=timing['registrations'], capture_ms=gui['capture_ms'],
                **{p + '_ms': timing[p + '_us'] / 1000 for p in phases},
                driver_ms=timing['driver_us'] / 1000, busy_ms=busy_ms,
                ipc_inclusive_ms=gui['ipc_inclusive_ms'], ipc_exclusive_ms=ipc_exclusive,
                gui_other_ms=gui_other, total_ms=gui['total_ms'],
                capture_retries=sum(s.startswith('XQ_PICTURE_CAPTURE_RETRY ') for s in records))


def distribution(rows):
    names = ('capture_ms', 'prepare_ms', 'graph_ms', 'driver_ms', 'busy_ms',
             'post_ms', 'refine_ms', 'assign_ms', 'ipc_inclusive_ms',
             'ipc_exclusive_ms', 'gui_other_ms', 'total_ms')
    return {name: dict(p50=statistics.median(r[name] for r in rows),
                       p95=sorted(r[name] for r in rows)[math.ceil(.95 * len(rows)) - 1])
            for name in names} if rows else None


def summarize(rows):
    assert rows
    unique = {(r['pair'], r['group']) for r in rows}
    assert len(unique) == len(rows), 'Duplicate pair/group'
    groups = {}
    for name in ('cold', 'warm'):
        group = [r for r in rows if r['group'] == name]
        successful = [r for r in group if r['status'] == 0]
        rejected = [r for r in group if r['status'] != 0]
        groups[name] = dict(n=len(group), native_status0=len(successful), rejected=len(rejected),
            all_terminal_outcomes=distribution(group), status0_outcomes=distribution(successful),
            rejection_outcomes=distribution(rejected),
            limits_ms={str(limit): dict(within_limit=sum(r['total_ms'] <= limit for r in group),
                status0_within_limit=sum(r['total_ms'] <= limit for r in successful),
                p95_status0_pass=bool(successful) and distribution(successful)['total_ms']['p95'] <= limit)
                for limit in (10000, 5000, 3000)})
    return dict(status='MEASURED', production_ready=False, full_integer_pipeline=False,
        scope='real fresh capture through displayed recognition outcome; software FIFO trigger',
        physical_space_acceptance=False, quantile='P50 median; P95 empirical nearest rank; small n is not a tail guarantee',
        cold_definition='first capture after worker+GUI restart; loaded models; startup excluded; not power-on cold',
        nesting='graph includes driver; driver includes busy; IPC inclusive includes worker phases; never add nested columns',
        timer_overhead='included; no diagnostic SHA/observer/tensor export; clock calibration reported separately',
        status0_is_accuracy_acceptance=False, groups=groups, samples=rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--samples', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert not a.out.exists(), 'Use a fresh summary path'
    result = summarize([parse_sample(d) for d in a.samples])
    result['analyzer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('CLEAN_LATENCY_SUMMARY_PASS samples=' + str(len(result['samples'])))


if __name__ == '__main__':
    main()
