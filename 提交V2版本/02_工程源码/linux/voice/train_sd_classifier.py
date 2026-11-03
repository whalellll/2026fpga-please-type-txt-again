#!/usr/bin/env python3
"""Experimental selected-SD-only XQT1 training, with explicit missing classes.

Keeps all25 runtime token IDs. Does not relax either full-vocabulary trainer.
Only human accepted clips whose parent SHA matches an explicit source JSON
can enter this experiment. Missing positive classes are reported, not backfilled.
"""
import argparse
from collections import Counter,defaultdict
import hashlib,json,re,shutil
from pathlib import Path
import numpy as np
import torch
from train_recorded_classifier import fit,save,sha
from train_tdnn_ctc import TOKENS,raw_features,read_wave,normalize
from train_pilot_classifier import layers_from_file

def is_selected(item,allowed_groups):
    return (item.get('status')=='human_accepted' and item.get('token') in TOKENS[1:]
            and item.get('parent_recording_sha256') in allowed_groups)

def choose_group_holdout(records):
    groups=defaultdict(list)
    for i,r in enumerate(records):groups[r['parent_group_sha256']].append(i)
    observed={r['token'] for r in records};skipped=[]
    ordered=sorted(groups,key=lambda g:(max(records[i]['session'] for i in groups[g]),g),reverse=True)
    for group in ordered:
        held=set(groups[group]);remaining={r['token'] for i,r in enumerate(records) if i not in held}
        missing=sorted(observed-remaining)
        if not missing:return sorted(held),skipped
        skipped.append({'group':group,'missing_training_tokens':missing})
    raise ValueError('No whole-source holdout retains every observed class; no random clip fallback')

def freeze(args):
    dataset=args.dataset.resolve();allowed={};source_jsons=[]
    for sidecar in args.source_json:
        origin=json.loads(sidecar.read_text(encoding='utf8'))
        digest=origin.get('request',{}).get('raw_sha256','')
        if origin.get('transport')!='board SD FAT32' or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('Require board SD recording JSON with source SHA')
        if digest in allowed:raise ValueError('Duplicate source group')
        allowed[digest]=sidecar.stem
        source_jsons.append({'recording':sidecar.stem,'sha256':sha(sidecar),'parent_sha256':digest})
    records=[];seen=set();selected=[]
    for path in sorted(dataset.rglob('*.accepted.json')):
        item=json.loads(path.read_text(encoding='utf8'))
        if not is_selected(item,set(allowed)):continue
        if item['split']!='train':raise ValueError('Selected SD recording is not train; retain original split')
        if path.with_name(path.name.replace('.accepted.json','.rejected.json')).exists():raise ValueError('Rejected conflict')
        audio=(path.parent/item['path']).resolve()
        if not audio.is_relative_to(dataset) or sha(audio)!=item['sha256']:raise ValueError('Audio path/hash mismatch')
        if item['sha256'] in seen:raise ValueError('Duplicate selected clip')
        seen.add(item['sha256']);samples=read_wave(audio)
        selected.append((path,item,audio,samples))
    if len(selected)!=args.expected_count:raise ValueError('Selected count differs: '+str(len(selected)))
    if {item['parent_recording_sha256'] for _,item,_,_ in selected}!=set(allowed):raise ValueError('A selected source has no accepted clips')
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'data').mkdir()
    for path,item,audio,samples in selected:
        group=item['parent_recording_sha256'];target=args.output/'data'/('sample_%03d.wav'%len(records))
        shutil.copy2(audio,target)
        if sha(target)!=item['sha256']:raise ValueError('Frozen copy SHA mismatch')
        target.with_suffix('.pcm').write_bytes(samples.astype('<i2').tobytes())
        records.append({'index':len(records),'id':item['id'],'token':item['token'],'label':TOKENS.index(item['token']),
            'speaker':item['speaker'],'session':item['session'],'source_split':item['split'],
            'metadata_sha256':sha(path),'sha256':item['sha256'],'path':target.relative_to(args.output).as_posix(),
            'samples':len(samples),'parent_group_sha256':group,'source_recording':allowed[group]})
    counts=Counter(r['token'] for r in records)
    value={'schema':1,'status':'SD_ONLY_PARTIAL_VOCAB_EXPERIMENT','token_ids':TOKENS,'records':records,
        'counts':dict(counts),'missing_tokens':[t for t in TOKENS[1:] if t not in counts],
        'source_jsons':source_jsons,'older_recordings_included':False,
        'fingerprint':hashlib.sha256(json.dumps([(r['sha256'],r['label']) for r in records]).encode()).hexdigest()}
    save(args.output/'snapshot.json',value)
    print(json.dumps({k:value[k] for k in ['status','counts','missing_tokens','fingerprint']},ensure_ascii=True),flush=True)

