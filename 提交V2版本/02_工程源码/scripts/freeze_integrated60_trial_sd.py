"""Save exact trial boot inputs for the temporary branch, without SD/Flash IO."""
from pathlib import Path
import argparse,hashlib,json,shutil
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--materialize',type=Path);ap.add_argument('--resume',action='store_true');a=ap.parse_args()
    stored=R/'artifacts/integrated60_linefix_trial_20261024/sd-inputs'
    if a.materialize is None:
        source=R/'build/integrated-stream-sd-kit-01';m=read(source/'manifest.json')
        assert m['voice_stream_enabled'] and m['cpu_hz']==60000000 and len(m['tests'])==18
        if stored.exists():
            assert a.resume and not (stored/'input-map.json').exists()
            assert sha(stored/'manifest.json')==sha(source/'manifest.json')
        else:stored.mkdir()
        def copy_exact(src,dst):
            if dst.exists():assert sha(dst)==sha(src)
            else:shutil.copyfile(src,dst)
        copy_exact(source/'manifest.json',stored/'manifest.json')
        mapping={}
        for name,row in m['sd_root_files'].items():
            p=source/'sd-root'/name;assert sha(p)==row['sha256']
            if name in ['pikafish.pff','pikafish.atk']:
                target=R/'linux/boot'/name;assert sha(target)==sha(p)
            else:
                target=stored/'payloads'/name;target.parent.mkdir(exist_ok=True);copy_exact(p,target)
            mapping[name]=dict(source=target.relative_to(R).as_posix(),sha256=sha(target),bytes=target.stat().st_size)
        (stored/'evidence').mkdir(exist_ok=a.resume)
        for name in m['tests']:
            p=source/'evidence'/name;assert b'HOST_TEST_PASS' in p.read_bytes()
            copy_exact(p,stored/'evidence'/name)
        proof=dict(status='EXACT_BOARD_TRIAL_SD_INPUTS_NOT_FORMAL_DELIVERY',manifest_sha256=sha(stored/'manifest.json'),
            files=mapping,loader_evidence_sha256={name:sha(stored/'evidence'/name) for name in m['tests']},trial_hardware_manifest_sha256=sha(stored.parent/'manifest.json'),
            scope='Original software SD manifest/write receipt unchanged. Board result stores separate compatible-payload binding to timing-failed native4. Official Pikafish weights reuse tracked linux/boot files. No new media write or formal package.')
        (stored/'input-map.json').write_text(json.dumps(proof,indent=2)+'\n')
        print(proof['status']);return
    proof=read(stored/'input-map.json');m=read(stored/'manifest.json')
    assert sha(stored/'manifest.json')==proof['manifest_sha256']
    assert sha(stored.parent/'manifest.json')==proof['trial_hardware_manifest_sha256']
    assert set(proof['files'])==set(m['sd_root_files']) and len(proof['files'])==8
    assert not a.materialize.exists();a.materialize.mkdir(parents=True);(a.materialize/'sd-root').mkdir()
    for name,row in proof['files'].items():
        p=R/row['source'];assert sha(p)==row['sha256']==m['sd_root_files'][name]['sha256']
        shutil.copyfile(p,a.materialize/'sd-root'/name)
        assert sha(a.materialize/'sd-root'/name)==row['sha256']
    shutil.copyfile(stored/'manifest.json',a.materialize/'manifest.json')
    shutil.copytree(stored/'evidence',a.materialize/'evidence')
    for name in m['tests']:
        assert b'HOST_TEST_PASS' in (a.materialize/'evidence'/name).read_bytes()
        assert sha(a.materialize/'evidence'/name)==proof['loader_evidence_sha256'][name]
    result=dict(status='TRIAL_SD_MATERIALIZED_ALL_EIGHT_BYTE_HASHES_AND_18_LOADER_RECEIPTS_PASS_NOT_MEDIA_WRITE',manifest_sha256=proof['manifest_sha256'],files=proof['files'],source_script_sha256=sha(Path(__file__)))
    (a.materialize/'materialize-result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()
