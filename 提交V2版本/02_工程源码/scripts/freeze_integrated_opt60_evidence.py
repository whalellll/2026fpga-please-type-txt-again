"""Save completed optimization preflight evidence, without making a delivery ZIP."""
from pathlib import Path
import argparse, gzip, hashlib, json, shutil
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,default=ROOT/'docs/validation/integrated-opt60-preflight-20261024');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    gate=ROOT/'build/opt60-gates-01.json';gates=json.loads(gate.read_text());assert gates['status']=='INTEGRATED_OPT60_CORRECTNESS_SOFTWARE_RESOURCE_GATES_PASS_NOT_STA_OR_BOARD'
    files={}
    for rel in gates['checks']:
        source=ROOT/'build'/rel
        target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        assert sha(source)==sha(target);files[rel]=sha(target)
    shutil.copyfile(gate,out/'gates.json');files['gates.json']=sha(out/'gates.json')
    log=ROOT/'build/batch60-full-regression-integrated-opt60-02.log'
    with gzip.open(out/'full-regression.log.gz','wb') as f:f.write(log.read_bytes())
    files['full-regression.log.gz']=sha(out/'full-regression.log.gz')
    history=[]
    for name in ['iopt60s1','iopt60s2','iopt60s3']:
        native=Path('G:/')/name;receipt=native/'resource-evidence/result.json'
        target=out/(name+'-receipt.json');shutil.copyfile(receipt,target);files[target.name]=sha(target)
        history.append(dict(native_root=native.as_posix(),receipt_sha256=sha(receipt),
                            conclusion='Compile multi-writer failure' if name.endswith('1') else 'Synthesis success, rejected register-file expansion/over-capacity' if name.endswith('2') else 'Synthesis and actual resource/retention checks pass; not STA'))
        snr=native/'pds/synthesize/soc_top.snr'
        if snr.exists():
            with gzip.open(out/(name+'-synthesis.snr.gz'),'wb') as f:f.write(snr.read_bytes())
            files[name+'-synthesis.snr.gz']=sha(out/(name+'-synthesis.snr.gz'))
    record=dict(status='INTEGRATED_OPT60_PREFLIGHT_FROZEN_NOT_STA_OR_BOARD',files=files,history=history,
                gate_sha256=sha(gate),scope='Local implementation preflight only. No formal package, media write, board pass or remote push.')
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'])
if __name__=='__main__':main()
