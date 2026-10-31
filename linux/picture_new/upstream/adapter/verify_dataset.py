"""Bind raw evaluation inputs to the original training handoff hash lists."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
DESKTOP=Path('C:/Users/dogandlamb/Desktop')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hashes(path):
    return {line.split()[1].lstrip('*').replace('\\','/'):line.split()[0] for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()}
def main():
    original=DESKTOP/'训练交付包_新方案_20261018';dataset=DESKTOP/'图像数据集'
    board_hashes=hashes(original/'board_labels_sha256.txt');data_hashes=hashes(original/'dataset_sha256.txt')
    records=[];mismatches=[];unregistered=[]
    for idx in range(908,1043):
        stem=f'IMG{idx:05d}';entry={'frame':stem}
        for kind,path,registry,key in (
            ('image',dataset/'in'/(stem+'.PNG'),data_hashes,'in/'+stem+'.PNG'),
            ('pieces',dataset/'out'/(stem+'.json'),data_hashes,'out/'+stem+'.json'),
            ('board',original/'board'/(stem+'.json'),board_hashes,'board/'+stem+'.json')):
            actual=sha(path);expected=registry.get(key)
            entry[kind]={'path':str(path),'sha256':actual,'baseline_sha256':expected}
            if expected is None:unregistered.append(key)
            elif actual!=expected:mismatches.append(key)
        records.append(entry)
    report={'frames':135,'range':[908,1042],'records':records,'mismatches':mismatches,'unregistered':unregistered,
            'board_dir':str(original/'board'),'board_hash_list_sha256':sha(original/'board_labels_sha256.txt'),
            'data_hash_list_sha256':sha(original/'dataset_sha256.txt'),'corrections_applied_in_memory_only':True,
            'independent_test':False,'reason':'R2 declares reused game 3 failure-analysis set'}
    out=REPO/'docs/validation/picture-p20-combined-20261020/dataset-inputs.json'
    with out.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('P20_DATASET_HASH_CHECK',len(records),'frames mismatches',mismatches,'unregistered',unregistered[:5])
    if mismatches:raise SystemExit(1)
if __name__=='__main__':main()
