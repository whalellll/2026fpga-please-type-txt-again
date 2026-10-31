"""Review the pinned r02 model return offline against its original handoff.

No training, full-network inference or device access. Only the statically read,
hash-pinned oracle and C harness run, with finite command timeouts. Original
archives and the r01 checker stay unchanged.
"""
import argparse
from collections import Counter
import copy
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

from check_picture_model_int8_return import extract_verified, flat, INCLUDES, HANDOFF_SHA
from picture_workspace import ROOT, workspace_path, wsl_path


RETURN_SHA = 'cb471ad3500975fe1101645600af6b4f5f715e55598805f7f7fe928a6dcdc307'
R01_SHA = '3a1734637b009299db623ac825503d850f0c0cb821bbbd1e5cc383bdbbdf7666'
PREFIX = 'xinyi_model_int8_r02_return/'
WIDTH = {'q_cases': 8, 'fq_cases': 8, 'pack_cases': 8, 'tlc_case': 8,
         'pre_cases': 16, 'add_cases': 16, 'concat_cases': 16,
         'near_cases': 16, 'conv_cases': 16, 'export_cases': 32}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_return(path, out):
    assert sha(path) == RETURN_SHA, 'Unreviewed archive'
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert len(names) == len(set(names)) == 17
        assert sum(i.file_size for i in z.infolist()) == 400728
        assert z.testzip() is None
        for item in z.infolist():
            name = item.filename
            p = PurePosixPath(name)
            assert name.startswith(PREFIX) and not p.is_absolute()
            assert '..' not in p.parts and ':' not in name and '\\' not in name
            assert not stat.S_ISLNK(item.external_attr >> 16)
        sums = {}
        for line in z.read(PREFIX + 'SHA256SUMS.txt').decode().splitlines():
            digest, name = line.split(None, 1)
            name = name.lstrip('*')
            assert name not in sums
            sums[name] = digest
        assert set(names) == {PREFIX + n for n in sums} | {PREFIX + 'SHA256SUMS.txt'}
        for name, digest in sums.items():
            assert hashlib.sha256(z.read(PREFIX + name)).hexdigest() == digest
        out.mkdir()
        for name in names:
            dest = out.joinpath(*PurePosixPath(name[len(PREFIX):]).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(name))
    return dict(sha256=RETURN_SHA, bytes=path.stat().st_size, members=17,
                hashed_payloads=16, crc_hashes_paths_coverage_pass=True)


