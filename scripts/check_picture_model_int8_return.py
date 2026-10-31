"""Bounded offline intake of the exact reviewed model-side r01 return.

Does not train, execute a network, load a device, or modify the incoming ZIP.
Only the hash-pinned, statically reviewed oracle/harness are executed, against
the original handoff source snapshot rather than today's dirty source tree.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import sys
import zipfile

from picture_workspace import ROOT, workspace_path, wsl_path


RETURN_SHA = '3a1734637b009299db623ac825503d850f0c0cb821bbbd1e5cc383bdbbdf7666'
HANDOFF_SHA = 'b4d35ee19b457603ea722a8c3fd8469965462c6dc53a718e16a7dad36cc5ddf4'
INCLUDES = ['linux/picture_new/hwc_fast', 'linux/picture_new', 'linux/vision',
            'linux/mac_accel', 'artifacts/vision-model-20261020-adapter/runtime',
            'sw/bootloader']
WIDTH = {'q_cases': 8, 'fq_cases': 8, 'two_level_cases': 8, 'pack_cases': 8,
         'pre_cases': 16, 'add_cases': 16, 'concat_cases': 16,
         'near_cases': 16, 'conv_cases': 16, 'export_cases': 32}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def extract_verified(path, expected_sha, out):
    data = path.read_bytes()
    assert sha(data) == expected_sha, 'Archive differs from reviewed identity'
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert len(names) == len(set(names)) < 500
        assert sum(i.file_size for i in z.infolist()) < 64 * 1024 * 1024
        assert z.testzip() is None
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            assert not p.is_absolute() and '..' not in p.parts
            assert '\\' not in item.filename and ':' not in item.filename
            assert not stat.S_ISLNK(item.external_attr >> 16)
        sums = {}
        for line in z.read('SHA256SUMS.txt').decode().splitlines():
            if line.strip():
                digest, name = line.split(None, 1)
                name = name.lstrip('*')
                assert name not in sums
                sums[name] = digest
        assert set(sums) == set(names) - {'SHA256SUMS.txt'}
        for name, digest in sums.items():
            assert sha(z.read(name)) == digest
        out.mkdir()
        for name in names:
            dest = out.joinpath(*PurePosixPath(name).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(name))
    return dict(sha256=expected_sha, bytes=len(data), members=len(names),
                hashed_payloads=len(sums), hashes_crc_safe_paths=True)


def flat(value):
    if isinstance(value, list):
        return [n for v in value for n in flat(v)]
    return [value]


def compare(expected, actual):
    assert actual.keys() == expected.keys(), 'Missing or extra section'
    counts = {}
    for key, exp in expected.items():
        act = actual[key]
        if exp == 'MUST_FAIL':
            assert act == 1 and type(act) in (int, bool), key
            counts[key] = 1
            continue
        assert len(exp) == len(act), key
        mask = (1 << WIDTH[key]) - 1
        total = 0
        for e, a in zip(exp, act):
            ev, av = flat(e), flat(a)
            assert len(ev) == len(av), key
            assert all((int(x) & mask) == (int(y) & mask) for x, y in zip(ev, av)), key
            total += len(ev)
        counts[key] = total
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--return-zip', type=Path, required=True)
    ap.add_argument('--handoff-zip', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = workspace_path(args.output)
    assert out.is_relative_to((ROOT / 'build/picture-e42-20261025').resolve())
    out.mkdir(exist_ok=False)
    result = dict(status='FAILED_PRESERVED', hardware_used=False,
                  training_or_calibration=False, full_network_executed=False,
                  production_sources_modified=False, checks=[], findings=[])
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))

    def run(name, command):
        # A finite command, not a watcher/retry loop. Save only bounded output.
        proc = subprocess.run(command, capture_output=True, timeout=50)
        assert len(proc.stdout) + len(proc.stderr) < 1024 * 1024
        (out / (name + '.stdout')).write_bytes(proc.stdout)
        (out / (name + '.stderr')).write_bytes(proc.stderr)
        result['checks'].append(dict(name=name, exit_code=proc.returncode))
        assert proc.returncode == 0, (name, proc.returncode)
        return proc.stdout

    def wsl(name, command):
        return run(name, ['wsl.exe', '-d', 'Ubuntu-22.04', '--', 'sh', '-c',
                         'ulimit -c 0\nexec timeout 35s ' + shlex.join(command)])

    try:
        incoming, handoff = out / 'return-original', out / 'handoff-original'
        result['return_archive'] = extract_verified(args.return_zip, RETURN_SHA, incoming)
        result['handoff_archive'] = extract_verified(args.handoff_zip, HANDOFF_SHA, handoff)
        manifest = load(incoming / 'return-manifest.json')
        assert manifest['received_archive_sha256'] == HANDOFF_SHA
        inv = load(handoff / 'baseline-inventory.json')
        candidate = load(incoming / 'candidate-contract.json')
        assert candidate['status'] == 'DESIGN_ONLY_NOT_TRAINED'
        assert candidate['baseline_model_sha256'] == {
            n: g['sha256'] for n, g in inv['graphs'].items()}
        graph_names = {'board.xqm': 'board(xqm)', 'classifier.xqm': 'classifier(xqm)',
                       'detector.xqm': 'detector(xqm)', 'detector.xqi': 'detector(xqi-exec)'}
        rows = list(csv.DictReader(io.StringIO((incoming / 'tensor-contracts.csv').read_text(encoding='utf-8-sig'))))
        assert len(rows) == 200
        by_node = {(r['graph'], int(r['node'])): r for r in rows}
        assert len(by_node) == len(rows)
        for name, g in inv['graphs'].items():
            for n in g['nodes']:
                row = by_node[graph_names[name], n['index']]
                assert row['op'] == n['operation']
                assert row['shape_CHW'] == 'x'.join(map(str, n['shape_chw']))
                assert row['parents'] == ';'.join(map(str, n['parents']))
                assert row['consumers'] == (';'.join(map(str, n['consumers'])) or ('OUTPUT' if n['is_output'] else ''))
                if name.endswith('xqi'):
                    assert int(row['storage_bits']) == n['storage_bits']
                    assert int(row['output_exponent']) == n['output_exponent']
                    assert int(row['logical_output_bytes']) == n['logical_output_bytes']
                if n['operation'] == 'conv':
                    assert int(row['K']) == n['k']
                    assert int(row['dense_macs']) == n['dense_macs']
        result['tensor_contract_rows_verified'] = len(rows)
        result['tensor_contract_verification_scope'] = 'identity/topology/shape/K/MAC and XQI dtype/exponent/bytes only; XQM storage/layout prose not accepted'
        result['xqm_rows_with_incorrect_hwc_layout'] = sum(
            r['graph'].endswith('(xqm)') and r['layout'].startswith('HWC') for r in rows)
        assert result['xqm_rows_with_incorrect_hwc_layout'] == 115
        nodes = inv['graphs']['detector.xqi']['nodes']
        stats = load(incoming / 'audit_stats.json')
        assert stats['detector_dense_macs_640'] == sum(n.get('dense_macs', 0) for n in nodes)
        assert stats['detector_dense_macs_512_est'] * 25 == stats['detector_dense_macs_640'] * 16
        assert stats['s8_nodes'] == Counter(n['storage_bits'] for n in nodes)[8] == 69
        assert stats['s16_nodes'] == 16
        for bits in (8, 16):
            assert stats['logical_S%d_bytes' % bits] == sum(n['logical_output_bytes'] for n in nodes if n['storage_bits'] == bits)
        tensors = {t['id']: t for t in candidate['tensors']}
        layers = {l['id']: l for l in candidate['layers']}
        assert len(layers) == len(tensors) == len(nodes) == 85
        dangling = [(t['id'], c) for t in tensors.values() for c in t['consumers']
                    if c not in layers and c != 'HEAD_EXPORT']
        result['candidate_dangling_consumer_refs'] = len(dangling)
        result['candidate_dangling_consumer_examples'] = dangling[:4]
        for n, layer, tensor in zip(nodes, candidate['layers'], candidate['tensors']):
            c, h, w = n['shape_chw']
            assert tensor['shape'] == [1, c, h * 4 // 5, w * 4 // 5]
            assert layer['op'] == n['operation']
            assert all(t in tensors or t == 'INPUT' for t in layer['input_tensor_ids'])
        result['candidate_shapes_ops_inputs_verified'] = 85
        run('oracle-regenerate', [sys.executable, '-X', 'utf8', '-B',
                                 str(incoming / 'synthetic_reference/oracle.py'), str(out / 'regenerated')])
        vectors = incoming / 'synthetic_reference/run/vectors.bin'
        assert (out / 'regenerated/vectors.bin').read_bytes() == vectors.read_bytes()
        expected = load(incoming / 'synthetic_reference/run/expected.json')
        assert load(out / 'regenerated/expected.json') == expected
        source = handoff / 'current-source'
        flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Wno-misleading-indentation',
                 '-ffp-contract=off', '-ffunction-sections', '-fdata-sections']
        flags += ['-I' + wsl_path(source / n) for n in INCLUDES]
        result['numeric_targets'] = []
        for target in ('host', 'rv32', 'asan-ubsan'):
            exe = out / ('harness-' + target)
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target == 'rv32' else 'cc'
            extra = ['-static', '-march=rv32ima', '-mabi=ilp32', '-mstrict-align'] if target == 'rv32' else []
            if target == 'asan-ubsan':
                extra += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            wsl(target + '-build', [cc, *flags, *extra,
                wsl_path(incoming / 'synthetic_reference/harness.c'),
                '-Wl,--gc-sections', '-lm', '-o', wsl_path(exe)])
            prefix = ['qemu-riscv32'] if target == 'rv32' else []
            actual = json.loads(wsl(target + '-run', [*prefix, wsl_path(exe), wsl_path(vectors)]))
            counts = compare(expected, actual)
            result['numeric_targets'].append(dict(target=target, sections=len(counts),
                compared_values=sum(counts.values()), values_by_section=counts, exact_equal=True))
        submitted_report = load(incoming / 'synthetic_reference/run/report.json')
        assert submitted_report['values_compared'] == counts
        result['independent_regeneration_matches_returned_vectors_expected'] = True
        result['numeric_value_count'] = sum(counts.values())
        # Ensure this independent comparator rejects data corruption and loss.
        corrupted = json.loads(json.dumps(expected))
        corrupted['q_cases'][0] ^= 1
        for name, bad in [('changed-value', corrupted), ('missing-section', {k:v for k,v in expected.items() if k != 'q_cases'})]:
            try:
                compare(expected, bad)
            except AssertionError:
                result['checks'].append(dict(name='negative-' + name, rejected=True))
            else:
                raise AssertionError('Comparator accepted ' + name)
        result['findings'] = [
            'Design contract has 106 dangling tensor consumer layer IDs; not executable-ready.',
            '115 XQM-view CSV rows incorrectly claim HWC; the ordinary runtime carrier is NCHW and selected S16/GAP cannot be inferred from reserved dtype fields.',
            'Report prose says 2583 values; actual report and independent replay total 2683.',
            'Probability threshold 0.001 is not a required logit step; sigmoid/confidence products must be analysed.',
            'S16 metadata bound 32768 is not evidence that observed logits fill the entire representable range.',
            '5836800 aggregate logical S16 bytes narrow to 2918400 logical S8 bytes; savings are not 5836800 and are not peak/DDR bytes; overlap with existing Concat views must be excluded.',
            'xi8_export_f32 is dimension-generic; fixed grids are enforced by outer adapter/decoder contracts.',
            'xqr_letterbox_plan explicitly rejects side 512; it is another candidate integration boundary.',
            'Classifier crops original RGB; reducing detector size does not directly rescale classifier source pixels.',
            'No new weights, exporter, truth evaluation or deployable candidate was returned.',
        ]
        assert sha(args.return_zip.read_bytes()) == RETURN_SHA
        assert sha(args.handoff_zip.read_bytes()) == HANDOFF_SHA
        result.update(status='PHASE_A_PARTIAL_ACCEPT_NUMERIC_REPRODUCED_CONTRACT_CORRECTIONS_REQUIRED',
                      candidate_accepted_for_deployment=False, quality_or_board_speed_proven=False)
    finally:
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(result['status'])
    print('targets=host,rv32,asan-ubsan values_per_target=%d dangling_consumers=%d' %
          (result['numeric_value_count'], result['candidate_dangling_consumer_refs']))


if __name__ == '__main__':
    main()
