"""Policy faults for derived artifact-manifest restoration; no hardware proof."""
from pathlib import Path
import argparse,hashlib,json,tempfile
from run_main70_extracted_regression import validate_rebuilt_artifact_manifest

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output.resolve();needroot=Path('G:/fpga').resolve();assert out.is_relative_to(needroot) and not out.exists();out.mkdir(parents=True)
    sha=lambda b:hashlib.sha256(b).hexdigest();cases=[]
    with tempfile.TemporaryDirectory(dir=out) as temp:
        root=Path(temp);(root/'artifacts').mkdir()
        initial={'code.bin':b'unchanged firmware','code.elf':b'unchanged ELF','code.build.json':b'{"build":1}','evidence.json':b'{"native":1}'}
        old={n:sha(b) for n,b in initial.items()};original={'artifacts/'+n:h for n,h in old.items()}
        sealed=''.join(h+'  '+n+'\n' for n,h in old.items()).encode()
        def trial(name,data,rows,metadata,passed):
            for n,b in initial.items():(root/'artifacts'/n).write_bytes(data.get(n,b))
            (root/'artifacts/SHA256SUMS.txt').write_bytes(rows)
            try:validate_rebuilt_artifact_manifest(root,sealed,metadata,original)
            except (ValueError,UnicodeError):ok=False
            else:ok=True
            assert ok==passed,(name,ok);cases.append(dict(name=name,accepted=ok))
        reorder=''.join(old[n]+'  '+n+'\r\n' for n in reversed(old)).encode();trial('reorder-and-crlf',{},reorder,{},True)
        meta=b'{"build":2}';new={**old,'code.build.json':sha(meta)}
        rows=lambda m:''.join(h+'  '+n+'\n' for n,h in m.items()).encode()
        trial('verified-build-json-only',{'code.build.json':meta},rows(new),{'artifacts/code.build.json':sha(meta)},True)
        trial('changed-firmware-rejected',{'code.bin':b'changed'},rows({**old,'code.bin':sha(b'changed')}),{'artifacts/code.bin':sha(b'changed')},False)
        trial('native-evidence-json-rejected',{'evidence.json':b'changed'},rows({**old,'evidence.json':sha(b'changed')}),{'artifacts/evidence.json':sha(b'changed')},False)
        trial('missing-name-rejected',{},rows({n:h for n,h in old.items() if n!='code.elf'}),{},False)
        trial('extra-name-rejected',{},rows({**old,'unknown.bin':'0'*64}),{},False)
        trial('duplicate-name-rejected',{},sealed+sealed.splitlines()[0]+b'\n',{},False)
        trial('wrong-digest-rejected',{},rows({**old,'code.elf':'0'*64}),{},False)
        trial('unbound-metadata-rejected',{'code.build.json':meta},rows(new),{},False)
        trial('escaping-name-rejected',{},sealed+b'0'*64+b'  ../code.bin\n',{},False)
    record=dict(status='MAIN70_REGENERATED_ARTIFACT_MANIFEST_POLICY_PASS_NOT_BOARD',cases=cases,hardware_used=False)
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'],len(cases))

if __name__=='__main__':main()
