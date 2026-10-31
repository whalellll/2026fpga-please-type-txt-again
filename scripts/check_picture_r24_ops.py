"""Check unchanged r24 synthetic vectors against integer-only C operators.

The delivered generator is never executed or imported (it writes in place).
Sigmoid tables here are TEST fixtures from its documented formula, not frozen
production exports. Report conflicts as failures; never rewrite expected data.
"""
import argparse
import json
import math
from pathlib import Path
import re
import struct
import sys
import check_picture_integer_graph as common

TYPES = {'residual_add': 8, 'concat': 7, 'nearest_upsample': 5,
         'bilinear_upsample': 6, 'sigmoid': 3, 'maxpool': 4, 'gap': 9, 'relu': 11}


def even_shift(value, shift):
    if not shift:
        return value
    q, r = divmod(abs(value), 1 << shift)
    if r*2 > 1 << shift or (r*2 == 1 << shift and q % 2):
        q += 1
    return -q if value < 0 else q


def spec_result(op, v):
    """Independent arithmetic for the two identified delivery conflicts."""
    if op == 'concat':
        return [even_shift(x, v['e_common']-br['exponent'])
                for br in v['branches'] for x in br['data']]
    if op == 'bilinear_upsample':
        out = []
        for c in range(v['c']):
            for y in range(v['h']*2):
                sy = max(0, 2*y-1);y0, fy = divmod(sy, 4);y1 = min(y0+1, v['h']-1)
                for x in range(v['w']*2):
                    sx = max(0, 2*x-1);x0, fx = divmod(sx, 4);x1 = min(x0+1, v['w']-1)
                    p = lambda yy, xx: v['data'][c*v['h']*v['w']+yy*v['w']+xx]
                    total = ((4-fy)*(4-fx)*p(y0,x0)+(4-fy)*fx*p(y0,x1)+
                             fy*(4-fx)*p(y1,x0)+fy*fx*p(y1,x1))
                    out.append(max(-32768, min(32767, even_shift(total, 4))))
        return out
    return v['expected']