def train(args):
    snapshot=json.loads(args.snapshot.read_text(encoding='utf8'));root=args.snapshot.resolve().parent
    if snapshot['token_ids']!=TOKENS or snapshot['older_recordings_included']:raise ValueError('Unexpected snapshot contract')
    records=snapshot['records'];holdout,skipped=choose_group_holdout(records)
    segments=json.loads(args.segments.read_text(encoding='utf8'))
    if segments['snapshot_sha256']!=sha(args.snapshot):raise ValueError('Wrong VAD manifest')
    by_source={r['source_index']:r for r in segments['entries']}
    if len(by_source)!=len(segments['entries']) or set(by_source)!=set(range(len(records))):raise ValueError('VAD coverage mismatch')
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'data').mkdir()
    features=[];labels=[];parents=[];kinds=[];full=[];preferred=[];ambiguous=[]
    def add(samples,parent,kind):
        if not 400<=len(samples)<=32240:raise ValueError('Input outside runtime bounds')
        i=len(features);features.append(raw_features(samples));labels.append(records[parent]['label']);parents.append(parent);kinds.append(kind)
        (args.output/'data'/('item_%03d.pcm'%i)).write_bytes(samples.astype('<i2').tobytes());return i
    for i,record in enumerate(records):
        path=(root/record['path']).resolve()
        if not path.is_relative_to(root) or sha(path)!=record['sha256']:raise ValueError('Frozen input mismatch')
        original=add(read_wave(path),i,'full_clip');full.append(original);chosen=original
        entry=by_source[i]
        if len(entry['segments'])==1:
            segment=entry['segments'][0];path=(args.segments.resolve().parent/segment['path']).resolve()
            if not path.is_relative_to(args.segments.resolve().parent) or sha(path)!=segment['sha256']:raise ValueError('VAD input mismatch')
            samples=np.frombuffer(path.read_bytes(),dtype='<i2').astype(np.int32)
            chosen=add(samples,i,'exact_vad')
            for left,right in [(1600,0),(0,1600),(1600,1600),(0,3200)]:
                if len(samples)+left+right<=32240:add(np.pad(samples,(left,right)),i,'vad_padding_%d_%d'%(left,right))
        else:ambiguous.append({'source_index':i,'token':record['token'],'segment_count':len(entry['segments']),'policy':'Keep accepted full clip only'})
        preferred.append(chosen)
    held_set=set(holdout);train_indices=[i for i,parent in enumerate(parents) if parent not in held_set]
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    held=fit(features,labels,train_indices,args.output/'sd77-holdout.xqt',args)
    candidate=fit(features,labels,list(range(len(features))),args.output/'sd77-candidate.xqt',args)
    metrics={}
    def evaluate(model,indices,integer):
        predictions=[x['prediction'] for x in model['int8_predictions']] if integer else model['float_predictions']
        return {'correct':sum(predictions[i]==labels[i] for i in indices),'total':len(indices)}
    for name,model,indices in [('holdout_full',held,[full[i] for i in holdout]),('holdout_vad_or_full',held,[preferred[i] for i in holdout]),
                             ('all_fit_full_resubstitution',candidate,full),('all_fit_vad_or_full_resubstitution',candidate,preferred)]:
        for integer in [False,True]:metrics[name+('_int8' if integer else '_float')]=evaluate(model,indices,integer)
    for name in ['sd77-holdout','sd77-candidate']:
        offset,scale,_=layers_from_file(args.output/(name+'.xqt'))
        for i,f in enumerate(features):(args.output/'data'/('item_%03d.%s.features'%(i,name))).write_bytes(normalize(f,offset,scale).tobytes())
    report={'schema':1,'status':'SD_ONLY_77_PARTIAL_VOCAB_TRAINED','architecture':[40,args.hidden1,args.hidden2,25],
        'format':'XQT1','epochs':args.epochs,'seed':args.seed,'token_ids':TOKENS,'recording_count':len(records),
        'class_counts':snapshot['counts'],'missing_tokens':snapshot['missing_tokens'],'older_recordings_included':False,
        'data_fingerprint':snapshot['fingerprint'],'snapshot_sha256':sha(args.snapshot),'segment_manifest_sha256':sha(args.segments),
        'holdout_parent_indices':holdout,'holdout_source_recordings':sorted({records[i]['source_recording'] for i in holdout}),
        'holdout_training_parents':len(records)-len(holdout),'holdout_skipped_groups':skipped,
        'holdout_policy':'Newest complete source whose removal retains all observed positive classes; no score-based selection',
        'feature_item_count':len(features),'feature_parent_indices':parents,'feature_kinds':kinds,'feature_labels':labels,
        'full_clip_item_indices':full,'preferred_item_indices':preferred,'ambiguous_vad_policy':ambiguous,
        'metrics':metrics,'holdout_model':held,'all_fit_candidate':candidate,
        'source_sha256':{n:sha(Path(__file__).with_name(n)) for n in ['train_sd_classifier.py','train_recorded_classifier.py','train_pilot_classifier.py','train_token_classifier.py','train_tdnn_ctc.py']},
        'limits':['Only22 positive classes; chonglai/tuichu and blank have no positive training samples',
            'Runtime25 token IDs retained without renumbering; missing outputs are not guaranteed suppressed',
            'Same-speaker one-source exploratory holdout; not independent accuracy acceptance',
            'All-fit model sees every selected parent; resubstitution is not held-out accuracy',
            'No old audio used in normalization, fitting or evaluation; no background rejection calibration']}
    save(args.output/'results.json',report)
    print(json.dumps(metrics,indent=2),flush=True);print('SD77_CANDIDATE',candidate['sha256'],candidate['bytes'],flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze');f.add_argument('dataset',type=Path);f.add_argument('output',type=Path)
    f.add_argument('--source-json',type=Path,action='append',required=True);f.add_argument('--expected-count',type=int,default=77)
    t=sub.add_parser('train');t.add_argument('snapshot',type=Path);t.add_argument('output',type=Path)
    t.add_argument('--segments',type=Path,required=True);t.add_argument('--hidden1',type=int,default=64);t.add_argument('--hidden2',type=int,default=32)
    t.add_argument('--epochs',type=int,default=600);t.add_argument('--seed',type=int,default=1)
    args=parser.parse_args()
    if args.command=='freeze':freeze(args)
    else:
        if not (1<=args.hidden1<=256 and 1<=args.hidden2<=256 and args.epochs>=4):parser.error('Invalid dimensions/epochs')
        train(args)
if __name__=='__main__':main()
