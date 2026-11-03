#!/usr/bin/env python3
"""Attribute an unchanged PDS synthesis report to its frozen input snapshot.

Rows are inclusive. Self counts subtract only immediate children, avoiding
double-counting nested CPU/MAC instances. This is mapping evidence, not STA.
"""
import argparse
from pathlib import Path
import hashlib
import json
import re


def profile(root):
    root = Path(root).resolve()
    snapshot_path = root/'pds/build_snapshot.json'
    source_kind = 'frozen-physical-inputs'
    if not snapshot_path.exists():
        snapshot_path = root/'resource-evidence/result.json'
        source_kind = 'frozen-resource-only-inputs'
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
    if source_kind == 'frozen-resource-only-inputs':
        assert snapshot['status'] == 'SYNTHESIS_COMPLETE_RESOURCE_REVIEW_ONLY'
    report = root/'pds/synthesize/soc_top.snr'
    raw = report.read_bytes()
    fields = ('lut', 'ff', 'lutram', 'apm', 'drm36k_equivalent')
    rows, stack = [], []
    for line in raw.decode(errors='strict').splitlines():
        cells = line.split('|')
        if len(cells) < 8 or not re.fullmatch(r'\s*\d+\s*', cells[2]):
            continue
        label = cells[1]
        match = re.fullmatch(r'(\s*)\+\s+(.*?)\s*', label)
        depth = (len(match[1])-1)//2+1 if match else 0
        name = match[2] if match else label.strip()
        if not rows:
            assert name == 'soc_top' and depth == 0
        else:
            assert depth > 0 and depth <= len(stack), (name, depth)
        stack = stack[:depth]
        parent = stack[-1] if stack else None
        row = {'path': (rows[parent]['path']+'/' if parent is not None else '')+name,
               'depth': depth, 'parent': parent,
               'inclusive': {key: float(cells[i+2]) for i,key in enumerate(fields)}}
        rows.append(row)
        stack.append(len(rows)-1)
    assert len(rows) > 100
    for row in rows:
        row['self'] = dict(row['inclusive'])
    for row in rows[1:]:
        target = rows[row['parent']]['self']
        for key in fields:
            target[key] -= row['inclusive'][key]
    assert all(value >= 0 for row in rows for value in row['self'].values())
    text = raw.decode()
    for label, key in [('Total LUTs', 'lut'), ('Total Registers', 'ff')]:
        assert float(re.search(label+r':\s*(\d+)', text)[1]) == rows[0]['inclusive'][key]
    changed = [name for name,expected in snapshot['inputs'].items()
               if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected]
    assert not changed, changed
    assert not any('sparse' in row['path'].lower() for row in rows)
    return {'schema': 1, 'status': 'NATIVE_RESOURCE_PROFILE_INPUTS_VERIFIED_NOT_STA_OR_BOARD',
            'root': str(root), 'run_id': snapshot.get('run_id'), 'source_kind': source_kind,
            'snapshot_sha256': hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
            'report_sha256': hashlib.sha256(raw).hexdigest(),
            'input_count': len(snapshot['inputs']), 'rows': rows,
            'scope': 'Inclusive and self mapped resources; no sparse-named mapped subtree. '
                     'No physical timing, model throughput or board claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = profile(args.root)
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(result['status'], 'run='+str(result['run_id']), 'rows='+str(len(result['rows'])))
    print(json.dumps(result['rows'][0]['inclusive']))