def validate_contract(c, inv):
    assert c['status'] == 'DESIGN_ONLY_NOT_TRAINED'
    assert c['baseline_model_sha256'] == {k:v['sha256'] for k,v in inv['graphs'].items()}
    nodes = inv['graphs']['detector.xqi']['nodes']
    layers = {l['id']: l for l in c['layers']}
    tensors = {t['id']: t for t in c['tensors']}
    assert len(layers) == len(c['layers']) == len(tensors) == len(c['tensors']) == 85
    lid = lambda i: 'INPUT' if i < 0 else 'det%02d_%s' % (i, nodes[i]['operation'])
    tid = lambda i: 'INPUT' if i < 0 else 't_' + lid(i)
    order = {l['id']: i for i,l in enumerate(c['layers'])}
    for n in nodes:
        i = n['index']; l = layers[lid(i)]; t = tensors[tid(i)]
        assert l['op'] == n['operation'] and l['output_tensor_id'] == t['id']
        assert t['producer'] == l['id']
        assert l['input_tensor_ids'] == [tid(p) for p in n['parents']]
        expected = [lid(p) for p in n['consumers']]
        if n['is_output']:
            expected += ['HEAD_EXPORT']
        assert t['consumers'] == expected, 'Missing/extra/backward consumer'
        for p in n['parents']:
            if p >= 0:
                assert order[lid(p)] < order[l['id']]
                assert l['id'] in tensors[tid(p)]['consumers']
        for consumer in t['consumers']:
            if consumer != 'HEAD_EXPORT':
                assert t['id'] in layers[consumer]['input_tensor_ids']
        ch,h,w = n['shape_chw']
        assert h * 4 % 5 == w * 4 % 5 == 0
        assert t['shape'] == [1,ch,h*4//5,w*4//5]
        assert t['scale_or_exponent'].startswith('TBD')
        assert t['baseline_reference'] == dict(output_exponent=n['output_exponent'], storage_bits=n['storage_bits'])
        if n['operation'] == 'conv':
            assert l['k'] == n['k'] <= 1152 and n['shape_chw'][0] <= 256
            for field,key in [('kernel','kernel_hw'),('stride','stride_hw'),('dilation','dilation_hw')]:
                assert l[field] == n[key]
            assert l['multiplier'] == 1 and l['right_shift'].startswith('TBD')
            assert l['lut_sha256'] == ('TBD (Phase B regeneration)' if n['lut_bytes'] else None)
    outs = [tid(i) for i in inv['graphs']['detector.xqi']['output_nodes']]
    assert [o['tensor_id'] for o in c['outputs']] == outs
    assert [o['shape'] for o in c['outputs']] == [tensors[t]['shape'] for t in outs]
    assert c['input']['side'] == 512 and c['input']['exponent'].startswith('TBD')
    assert c['training_or_calibration_authorization'] is None
    assert c['authorized_data_identity'] is None
    assert c['quality_test_status'] == c['device_test_status'] == c['numeric_test_status'] == 'NOT_RUN'
    assert c['geometry_thresholds_unchanged'] and c['estimated_recommendations_preserved']
    return dict(layers=85, tensors=85, bidirectional_edges=sum(len(n['consumers']) for n in nodes),
                unresolved_or_extra_consumer_refs=0, topology_shapes_and_baseline_bindings_pass=True)


def compare(expected, actual):
    keys = (set(expected) - {'fq_fail_bits','tlc_negative_control'}) | {'fq_fail'}
    assert set(actual) == keys, 'Missing/extra actual section'
    assert expected['fq_fail_bits'] == [0x7fc00000, 0x7f800000, 0xff800000]
    assert actual['fq_fail'] == [1,1,1], 'Non-finite input accepted'
    counts = {'fq_fail': 3}
    for key in keys - {'fq_fail'}:
        exp, act = expected[key], actual[key]
        if exp == 'MUST_FAIL':
            assert act == 1 and type(act) in (int,bool)
            counts[key] = 1
            continue
        assert len(exp) == len(act), key
        mask = (1 << WIDTH[key]) - 1
        count = 0
        for e,a in zip(exp,act):
            ev,av = flat(e),flat(a)
            assert len(ev) == len(av), key
            assert all((int(x)&mask) == (int(y)&mask) for x,y in zip(ev,av)), key
            count += len(ev)
        counts[key] = count
    nocast = expected['tlc_negative_control']['nocast_values']
    assert expected['tlc_negative_control']['must_differ'] is True
    assert len(nocast) == len(actual['tlc_case']) == 48
    diff = sum((int(x)&255) != (int(y)&255) for x,y in zip(nocast,actual['tlc_case']))
    assert diff == 7, 'Storage-cast control not exercised'
    assert sum(counts.values()) == 2710
    return counts,diff


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--return-zip', type=Path, required=True)
    ap.add_argument('--handoff-zip', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(exist_ok=False)
    result = dict(status='FAILED_PRESERVED', hardware_used=False, full_network_executed=False,
                  training_or_calibration=False, production_sources_modified=False, checks=[])
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))

    def run(name, command):
        p = subprocess.run(command, capture_output=True, timeout=50)
        assert len(p.stdout)+len(p.stderr) < 1024*1024
        (out/(name+'.stdout')).write_bytes(p.stdout)
        (out/(name+'.stderr')).write_bytes(p.stderr)
        result['checks'].append(dict(name=name, exit_code=p.returncode))
        assert p.returncode == 0, (name,p.returncode)
        return p.stdout

    def wsl(name, command):
        return run(name,['wsl.exe','-d','Ubuntu-22.04','--','sh','-c',
                        'ulimit -c 0\nexec timeout 35s '+shlex.join(command)])

    try:
        incoming,handoff = out/'return-original',out/'handoff-original'
        result['return_archive'] = extract_return(a.return_zip,incoming)
        result['handoff_archive'] = extract_verified(a.handoff_zip,HANDOFF_SHA,handoff)
        manifest = load(incoming/'return-manifest.json')
        assert manifest['source_r01_archive_sha256'] == R01_SHA
        assert manifest['source_original_handoff_sha256'] == HANDOFF_SHA
        sums = set()
        for line in (incoming/'SHA256SUMS.txt').read_text().splitlines():
            sums.add(line.split(None,1)[1])
        assert set(manifest['files']) == sums - {'return-manifest.json'}
        inv = load(handoff/'baseline-inventory.json')
        c = load(incoming/'candidate-contract.json')
        result['candidate_contract'] = validate_contract(c,inv)
        rows = list(csv.DictReader(io.StringIO((incoming/'tensor-contracts.csv').read_text(encoding='utf-8'))))
        lookup = {(r['graph'],int(r['node'])):r for r in rows}
        assert len(lookup) == len(rows) == 200
        for name,g in inv['graphs'].items():
            for n in g['nodes']:
                row = lookup[name,n['index']]
                assert row['op'] == n['operation']
                assert row['shape_CHW'] == 'x'.join(map(str,n['shape_chw']))
                assert row['parents'] == ';'.join(map(str,n['parents']))
                assert row['consumers'] == (';'.join(map(str,n['consumers'])) or ('OUTPUT' if n['is_output'] else ''))
                if name.endswith('.xqi'):
                    for key,nkey in [('storage_bits','storage_bits'),('output_exponent','output_exponent'),('logical_output_bytes','logical_output_bytes')]:
                        assert int(row[key]) == n[nkey]
                    assert row['layout'].startswith('HWC')
                else:
                    assert row['layout'].startswith('NCHW') and row['storage_bits'] == 'n/a (XQM view)'
                if n['operation'] == 'conv':
                    assert int(row['K']) == n['k'] and int(row['dense_macs']) == n['dense_macs']
        assert lookup['classifier.xqm',7]['classification'] == 'C_cls_S16_GAP_path'
        result['csv_rows_verified'] = 200
        nodes = inv['graphs']['detector.xqi']['nodes']
        stats = load(incoming/'audit_stats.json')
        addcat = [n for n in nodes if n['storage_bits']==16 and n['operation'] in ('add','concat')]
        logical = sum(n['logical_output_bytes'] for n in addcat)
        assert len(addcat) == 13 and logical == stats['add_concat_S16_logical_bytes'] == 5836800
        assert logical//2 == stats['add_concat_narrowing_logical_delta'] == 2918400
        assert stats['detector_dense_macs_640'] == inv['graphs']['detector.xqi']['dense_conv_linear_macs'] == 2092134400
        assert stats['detector_dense_macs_512_est'] == 1338966016
        # Frozen descriptor selection corresponding to the reviewed concat planner.
        views = [n for n in nodes if n['operation']=='concat' and n['consumers']==[n['index']+1]
                 and nodes[n['index']+1]['operation']=='conv'
                 and nodes[n['index']+1]['parents']==[n['index']]
                 and all(0 <= nodes[p]['output_exponent']-n['output_exponent'] <= 32-nodes[p]['storage_bits'] for p in n['parents'])]
        s16views = [n for n in views if n['storage_bits']==16]
        assert len(views)==9 and len(s16views)==5
        assert sum(n['logical_output_bytes'] for n in views)==4300800
        overlap = sum(n['logical_output_bytes'] for n in s16views)
        assert overlap == 3276800
        result['logical_memory_accounting'] = dict(view_pairs=9, s16_view_pairs=5,
            s8_view_pairs=4, eligible_view_nodes=[n['index'] for n in views],
            eligible_s16_view_nodes=[n['index'] for n in s16views],
            remaining_materialized_s16_concat_nodes=[n['index'] for n in addcat if n['operation']=='concat' and n not in s16views],
            all_view_elided_bytes=4300800, s16_view_elided_bytes=overlap,
            hypothetical_extra_s16_to_s8_logical_delta_after_views=(logical-overlap)//2,
            allocation_peak_ddr_or_speedup_measured=False)
        run('oracle-regenerate',[sys.executable,'-X','utf8','-B',str(incoming/'synthetic_reference/oracle.py'),str(out/'regenerated')])
        vectors = incoming/'synthetic_reference/r02_run/vectors.bin'
        assert vectors.read_bytes() == (out/'regenerated/vectors.bin').read_bytes()
        expected = load(incoming/'synthetic_reference/r02_run/expected.json')
        assert expected == load(out/'regenerated/expected.json')
        source = handoff/'current-source'
        flags = ['-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation',
                 '-ffp-contract=off','-ffunction-sections','-fdata-sections']
        flags += ['-I'+wsl_path(source/p) for p in INCLUDES]
        result['numeric_targets'] = []
        for target in ('host','rv32','asan-ubsan'):
            cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc' if target=='rv32' else 'cc'
            extra = ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'] if target=='rv32' else []
            if target=='asan-ubsan':
                extra += ['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            exe = out/('harness-'+target)
            wsl(target+'-build',[cc,*flags,*extra,wsl_path(incoming/'synthetic_reference/harness.c'),
                               '-Wl,--gc-sections','-lm','-o',wsl_path(exe)])
            prefix = ['qemu-riscv32'] if target=='rv32' else []
            actual = json.loads(wsl(target+'-run', [*prefix,wsl_path(exe),wsl_path(vectors)]))
            counts,diff = compare(expected,actual)
            result['numeric_targets'].append(dict(target=target, actual_sections=12,
                numeric_and_return_status_values=sum(counts.values()),derived_storage_cast_control_differences=diff,
                values_by_section=counts,exact_equal=True))
        for name,mut in [('changed-bit',lambda a:a['q_cases'].__setitem__(0,a['q_cases'][0]^1)),
                         ('missing-section',lambda a:a.pop('q_cases')),
                         ('nonfinite-accepted',lambda a:a['fq_fail'].__setitem__(0,0))]:
            bad = copy.deepcopy(actual);mut(bad)
            try: compare(expected,bad)
            except AssertionError: result['checks'].append(dict(name='negative-'+name,rejected=True))
            else: raise AssertionError('Accepted '+name)
        bad = copy.deepcopy(c);bad['tensors'][0]['consumers'].append('det02_conv')
        try: validate_contract(bad,inv)
        except AssertionError: result['checks'].append(dict(name='negative-spurious-consumer',rejected=True))
        else: raise AssertionError('Accepted spurious consumer')
        report = load(incoming/'synthetic_reference/r02_run/report.json')
        numeric_report_counts = {('fq_fail' if k=='fq_fail_bits' else k):v for k,v in report['values_compared'].items() if k!='tlc_negative_control'}
        assert numeric_report_counts == counts
        result['reported_values_sum_including_derived_control'] = sum(report['values_compared'].values())
        result['engineering_clarifications'] = [
            '2710 actual numeric/return-status values in 12 C-output sections, plus one derived no-cast negative control (7 differences); report JSON includes that control and sums to 2711.',
            'Nine existing Concat views include five S16 and four S8; S16 overlap is 3276800 bytes. Shared-consumer S16 concat node75 stays materialized. After excluding views, hypothetical further storage narrowing is 1280000 logical bytes before changed reuse/allocation effects.',
            'xi8_load also assumes 640 for first-layer shape validation, before input_load/run; do not bypass it to accept a 512 candidate.',
            'Sigmoid p(1-p)*delta/2 is a local approximation, not a rigorous finite-step upper bound; use an exact interval or global derivative <=1/4 when a bound is needed.',
        ]
        assert sha(a.return_zip)==RETURN_SHA and sha(a.handoff_zip)==HANDOFF_SHA
        result.update(status='PHASE_A_R02_ACCEPTED_WITH_ENGINEERING_CLARIFICATIONS_NOT_A_TRAINED_MODEL',
                      candidate_accepted_for_deployment=False, quality_or_board_speed_proven=False)
    finally:
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'])
    print('3 targets x 2710 values; 12 actual sections + cast control; dangling refs=0')


if __name__=='__main__':main()
