"""SD-only selection and whole-source holdout rules; no training or board I/O."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'linux/voice'))
from train_sd_classifier import choose_group_holdout,is_selected,TOKENS

allowed={'sd1','sd2','sd3'}
assert is_selected({'status':'human_accepted','token':'ma','parent_recording_sha256':'sd1'},allowed)
assert not is_selected({'status':'human_accepted','token':'ma','parent_recording_sha256':'older'},allowed)
assert not is_selected({'status':'pending','token':'ma','parent_recording_sha256':'sd1'},allowed)
assert not is_selected({'status':'human_accepted','token':'ma','raw_sha256':'sd1'},allowed)
assert not is_selected({'status':'human_accepted','token':'invalid','parent_recording_sha256':'sd1'},allowed)
records=[]
for group,session,words in [('sd1','1',['ma','liu']),('sd2','2',['ma','liu']),('sd3','3',['pao'])]:
    records += [{'parent_group_sha256':group,'session':session,'token':word} for word in words]
hold,skipped=choose_group_holdout(records)
assert hold==[2,3] and skipped==[{'group':'sd3','missing_training_tokens':['pao']}]
train_groups={r['parent_group_sha256'] for i,r in enumerate(records) if i not in hold}
held_groups={records[i]['parent_group_sha256'] for i in hold}
assert not train_groups & held_groups
assert TOKENS.index('ma')==2 and TOKENS.index('pao')==3 and len(TOKENS)==25
try:choose_group_holdout([{'parent_group_sha256':'one','session':'1','token':'ma'}])
except ValueError:pass
else:raise AssertionError('No valid group holdout must not become a random clip split')
print('SD_ONLY_TRAINING_POLICY_PASS: no older audio, whole-source split, coverage, unchanged token ABI')
