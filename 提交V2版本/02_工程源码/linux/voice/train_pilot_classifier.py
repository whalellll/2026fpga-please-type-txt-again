#!/usr/bin/env python3
"""Experimental accepted-recording XQT1 training; not a release accuracy gate.

Uses one chronological recording per class as an exploratory holdout. A second
candidate fits all frozen recordings for later live tests. Their metrics are
reported separately. No original capture labels or production trainer gates
are modified. Augmentation is deliberately absent in this first experiment.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct

import numpy as np
import torch
from torch import nn

from train_token_classifier import TokenMlp, export_model
from train_tdnn_ctc import TOKENS, raw_features, read_wave, normalize, quantize_layer, requantize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parameters(features):
    values = np.concatenate([x.ravel() for x in features]).astype(np.float64)
    offset = int(round(float(values.mean())))
    scale = int(round(24.0 / max(1.0, float(values.std())) * 32768.0))
    return offset, scale


def pool(features, offset, scale):
    values = normalize(features, offset, scale).astype(np.int64)
    sums = values.sum(axis=0)
    means = np.where(sums >= 0, sums // len(values), -((-sums) // len(values)))
    return np.concatenate((means, values.max(axis=0))).astype(np.int8)


def layers_from_file(path):
    image = path.read_bytes()
    assert image[:4] == b'XQT1'
    h1, h2, classes, offset, scale, s1, s2, s3 = struct.unpack_from('<IIIiiIII', image, 32)
    position = 128
    layers = []
    for inputs, outputs, shift in ((40, h1, s1), (h1, h2, s2), (h2, classes, s3)):
        weight = np.frombuffer(image, dtype=np.int8, count=outputs * inputs, offset=position).copy().reshape(outputs, inputs)
        position += outputs * inputs
        bias = np.frombuffer(image, dtype='<i4', count=outputs, offset=position).copy()
        position += outputs * 4
        layers.append((weight, bias, shift))
    assert position == len(image)
    return offset, scale, layers


def integer_result(path, features):
    offset, scale, layers = layers_from_file(path)
    value = pool(features, offset, scale).astype(np.int64)
    for index, (weight, bias, shift) in enumerate(layers):
        value = requantize(weight.astype(np.int64) @ value + bias, shift, index < 2).astype(np.int64)
    order = np.argsort(-value, kind='stable')
    token = int(order[0])
    margin = int(value[order[0]] - value[order[1]]) * 1000 // 255
    return {'prediction': token, 'token': TOKENS[token], 'score': margin,
            'top3': [{'token': TOKENS[int(k)], 'logit': int(value[k])} for k in order[:3]]}


def fit(features, labels, train, out, args):
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    offset, scale = parameters([features[i] for i in train])
    values = np.stack([pool(x, offset, scale) for x in features])
    x = torch.from_numpy(values[train].astype(np.float32))
    y = torch.tensor([labels[i] for i in train], dtype=torch.long)
    model = TokenMlp(args.hidden1, args.hidden2)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones=[args.epochs // 2, args.epochs * 3 // 4], gamma=0.3)
    loss_function = nn.CrossEntropyLoss()
    history = []
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad()
        loss = loss_function(model(x), y)
        loss.backward()
        optimizer.step()
        scheduler.step()
        if (epoch + 1) % 50 == 0 or epoch == 0:
            history.append({'epoch': epoch + 1, 'train_loss': float(loss.detach())})
    model.eval()
    with torch.no_grad():
        floating = model(torch.from_numpy(values.astype(np.float32))).argmax(dim=1).tolist()
    export_model(model, out, offset, scale)
    integers = [integer_result(out, x) for x in features]
    return {'sha256': sha(out), 'bytes': out.stat().st_size, 'offset_q8': offset, 'scale_q15': scale,
            'train_indices': train, 'float_predictions': floating, 'int8_predictions': integers,
            'history': history, 'checkpoint_selection': 'Fixed epoch count, final checkpoint; no holdout-based tuning'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--allow-pilot', action='store_true')
    parser.add_argument('--hidden1', type=int, default=32)
    parser.add_argument('--hidden2', type=int, default=16)
    parser.add_argument('--epochs', type=int, default=300)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    if not (1 <= args.hidden1 <= 256 and 1 <= args.hidden2 <= 256 and args.epochs >= 1):
        parser.error('invalid dimensions/epochs')
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = sorted(args.dataset.rglob('*.accepted.json'))
    records = []
    seen = set()
    for source in frozen:
        item = json.loads(source.read_text(encoding='utf8'))
        if item['status'] != 'human_accepted' or item['token'] not in TOKENS[1:]:
            continue
        if item['split'] == 'pilot' and not args.allow_pilot:
            continue
        if item['split'] in ('test', 'validation'):
            raise ValueError('This experiment does not repurpose previously assigned validation/test data')
        if source.with_name(source.name.replace('.accepted.json', '.rejected.json')).exists():
            raise ValueError('Conflicting acceptance/rejection: ' + str(source))
        audio = (source.parent / item['path']).resolve()
        if not audio.is_relative_to(args.dataset.resolve()) or sha(audio) != item['sha256']:
            raise ValueError('Recording path/hash mismatch: ' + str(source))
        if item['sha256'] in seen:
            raise ValueError('Duplicate accepted recording; do not leak copies across subsets')
        seen.add(item['sha256'])
        sample = read_wave(audio)
        index = len(records)
        target = args.output / 'data' / ('sample_%03d.wav' % index)
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(audio, target)
        pcm = sample.astype('<i2').tobytes()
        target.with_suffix('.pcm').write_bytes(pcm)
        records.append({'id': item['id'], 'token': item['token'], 'label': TOKENS.index(item['token']),
                        'speaker': item['speaker'], 'session': item['session'], 'source_split': item['split'],
                        'source_metadata_sha256': sha(source), 'sha256': item['sha256'],
                        'path': target.relative_to(args.output).as_posix()})
    groups = defaultdict(list)
    for i, row in enumerate(records): groups[row['token']].append(i)
    if len(groups) < 2 or any(len(v) < 2 for v in groups.values()):
        raise ValueError('Need at least two classes and two different recordings per included class')
    holdout = sorted(v[-1] for v in groups.values())
    train = [i for i in range(len(records)) if i not in holdout]
    with (args.output / 'exploratory_manifest.csv').open('x', encoding='utf8', newline='') as f:
        writer = csv.writer(f);writer.writerow(['path','split','tokens','speaker','session','sha256'])
        for i, row in enumerate(records): writer.writerow([row['path'],'holdout' if i in holdout else 'train',row['token'],row['speaker'],row['session'],row['sha256']])
    features = [raw_features(read_wave(args.output / row['path'])) for row in records]
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    print('FROZEN_RECORDINGS', len(records), dict(Counter(r['token'] for r in records)), flush=True)
    held = fit(features, [r['label'] for r in records], train, args.output / 'holdout-eval.xqt', args)
    all_fit = fit(features, [r['label'] for r in records], list(range(len(records))), args.output / 'pilot-candidate.xqt', args)
    baseline = [integer_result(args.baseline, x) for x in features]
    for i, row in enumerate(records):
        row['baseline'] = baseline[i]
        row['exploratory'] = held['int8_predictions'][i]
        row['all_fit_resubstitution'] = all_fit['int8_predictions'][i]
        for name in ('holdout-eval', 'pilot-candidate'):
            offset, scale, _ = layers_from_file(args.output / (name + '.xqt'))
            (args.output / 'data' / ('sample_%03d.%s.features' % (i, name))).write_bytes(normalize(features[i], offset, scale).tobytes())
    correct = lambda values, indices: sum(values[i] == records[i]['label'] for i in indices)
    indices = list(range(len(records)))
    metrics = {'baseline_all_recordings': {'correct': correct([r['prediction'] for r in baseline], indices), 'total':len(records)},
               'exploratory_float_holdout': {'correct':correct(held['float_predictions'], holdout),'total':len(holdout)},
               'exploratory_int8_holdout': {'correct':correct([r['prediction'] for r in held['int8_predictions']], holdout),'total':len(holdout)},
               'candidate_float_training_resubstitution':{'correct':correct(all_fit['float_predictions'], indices),'total':len(records)},
               'candidate_int8_training_resubstitution':{'correct':correct([r['prediction'] for r in all_fit['int8_predictions']], indices),'total':len(records)}}
    report = {'schema':1, 'status':'EXPERIMENTAL_PILOT_TRAINING_COMPLETE_NOT_ACCURACY_ACCEPTANCE',
              'architecture':[40,args.hidden1,args.hidden2,25], 'format':'XQT1', 'seed':args.seed,'epochs':args.epochs,
              'normalization':'Fitted only to training recordings for holdout model; all recordings for all-fit candidate; same existing feature code',
              'sampling_scope':'Single-session chronological within-class holdout; not independent speaker/session validation',
              'holdout_indices':holdout,'trained_tokens':sorted(groups),'untrained_tokens':[t for t in TOKENS[1:] if t not in groups],
              'holdout_model':held,'all_fit_candidate':all_fit,'metrics':metrics,'records':records,
              'baseline_sha256':sha(args.baseline),'source_sha256':{p.name:sha(p) for p in [Path(__file__),Path(__file__).with_name('train_token_classifier.py'),Path(__file__).with_name('train_tdnn_ctc.py')]},
              'training_data_policy':'Local frozen copies under data/; do not package personal WAV/PCM or generated features with candidate delivery',
              'limitations':['Tiny dataset, no independent test set','Other 19 words and unknown/background rejection untrained','Quantized score is logit margin, not probability','Live VAD segmentation may differ from full-clip inference','No FPGA/Pikafish changes; CPU runtime candidate only']}
    (args.output / 'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(metrics,ensure_ascii=True,indent=2),flush=True)
    print('PILOT_MODEL_CANDIDATE',all_fit['sha256'],all_fit['bytes'],flush=True)


if __name__ == '__main__':main()
