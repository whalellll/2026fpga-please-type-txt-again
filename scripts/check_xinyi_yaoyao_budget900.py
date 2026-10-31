"""Independently check the finite native-rate900ms candidate; no playback."""
import argparse, copy, hashlib, itertools, json, statistics, wave
from pathlib import Path
from picture_workspace import ROOT, workspace_path
from check_xinyi_yaoyao_phrases import validate_row
SHA=lambda b:hashlib.sha256(b).hexdigest()
RATES=[1.2,1.25,1.3,1.35,1.4,1.45,1.5]
CAP=14400

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
 a=ap.parse_args();candidate,reference,out=map(workspace_path,[a.candidate,a.reference,a.output]);out.mkdir(parents=True,exist_ok=False)
 mb=(candidate/'manifest.json').read_bytes();m=json.loads(mb);rb=(reference/'manifest.json').read_bytes();r=json.loads(rb)
 assert m['schema']=='xinyi-whole-phrase-budget900-candidate/1' and m['complete'] and m['expected_entries']==5103
 assert m['format']=='s16le' and m['sample_rate']==16000 and m['channels']==1 and m['voice']=='Microsoft Yaoyao'
 assert not m['resampled'] and not m['interior_clipped'] and not m['automatically_played'] and not m['hearing_verified'] and not m['board_tested']
 assert m['pcm_target_samples']==CAP and m['maximum_native_rate']==1.5 and m['edge_context_samples']==240
 assert SHA(rb)==m['source_manifest_sha256'] and rb==(candidate/'evidence/reference-manifest.json').read_bytes()
 expected=set(itertools.product(range(16,25),range(1,10),range(25,28),range(1,10)))|set(itertools.product(range(28,31),range(16,25),range(25,28),range(1,10)))|set(itertools.product(range(1,10),range(16,25),range(25,28),range(1,10)))
 assert len(expected)==5103 and {tuple(v['tokens']) for v in m['files'].values()}==expected
 assert {p.relative_to(candidate).as_posix() for p in (candidate/'whole').iterdir()}==set(m['files'])
 prior=json.loads((reference/'attempts.json').read_text(encoding='utf8'));new=json.loads((candidate/'attempts.json').read_text(encoding='utf8'))
 copied=0;generated=0;durations=[];total=0
 for n,row in m['files'].items():
  payload=(candidate/n).read_bytes();validate_row(n,row,payload)
  assert row['native_rate'] in RATES and row['over900ms']==(row['samples']>CAP)
  old=r['files'][n]
  assert all(row[k]==old[k] for k in ['tokens','text','spoken_text'])
  known=[old]+[v for v in prior.get(n,[]) if v['sha256']!=old['sha256']]
  fitting=sorted([v for v in known if v['samples']<=CAP],key=lambda v:v['native_rate'])
  if fitting:
   assert n not in new and row['sha256']==fitting[0]['sha256'] and row['native_rate']==fitting[0]['native_rate']
   origin=Path(row['origin_path']);assert origin.is_relative_to(reference) and SHA(origin.read_bytes())==row['sha256']
   copied+=1
  else:
   tried=new[n];start=max(v['native_rate'] for v in known);rates=[v for v in RATES if v>start]
   assert tried and [v['native_rate'] for v in tried]==rates[:len(tried)]
   assert all(v['samples']>CAP for v in tried[:-1])
   assert tried[-1]['samples']<=CAP or tried[-1]['native_rate']==1.5
   assert row['sha256']==tried[-1]['sha256'] and row['native_rate']==tried[-1]['native_rate']
   for trial in tried:
    origin=Path(trial['origin_path']);assert origin.is_relative_to(candidate/'attempts')
    validate_row(n,trial,origin.read_bytes())
    assert all(trial[k]==old[k] for k in ['tokens','text','spoken_text'])
   generated+=1
  durations.append(row['duration_ms']);total+=len(payload)
 assert copied==1373==m['copied_original_900_clips'] and generated==3730 and len(new)==3730
 assert m['native_rate_histogram']=={str(v):sum(row['native_rate']==v for row in m['files'].values()) for v in RATES}
 assert m['pcm_bytes']==total and m['maximum_samples']==max(v['samples'] for v in m['files'].values())
 assert m['over900ms']==sum(d>900 for d in durations) and m['over960ms']==sum(d>960 for d in durations)
 for n,h in m['source_sha256'].items():assert SHA((candidate/'source'/n).read_bytes())==h
 pairs=0
 for p in (candidate/'audition-pairs').glob('*.wav'):
  label,key=p.stem.split('-',1);base=reference if label=='old960' else candidate
  assert label in ['old960','new900']
  with wave.open(str(p)) as w:
   assert w.getframerate()==16000 and w.getnchannels()==1 and w.getsampwidth()==2
   assert w.readframes(w.getnframes())==(base/'whole'/(key+'.pcm')).read_bytes()
  pairs+=1
 n=next(iter(m['files']));row=m['files'][n];data=(candidate/n).read_bytes();bad=bytearray(data);bad[len(bad)//2]^=1
 negatives=[]
 for label,name,metadata,payload in [('corrupt-one-byte',n,row,bad),('wrong-fixed-token-filename','whole/00-00-00-00.pcm',row,data),('odd-pcm-length',n,row,data[:-1]),('invalid-token-prefix',n,{**row,'tokens':[0,16,25,1]},data)]:
  try:validate_row(name,metadata,payload)
  except AssertionError:negatives.append(label)
  else:raise AssertionError('Accepted negative '+label)
 assert (reference/'manifest.json').read_bytes()==rb
 result=dict(status='BUDGET900_5103_CLOSURE_NATIVE_RATE_FIRST_FIT_SHA_FORMAT_PAIRS_NEGATIVES_PASS_NOT_BOARD_OR_HEARING',hardware_used=False,automatically_played=False,physical_1000ms_pass=False,manifest_sha256=SHA(mb),reference_manifest_sha256=SHA(rb),complete_count=5103,copied_original_900_clips=copied,newly_synthesized_phrases=generated,total_attempts=sum(len(v) for v in new.values()),pcm_bytes=total,minimum_ms=min(durations),median_ms=statistics.median(durations),maximum_ms=max(durations),over900ms=sum(d>900 for d in durations),native_rate_histogram=m['native_rate_histogram'],audition_pair_wavs_exact=pairs,negative_controls=negatives,checker_sha256=SHA(Path(__file__).read_bytes()),source_sha256=m['source_sha256'])
 (out/'checker.py').write_bytes(Path(__file__).read_bytes());(out/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))

if __name__=='__main__':main()
