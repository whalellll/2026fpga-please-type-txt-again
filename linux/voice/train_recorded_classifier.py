#!/usr/bin/env python3
"""Freeze accepted real recordings and train an experimental 24-word XQT1 model.

Formal trainer gates and source recording splits are unchanged. A per-word
chronological holdout is exploratory, not independent accuracy acceptance.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import shutil

import numpy as np
import torch

from train_token_classifier import TokenMlp, export_model
from train_pilot_classifier import integer_result, layers_from_file, parameters, pool
from train_tdnn_ctc import TOKENS, normalize, raw_features, read_wave

MAX_SAMPLES = 32240


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def freeze(args):
    dataset = args.dataset.resolve()
    sources = sorted(dataset.rglob('*.accepted.json'))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'data').mkdir()
    records, seen = [], set()
    for source in sources:
        item = json.loads(source.read_text(encoding='utf8'))
        if item['status'] != 'human_accepted' or item['token'] not in TOKENS[1:]:
            continue
        if item['split'] == 'pilot' and not args.allow_pilot:
            continue
        if item['split'] not in ('train', 'pilot'):
            raise ValueError('Do not repurpose validation/test recordings: ' + str(source))
        if source.with_name(source.name.replace('.accepted.json', '.rejected.json')).exists():
            raise ValueError('Acceptance/rejection conflict: ' + str(source))
        audio = (source.parent / item['path']).resolve()
        if not audio.is_relative_to(dataset) or sha(audio) != item['sha256']:
            raise ValueError('Path/hash mismatch: ' + str(source))
        if item['sha256'] in seen:
            raise ValueError('Duplicate recording SHA; resolve before splitting')
        seen.add(item['sha256'])
        samples = read_wave(audio)
        target = args.output / 'data' / ('sample_%03d.wav' % len(records))
        shutil.copy2(audio, target)
        if sha(target) != item['sha256']:
            raise ValueError('Snapshot hash mismatch')
        target.with_suffix('.pcm').write_bytes(samples.astype('<i2').tobytes())
        records.append({'index': len(records), 'id': item['id'], 'token': item['token'],
                        'label': TOKENS.index(item['token']), 'speaker': item['speaker'],
                        'session': item['session'], 'source_split': item['split'],
                        'metadata_sha256': sha(source), 'sha256': item['sha256'],
                        'path': target.relative_to(args.output).as_posix(), 'samples': len(samples),
                        'parent_group_sha256': item.get('parent_recording_sha256', item.get('raw_sha256', item['sha256']))})
    counts = Counter(r['token'] for r in records)
    if set(counts) != set(TOKENS[1:]) or min(counts.values(), default=0) < 2:
        raise ValueError('Full vocabulary needs all24 words and >=2 accepted recordings per word: ' + str(counts))
    value = {'schema': 1, 'records': records, 'counts': dict(counts), 'token_ids': TOKENS,
             'allow_pilot': args.allow_pilot,
             'fingerprint': hashlib.sha256(json.dumps([(r['sha256'], r['label']) for r in records]).encode()).hexdigest()}
    save(args.output / 'snapshot.json', value)
    print(json.dumps({'frozen': len(records), 'counts': counts, 'fingerprint': value['fingerprint']}), flush=True)


def fit(features, labels, train_indices, output, args):
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    offset, scale = parameters([features[i] for i in train_indices])
    pooled = np.stack([pool(x, offset, scale) for x in features])
    x = torch.from_numpy(pooled[train_indices].astype(np.float32))
    y = torch.tensor([labels[i] for i in train_indices], dtype=torch.long)
    model = TokenMlp(args.hidden1, args.hidden2)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, [args.epochs // 2, args.epochs * 3 // 4], gamma=0.3)
    history = []
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad()
        loss = torch.nn.functional.cross_entropy(model(x), y)
        loss.backward()
        optimizer.step()
        scheduler.step()
        if epoch == 0 or (epoch + 1) % 100 == 0:
            history.append({'epoch': epoch + 1, 'train_loss': float(loss.detach())})
            print(output.stem, epoch + 1, 'train_loss', float(loss.detach()), flush=True)
    model.eval()
    with torch.no_grad():
        floating = model(torch.from_numpy(pooled.astype(np.float32))).argmax(dim=1).tolist()
    export_model(model, output, offset, scale)
    checkpoint = output.with_suffix('.pt')
    torch.save({'state_dict': model.state_dict(), 'architecture': [40, args.hidden1, args.hidden2, len(TOKENS)],
                'feature_offset_q8': offset, 'feature_scale_q15': scale,
                'token_ids': TOKENS, 'epochs': args.epochs, 'seed': args.seed}, checkpoint)
    return {'sha256': sha(output), 'bytes': output.stat().st_size, 'checkpoint_sha256': sha(checkpoint),
            'offset_q8': offset, 'scale_q15': scale, 'history': history,
            'float_predictions': floating, 'int8_predictions': [integer_result(output, f) for f in features],
            'train_item_count': len(train_indices), 'selection': 'Fixed final epoch, no holdout-based tuning'}


def train(args):
    snapshot = json.loads(args.snapshot.read_text(encoding='utf8'))
    root = args.snapshot.resolve().parent
    records = snapshot['records']
    if snapshot['token_ids'] != TOKENS:
        raise ValueError('Token ABI mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'data').mkdir()
    segments = json.loads(args.segments.read_text(encoding='utf8'))
    if segments['snapshot_sha256'] != sha(args.snapshot):
        raise ValueError('Segment index does not belong to this frozen snapshot')
    segment_map = {r['source_index']: r for r in segments['entries']}
    if set(segment_map) != set(range(len(records))):
        raise ValueError('Segment index must cover every frozen recording exactly once')
    if len(segment_map) != len(segments['entries']):
        raise ValueError('Duplicate source index')
    features, labels, parents, kinds, full_indices, preferred_indices = [], [], [], [], [], []

    def add(samples, parent, kind):
        if not 400 <= len(samples) <= MAX_SAMPLES:
            raise ValueError('Feature input outside runtime bounds')
        index = len(features)
        features.append(raw_features(samples))
        labels.append(records[parent]['label'])
        parents.append(parent)
        kinds.append(kind)
        (args.output / 'data' / ('item_%03d.pcm' % index)).write_bytes(samples.astype('<i2').tobytes())
        return index

    exclusions = []
    for i, record in enumerate(records):
        audio = (root / record['path']).resolve()
        if not audio.is_relative_to(root) or sha(audio) != record['sha256']:
            raise ValueError('Frozen WAV mismatch')
        samples = read_wave(audio)
        full = add(samples, i, 'full_clip')
        full_indices.append(full)
        preferred = full
        entry = segment_map[i]
        if len(entry['segments']) == 1:
            segment = entry['segments'][0]
            path = (args.segments.resolve().parent / segment['path']).resolve()
            if not path.is_relative_to(args.segments.resolve().parent) or sha(path) != segment['sha256']:
                raise ValueError('VAD segment path/hash mismatch')
            samples = np.frombuffer(path.read_bytes(), dtype='<i2').astype(np.int32)
            preferred = add(samples, i, 'exact_vad')
            for left, right in [(1600, 0), (0, 1600), (1600, 1600), (0, 3200)]:
                if len(samples) + left + right <= MAX_SAMPLES:
                    add(np.pad(samples, (left, right)), i, 'vad_padding_%d_%d' % (left, right))
        else:
            exclusions.append({'source_index': i, 'token': record['token'], 'segment_count': len(entry['segments']),
                               'policy': 'Keep accepted full clip only; do not assign labels to ambiguous/no VAD segments'})
        preferred_indices.append(preferred)
    groups = defaultdict(list)
    for i, record in enumerate(records): groups[record['token']].append(i)
    proposed_holdout = {v[-1] for v in groups.values()}
    group_key = lambda i: records[i].get('parent_group_sha256', records[i]['sha256'])
    held_groups = {group_key(i) for i in proposed_holdout}
    holdout = sorted(i for i in range(len(records)) if group_key(i) in held_groups)
    available_training = {r['token'] for i, r in enumerate(records) if i not in holdout}
    if available_training != set(TOKENS[1:]):
        raise ValueError('Batch-group holdout leaves some words without training data; record more independent batches per word')
    held_items = [i for i, parent in enumerate(parents) if parent not in holdout]
    # The holdout model never uses any variant of held parents in normalization or fitting.
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    held = fit(features, labels, held_items, args.output / 'holdout-eval.xqt', args)
    candidate = fit(features, labels, list(range(len(features))), args.output / 'all24-candidate.xqt', args)

    def accuracy(predictions, indices):
        return {'correct': sum(predictions[i] == labels[i] for i in indices), 'total': len(indices)}

    hold_full = [full_indices[i] for i in holdout]
    hold_preferred = [preferred_indices[i] for i in holdout]
    metrics = {}
    for name, model, indices in [('holdout_full_clip', held, hold_full),
                                  ('holdout_vad_or_full', held, hold_preferred),
                                  ('all_fit_full_clip_resubstitution', candidate, full_indices),
                                  ('all_fit_vad_or_full_resubstitution', candidate, preferred_indices)]:
        metrics[name + '_float'] = accuracy(model['float_predictions'], indices)
        metrics[name + '_int8'] = accuracy([x['prediction'] for x in model['int8_predictions']], indices)
    per_class = []
    for token in TOKENS[1:]:
        parent = groups[token][-1]
        index = preferred_indices[parent]
        per_class.append({'token': token, 'source_index': parent, 'input_kind': kinds[index],
                          'prediction': held['int8_predictions'][index], 'correct': held['int8_predictions'][index]['prediction'] == records[parent]['label']})
    for name in ('holdout-eval', 'all24-candidate'):
        offset, scale, _ = layers_from_file(args.output / (name + '.xqt'))
        for i, f in enumerate(features):
            (args.output / 'data' / ('item_%03d.%s.features' % (i, name))).write_bytes(normalize(f, offset, scale).tobytes())
    report = {'schema': 1, 'status': 'ALL24_EXPERIMENTAL_TRAINING_COMPLETE_NOT_ACCURACY_ACCEPTANCE',
              'architecture': [40, args.hidden1, args.hidden2, 25], 'format': 'XQT1', 'epochs': args.epochs, 'seed': args.seed,
              'recording_count': len(records), 'class_counts': snapshot['counts'], 'token_ids': TOKENS,
              'sessions': dict(Counter(r['session'] for r in records)), 'source_splits': dict(Counter(r['source_split'] for r in records)),
              'snapshot_sha256': sha(args.snapshot), 'data_fingerprint': snapshot['fingerprint'],
              'segment_manifest_sha256': sha(args.segments), 'holdout_parent_indices': holdout,
              'holdout_policy': 'Last recording per word, expanded to every clip sharing a source batch SHA; all variants remain with parent',
              'holdout_training_parents': len(records) - len(holdout), 'feature_item_count': len(features),
              'feature_parent_indices': parents, 'feature_kinds': kinds, 'feature_labels': labels,
              'full_clip_item_indices': full_indices, 'preferred_item_indices': preferred_indices,
              'ambiguous_vad_policy': exclusions, 'metrics': metrics, 'holdout_per_class': per_class,
              'holdout_model': held, 'all_fit_candidate': candidate,
              'source_sha256': {name: sha(Path(__file__).with_name(name)) for name in
                                ['train_recorded_classifier.py', 'train_pilot_classifier.py', 'train_token_classifier.py', 'train_tdnn_ctc.py']},
              'limits': ['Chronological exploratory holdout, expanded to whole source batches; not independent sessions/speakers',
                         'All-fit candidate uses all frozen parents, including exploratory holdouts; its resubstitution is not test accuracy',
                         'Augmentation remains with parent; normalization fits training items only for holdout model',
                         'Reserved blank/background/unknown rejection not trained; margin is not probability',
                         'No board deployment or hardware speed acceptance; CPU XQT1 only',
                         'Private audio/features remain local and are excluded from delivery']}
    save(args.output / 'results.json', report)
    print(json.dumps(metrics, indent=2), flush=True)
    print('ALL24_CANDIDATE', candidate['sha256'], candidate['bytes'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze')
    f.add_argument('dataset', type=Path)
    f.add_argument('output', type=Path)
    f.add_argument('--allow-pilot', action='store_true')
    t = sub.add_parser('train')
    t.add_argument('snapshot', type=Path)
    t.add_argument('output', type=Path)
    t.add_argument('--segments', type=Path, required=True)
    t.add_argument('--hidden1', type=int, default=64)
    t.add_argument('--hidden2', type=int, default=32)
    t.add_argument('--epochs', type=int, default=600)
    t.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    if args.command == 'freeze': freeze(args)
    else:
        if not (1 <= args.hidden1 <= 256 and 1 <= args.hidden2 <= 256 and args.epochs >= 4):
            parser.error('Invalid dimensions/epochs')
        train(args)


if __name__ == '__main__':
    main()