def input_views(op, v):
    def one(data, e, c=1, h=1, w=None):
        return ([1,c,h,len(data) if w is None else w,e,len(data)], data)
    if op == 'residual_add':
        return [one(v['a'],v['e_a']),one(v['b'],v['e_b'])], [1,1,1,len(v['a'])],v['e_out']
    if op == 'concat':
        views = [one(br['data'],br['exponent'],br['channels'],v['hw'],v['hw']) for br in v['branches']]
        return views,[1,sum(br['channels'] for br in v['branches']),v['hw'],v['hw']],v['e_common']
    if op in ('sigmoid','relu'):
        e = v['e_in'] if op == 'sigmoid' else v['exponent']
        return [one(v['input'],e)],[1,1,1,len(v['input'])],v.get('e_out',e)
    views = [one(v['data'],v['exponent'],v['c'],v['h'],v['w'])]
    shape = [1,v['c'],v['h'],v['w']]
    if op in ('nearest_upsample','bilinear_upsample'):
        shape[2]*=2;shape[3]*=2
    if op == 'gap':
        shape[2]=shape[3]=1
    return views,shape,v['exponent']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--delivery', type=Path, default=common.ROOT/'build/training_side_r24')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--sanitize', action='store_true')
    ap.add_argument('--ruling', type=Path, default=common.ROOT/'docs/PictureNew_全整数图_差异裁定_20261025.md')
    a = ap.parse_args()
    assert not a.output.exists()
    delivered = {p.relative_to(a.delivery).as_posix(): common.sha(p) for p in a.delivery.rglob('*') if p.is_file()}
    manifest = json.loads((a.delivery/'test_vectors/manifest.json').read_text())
    assert set(manifest) == set(TYPES)
    cases = []
    exclusions = []
    case_origins = []
    ruling_hash = None
    if a.delivery.name == 'training_side_r24' and a.ruling.exists():
        # Exclusions authorize these exact invalid original bytes only.
        assert delivered['test_vectors/concat_vectors.json']=='0604cdf7963341a6bc74bffda2cd175a3bc2e7f2769f5c2a4062af622b833597'
        assert delivered['test_vectors/bilinear_upsample_vectors.json']=='1144b39208b80acb5b047a8a753f9ff43ab96fd23a9ba6708fdad44461a708a7'
        ruling_hash=common.sha(a.ruling)
        assert ruling_hash=='afd6e66583415cf4a821ef539241a3fbc050652650576e135e3407f3089e9eb2', 'Changed ruling requires explicit review'
    audit = []
    for op, entry in manifest.items():
        name = entry['file'];assert Path(name).name == name
        vectors = json.loads((a.delivery/'test_vectors'/name).read_text())
        assert len(vectors) == entry['count']
        for i, v in enumerate(vectors):
            assert v['op'] == op
            expected = spec_result(op, v)
            if expected != v['expected']:
                at = next(j for j, (x,y) in enumerate(zip(expected,v['expected'])) if x != y)
                audit.append({'op': op, 'vector_index': i, 'note': v['note'],
                              'first_difference': at, 'spec_integer': expected[at], 'delivered_expected': v['expected'][at]})
            invalid = ruling_hash and ((op == 'concat' and i<25) or (op == 'bilinear_upsample' and i==25))
            if invalid:
                exclusions.append({'op': op, 'original_index': i, 'reason': 'Invalid expected data per authoritative Oct25 ruling'})
            else:
                cases.append((op,v));case_origins.append({'op': op, 'original_index': i})
    a.output.mkdir(parents=True)
    exponents = sorted({v['e_in'] for op,v in cases if op == 'sigmoid'})
    fixture = a.output/'r24-test-only.bin'
    with fixture.open('xb') as f:
        f.write(b'XQOPV1\0\0'+struct.pack('<2I',len(exponents),len(cases)))
        for e in exponents:
            values = []
            for value in range(-32768,32768):
                x = value*2.0**e
                sigmoid = 1.0 if x>500 else 0.0 if x< -500 else 1.0/(1.0+math.exp(-x))
                values.append(max(-32768,min(32767,round(sigmoid*32768))))
            f.write(struct.pack('<2i',e,-15)+struct.pack('<65536h',*values))
        for op,v in cases:
            views,shape,e = input_views(op,v)
            f.write(struct.pack('<3Ii5I',TYPES[op],len(views),len(v['expected']),e,*shape,
                                exponents.index(v['e_in']) if op == 'sigmoid' else 0xffffffff))
            for head,data in views:
                f.write(struct.pack('<4IiI',*head)+struct.pack('<'+str(len(data))+'h',*data))
            f.write(struct.pack('<'+str(len(v['expected']))+'h',*v['expected']))
    sources = ['linux/picture_new/graph_ops.c','linux/picture_new/graph_ops.h',
               'linux/picture_new/test_graph_ops.c','linux/picture_new/test_graph_ops_vectors.c',
               'scripts/check_picture_r24_ops.py','scripts/check_picture_integer_graph.py',
               'linux/picture_new/r14-models.sha256']
    hashes = {n: common.sha(common.ROOT/n) for n in sources}
    model_dir=common.ROOT/'build/picture-merge-20261023/native-models'
    model_hashes={}
    for line in (common.ROOT/'linux/picture_new/r14-models.sha256').read_text().splitlines():
        digest,name=line.split();assert Path(name).name==name
        assert common.sha(model_dir/name)==digest
        model_hashes[name]=digest
    assert len(model_hashes)==3
    inventory = common.inventory(model_dir)
    covered = {'conv','sigmoid','maxpool','nearest','bilinear','concat','add','avgpool','identity','relu'}
    actual = {op for model in inventory.values() for op in model['node_counts']}
    uncovered = sorted(actual-covered)
    assert not uncovered, 'Training specification does not cover: '+str(uncovered)
    result = {'status': 'RUNNING', 'training_delivery_sha256': delivered, 'source_sha256': hashes,
              'training_vectors': sum(v['count'] for v in manifest.values()),
              'valid_vectors_tested': len(cases), 'excluded_invalid_vectors': exclusions,
              'ruling_sha256': ruling_hash, 'active_case_origins': case_origins,
              'counts': {k:v['count'] for k,v in manifest.items()},
              'vector_spec_conflicts': audit, 'sigmoid_tables': 'Generated from delivered formula for TEST ONLY; production LUT not delivered',
              'hardware_used': False, 'whole_graph_selected': False, 'accuracy_accepted': False,
              'existing_graph_inventory': inventory,
              'frozen_model_sha256': model_hashes,
              'uncovered_existing_node_types': uncovered, 'targets': {}}
    save = lambda: (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    targets = [('host','gcc',[],[])]
    if not a.sanitize:
        targets.append(('qemu','/opt/toolchain/bin/riscv32-linux-musl-gcc',
                        ['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'],['qemu-riscv32']))
    for target,cc,extra,prefix in targets:
        flags = common.FLAGS+extra+['-I'+str(common.ROOT/'linux/picture_new')]
        if a.sanitize:
            flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
        core, vectors = a.output/(target+'-core'),a.output/(target+'-vectors')
        for name,binary in [('test_graph_ops.c',core),('test_graph_ops_vectors.c',vectors)]:
            common.run([cc,*flags,common.ROOT/'linux/picture_new/graph_ops.c',common.ROOT/'linux/picture_new'/name,
                        '-Wl,--gc-sections','-o',binary],a.output/(binary.name+'-compile.log'),90)
        core_log, vector_log = a.output/(target+'-core.log'),a.output/(target+'-vectors.log')
        common.run([*prefix,core],core_log,60)
        common.run([*prefix,vectors,fixture],vector_log,90,expected_codes=(0,1))
        assert 'ERROR: AddressSanitizer' not in vector_log.read_text() and 'runtime error:' not in vector_log.read_text()
        assert 'S16_OPS_BATCH2_TIES_EXP240_MINIMUM_I32_GAP_IDENTITY_AND_GUARDS_PASS' in core_log.read_text()
        rows = re.findall(r'S16_OP_RESULT type=(\d+) tested=(\d+) failed=(\d+)',vector_log.read_text())
        assert len(rows) == 8
        outcomes = {next(k for k,v in TYPES.items() if v == int(t)): {'tested': int(n), 'failed': int(f)} for t,n,f in rows}
        result['targets'][target] = {'core_pass': True, 'operator_vectors': outcomes,
                                     'vectors_binary_sha256': common.sha(vectors)}
        if target == 'qemu':
            elf=vectors.read_bytes()
            assert elf[:6]==b'\x7fELF\x01\x01' and struct.unpack_from('<H',elf,18)[0]==243
            assert struct.unpack_from('<I',elf,36)[0]==0
        # The operator object itself must not reference soft-float or libm.
        obj=a.output/(target+'-ops.o')
        common.run([cc,*flags,'-c',common.ROOT/'linux/picture_new/graph_ops.c','-o',obj],a.output/(target+'-object.log'),90)
        nm = '/opt/toolchain/bin/riscv32-linux-musl-nm' if target == 'qemu' else 'nm'
        common.run([nm,'-u',obj],a.output/(target+'-symbols.log'),30)
        symbols=(a.output/(target+'-symbols.log')).read_text()
        assert not re.search(r'__(?:add|sub|mul|div|extend|trunc|float|fix).*?(?:sf|df)|\b(?:exp|round|pow)[fl]?\b',symbols)
        result['targets'][target]['operator_object_has_no_fp_helpers'] = True
        save()
    if len(targets)==2:
        assert result['targets']['host']['operator_vectors'] == result['targets']['qemu']['operator_vectors']
    assert all(common.sha(a.delivery/n)==h for n,h in delivered.items())
    if ruling_hash:
        assert common.sha(a.ruling)==ruling_hash
    assert all(common.sha(common.ROOT/n)==h for n,h in hashes.items())
    failures = sum(v['failed'] for v in result['targets']['host']['operator_vectors'].values())
    result['status'] = ('PARTIAL_TRAINING_VECTOR_CONFLICTS' if failures else
                        'ADJUDICATED_VALID_VECTORS_PASS_WAIT_R24A_NOT_WHOLE_GRAPH' if exclusions else
                        'OPERATOR_VECTORS_PASS_NOT_WHOLE_GRAPH')
    result['failed_vectors'] = failures
    result['all_209_original_vectors_accepted'] = False if exclusions else not failures
    result['concat_random_vector_acceptance_pending'] = bool(exclusions)
    save()
    print(result['status'], 'valid_vectors=',len(cases),'excluded=',len(exclusions),'failed=',failures)
    print(json.dumps(result['targets']['host']['operator_vectors']))
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
