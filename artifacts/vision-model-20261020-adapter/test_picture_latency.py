"""Synthetic receipt tests; no device, images or model inference."""
import json
import tempfile
from pathlib import Path
from analyze_picture_latency import parse_sample, summarize

RAW = '''XQ_MODEL_REQUEST token=19 frame=123 crc=deadbeef backend=rv32-driver-quantized-mac EXPERIMENTAL
XQ_PICTURE_LATENCY token=19 valid=1 terminal=model_rejected capture_ms=40 ipc_inclusive_ms=1100 mapping_ms=0 total_ms=1200
XQ_NATIVE_RECOGNITION status=5 executed_mask=7 cpu_reference=0 jobs=50 cycles=4950000
XQ_NATIVE_TIMING token=19 valid=1 observer_checks=0 prepare_us=100000 graph_us=700000 driver_us=500000 post_us=100000 refine_us=100000 assign_us=0 worker_us=1000000 ioctl_calls=51 registrations=1 ioctl_errors=0 jobs=50 cycles=4950000
'''


def main():
    with tempfile.TemporaryDirectory(prefix='xq-latency-test-') as temp:
        d = Path(temp)
        (d / 'sample.json').write_text(json.dumps(dict(pair=1, group='cold')), encoding='utf-8')
        def parse(text):
            (d / 'completed.txt').write_text(text, encoding='utf-8')
            return parse_sample(d)
        row = parse(RAW)
        assert parse('/ # / # ' + RAW) == row
        assert row['ipc_exclusive_ms'] == 100 and row['gui_other_ms'] == 60
        result = summarize([row])
        group = result['groups']['cold']
        assert group['rejected'] == 1 and group['status0_outcomes'] is None
        assert not group['limits_ms']['10000']['p95_status0_pass']
        assert not any(s in json.dumps(result) for s in ('token', 'frame', 'deadbeef'))
        cases = [
            RAW.replace('TIMING token=19', 'TIMING token=18'),
            RAW.replace('observer_checks=0', 'observer_checks=1'),
            RAW.replace('cpu_reference=0', 'cpu_reference=1'),
            RAW.replace('executed_mask=7', 'executed_mask=3'),
            RAW.replace('cycles=4950000', 'cycles=49500000'),
            RAW.replace('worker_us=1000000', 'worker_us=1000100'),
            RAW.replace('ioctl_errors=0', 'ioctl_errors=1'),
            RAW.replace('jobs=50 cycles=4950000\n', 'jobs=51 cycles=4950000\n', 1),
            RAW + RAW,
        ]
        for i, text in enumerate(cases):
            try:
                parse(text)
            except AssertionError:
                pass
            else:
                raise AssertionError('Unsafe receipt accepted: ' + str(i))
        good = parse(RAW.replace('status=5', 'status=0').replace('model_rejected', 'model_validated'))
        assert summarize([good])['groups']['cold']['native_status0'] == 1
    print('PICTURE_LATENCY_RECEIPT_TEST_PASS identity observer CPU partial_graph timing errors duplicate privacy rejection_split')


if __name__ == '__main__':
    main()
