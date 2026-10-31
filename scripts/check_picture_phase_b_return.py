"""Read-only Phase B intake: archive, graph and independent 60-layer packing checks.

Does not execute returned tools or read image datasets. Extracted weights and
sample metadata remain in the explicit private build area.
"""
import argparse
import ast
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import struct
import zipfile
from picture_workspace import ROOT, workspace_path
from model_int8_handoff.handoff_inventory import graph

EXPECTED = 'f5b2e6c15f432522a39ffd6f99a77cfc6473a9196805203e433792f123cb10ee'
PREFIX = 'xinyi_phase_b_r01_return/'


def digest(b):
    return hashlib.sha256(b).hexdigest()


def npy(b):
    assert b[:8] == b'\x93NUMPY\x01\x00'
    size = struct.unpack_from('<H', b, 8)[0]
    assert size < 4096
    h = ast.literal_eval(b[10:10+size].decode('ascii'))
    assert h['fortran_order'] is False and h['descr'] in ('|i1', '<i4', '<i8')
    width = {'|i1': 1, '<i4': 4, '<i8': 8}[h['descr']]
    data = b[10+size:]
    assert len(data) == math.prod(h['shape'])*width
    return h['shape'], data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--zip', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    out = workspace_path(a.output)
    assert out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve())
    out.mkdir(parents=True, exist_ok=False)
    raw = a.zip.read_bytes()
    assert digest(raw) == EXPECTED, 'Unexpected return identity'
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        assert len(names) == len(set(names)) == 138 and z.testzip() is None
        assert all(n.startswith(PREFIX) and '..' not in PurePosixPath(n).parts
                   and '\\' not in n and not n.endswith('/') for n in names)
        payload = {n[len(PREFIX):]: z.read(n) for n in names}
    sums = {}
    for line in payload['SHA256SUMS.txt'].decode().splitlines():
        sha, name = line.split('  ', 1)
        assert name not in sums
        sums[name] = sha
    assert set(sums) == set(payload)-{'SHA256SUMS.txt'}
    assert all(digest(payload[n]) == sha for n, sha in sums.items())
    manifest = json.loads(payload['return-manifest.json'])
    assert set(manifest['files']) == set(payload)-{'return-manifest.json','SHA256SUMS.txt'}
    for name, data in payload.items():
        target = out/'returned'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    base = 'candidate_r01_512/'
    inventories = {}
    packs = {}
    for ext in ('xqm', 'xqi'):
        data = payload[base+'pack/detector_512.'+ext]
        assert digest(data) == manifest['candidate'][ext]
        inventories[ext] = graph(data, digest(data))
        h = struct.unpack_from('<10I', data, 8)
        offset = 16 if ext == 'xqm' else 0
        nodes = [struct.unpack_from('<32i', data, 48+offset+i*128) for i in range(h[2])]
        packs[ext] = (nodes, data[48+offset+128*h[2]:])
        assert inventories[ext]['output_shapes_nchw'] == [[1,57,64,64],[1,57,32,32],[1,57,16,16]]
        assert list(nodes[0][1:4]) == [16,256,256]
    assert struct.unpack_from('<4I', payload[base+'pack/detector_512.xqm'], 48)[:3] == (3,512,512)
    meta = json.loads(payload[base+'pack/xqm_manifest.json'])
    layers = list(meta['source_npz_sha256'])
    qnodes, qblob = packs['xqm']; inodes, iblob = packs['xqi']
    convs = [i for i,n in enumerate(qnodes) if n[0] == 1]
    assert len(convs) == len(layers) == 60
    checks = []
    for i, layer in zip(convs, layers):
        q, n = qnodes[i], inodes[i]
        data = payload[base+'int8/'+layer+'.npz']
        assert digest(data) == meta['source_npz_sha256'][layer]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
            arrays = {s: npy(z.read(s+'.npy')) for s in
                      ('weight','bias','right_shifts','activation_lut')}
        co, ci, kh, kw = arrays['weight'][0]
        assert (co,kh,kw) == (n[1],n[10],n[11])
        w = arrays['weight'][1]; k = ci*kh*kw
        assert qblob[q[20]:q[20]+len(w)] == w
        packed = bytearray(((co+7)//8)*k*8)
        for oc in range(co):
            for c in range(ci):
                for y in range(kh):
                    for x in range(kw):
                        packed[((oc//8)*k+(y*kw+x)*ci+c)*8+oc%8] = w[((oc*ci+c)*kh+y)*kw+x]
        assert iblob[n[20]:n[20]+n[29]] == packed
        bias = struct.unpack('<'+'i'*co, arrays['bias'][1])
        shifts = struct.unpack('<'+'q'*co, arrays['right_shifts'][1])
        params = b''.join(struct.pack('<iII', bias[j] if j<co else 0, 1,
                                     shifts[j] if j<co else 0) for j in range((co+7)//8*8))
        assert iblob[n[21]:n[21]+n[30]] == params
        assert all(0 <= s <= 62 for s in shifts)
        lut = arrays['activation_lut'][1]
        assert qblob[q[23]:q[23]+q[24]] == lut == iblob[n[23]:n[23]+n[24]]
        if lut:
            assert lut == payload[base+'int8/'+layer+'.lut']
        checks.append({'node':i,'packed_weight_bytes':len(packed),'parameters_bytes':len(params),'lut_bytes':len(lut)})
    code = payload['run_ab_200.py'].decode()
    # These are findings about this pinned returned source, not an A/B rerun.
    assert 'raw640, _ = model640.pipeline.predict(image, f)' in code
    assert "raw640.get('predictions_original')" in code
    assert 'raw = run_interp_heads(t512)' in code
    assert 'p = p[p[:, 4] >= .05]' in code
    result = dict(status='INTAKE_AND_60_LAYER_PACKING_PASS_AB_GATE_NOT_COMPARABLE_NOT_DEPLOYABLE',
        archive_sha256=EXPECTED, archive_bytes=len(raw), members=len(payload), hash_entries=len(sums),
        independent_layer_checks=checks, inventories=inventories,
        findings=['512 pre-classifier vs640 fused pipeline predictions: A/B incomparable',
                  'numeric_verification.json retains CANDIDATE_NUMERIC_FAIL while t3_report reports PASS; supersession unclear',
                  'fixed lists/per-frame results/dependency identities not delivered: group split and attribution not independently reproduced',
                  'PC interpreter timing versus kit-host timing is not a backend-controlled speed comparison'],
        inference_run=False, datasets_read=False, frozen_model_replaced=False, hardware_used=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','archive_sha256','members','hash_entries')}))


if __name__ == '__main__':
    main()
