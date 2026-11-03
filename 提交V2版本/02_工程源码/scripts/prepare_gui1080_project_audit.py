"""Add missing frozen project documents/assets to a completed native candidate."""
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,subprocess,tarfile,uuid
from verify_cpu80_delivery import timing
from program_with_project_audit import adapt_voice75_functions

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['root','work','output']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--source-repo',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--voice-nnue-binding',type=Path,help='CPU75/70 hardware commit/native snapshot binding; final STA is independently required')
    a=ap.parse_args()
    root=a.root.resolve();work=a.work.resolve();out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
    result=dict(status='PREFLIGHT',started_utc=datetime.now(timezone.utc).isoformat(),root=str(root),added_files_sha256={},scope='Append missing files from the frozen implementation commit. Existing native files/inputs/outputs are retained. Full candidate audit only; no delivery archive or board operation.')
    def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    def run(name,command):
        log=out/(name+'.log')
        with log.open('xb') as stream:p=subprocess.run(list(map(str,command)),cwd=root,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
        result.setdefault('logs_sha256',{})[name]=sha(log);save();assert p.returncode==0,log
    save()
    try:
        if a.voice_nnue_binding:
            binding=read(a.voice_nnue_binding)
            assert binding['status']=='LOCAL_IMPLEMENTATION_COMMIT_AND_NATIVE_INPUT_HASHES_EQUAL_NOT_STA_OR_BOARD'
            assert sha(root/'artifacts/build_snapshot.json')==binding['snapshot_sha256']
            assert read(root/'config/clocks.json')['cpu_hz'] in (75000000,70000000)
            assert read(root/'config/display.json')['refresh_hz']==30
            flow=dict(native_root=binding['native_root'],run_id=binding['native_run'],
                      soc_implementation_commit=binding['source_commit'],
                      bitstream_sha256=sha(root/'artifacts/soc_top.sbit'))
            result['hardware_binding_sha256']=sha(a.voice_nnue_binding)
        else:
            flow=read(work/'flow.json');assert flow['status']=='COMBINED_ROM_GUI1080_NATIVE_ALL_GATES_PASS_BOARD_PENDING'
        assert Path(flow['native_root']).resolve()==root
        snapshot=read(root/'artifacts/build_snapshot.json');evidence=read(root/'artifacts/build_evidence.json')
        assert flow['run_id']==snapshot['run_id']==evidence['run_id']
        if a.voice_nnue_binding:assert len(snapshot['inputs'])==binding['inputs']
        assert evidence['timing']=='All Constraints Met' and timing((root/'artifacts/final_timing_xml.xml').read_bytes())==116
        stage=read(root/'candidate-stage.json');protected=stage['prepared_inputs']
        for table in [snapshot['inputs'],protected,evidence['outputs']]:
            for name,h in table.items():assert sha(root/name)==h,name
        assert sha(root/'artifacts/soc_top.sbit')==flow['bitstream_sha256']
        commit=flow['soc_implementation_commit'];assert len(commit)==40 and all(c in '0123456789abcdef' for c in commit)
        result.update(status='ADDING_MISSING_FROZEN_SOURCE_FILES',run_id=flow['run_id'],soc_implementation_commit=commit,bitstream_sha256=flow['bitstream_sha256']);save()
        commit_bound_inputs=set()
        with (out/'git-archive.stderr.log').open('xb') as errors:
            proc=subprocess.Popen(['git','archive','--format=tar',commit],cwd=a.source_repo,stdout=subprocess.PIPE,stderr=errors)
            with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
                for entry in archive:
                    name=PurePosixPath(entry.name)
                    assert not name.is_absolute() and '..' not in name.parts and '\\' not in entry.name and ':' not in entry.name
                    if entry.isdir():continue
                    assert entry.isfile(),entry.name
                    if entry.name in snapshot['inputs']:
                        assert hashlib.sha256(archive.extractfile(entry).read()).hexdigest()==snapshot['inputs'][entry.name],entry.name
                        commit_bound_inputs.add(entry.name)
                    path=root/entry.name
                    assert path.resolve().is_relative_to(root)
                    if path.exists():continue
                    path.parent.mkdir(parents=True,exist_ok=True)
                    temporary=path.with_name('.gui1080-auditcopy-'+uuid.uuid4().hex+'.tmp')
                    with temporary.open('xb') as stream:shutil.copyfileobj(archive.extractfile(entry),stream)
                    assert temporary.stat().st_size==entry.size and not path.exists()
                    temporary.replace(path);result['added_files_sha256'][entry.name]=sha(path)
            proc.stdout.close();assert proc.wait(timeout=120)==0
        assert commit_bound_inputs==set(snapshot['inputs']),'Frozen commit does not cover every native input'
        result['git_archive_stderr_sha256']=sha(out/'git-archive.stderr.log')
        for table in [snapshot['inputs'],protected,evidence['outputs']]:
            for name,h in table.items():assert sha(root/name)==h,name
        result.update(status='FROZEN_NATIVE_INPUTS_AND_OUTPUTS_UNCHANGED_AUDITING',protected_stage_files=len(protected),frozen_inputs=len(snapshot['inputs']));save()
        run('hashes',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command','. ./scripts/project_files.ps1; Write-ProjectHashes (Get-Location).Path'])
        audit=root/'scripts/audit_gui1080_candidate.ps1'
        if a.voice_nnue_binding:
            text,functions=adapt_voice75_functions(root,audit.read_text(encoding='utf-8-sig'))
            text=text.replace('$PSScriptRoot',"'"+str(root/'scripts').replace("'","''")+"'")
            audit=out/'voice75_project_audit_effective.ps1';audit.write_text(text,encoding='utf-8')
            result['inherited_function_sources']=functions
        run('project-audit',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',audit,'-Root',root,'-ExpectedRunId',flow['run_id'],'-CheckHashes'])
        assert b'SOC_GUI1080_CANDIDATE_PROJECT_AUDIT_PASS' in (out/'project-audit.log').read_bytes()
        for name,h in snapshot['inputs'].items():assert sha(root/name)==h,name
        for name,h in evidence['outputs'].items():assert sha(root/name)==h,name
        result.update(status='GUI1080_COMPLETE_FROZEN_PROJECT_AUDIT_PASS_NOT_DELIVERY_OR_BOARD',snapshot_sha256=sha(root/'artifacts/build_snapshot.json'),evidence_sha256=sha(root/'artifacts/build_evidence.json'),audit_script_sha256=sha(audit),project_hashes_sha256=sha(root/'SHA256SUMS.txt'))
    except Exception as error:result.update(status='FAILED_CANDIDATE_PROJECT_AUDIT_PRESERVED',error=repr(error));raise
    finally:
        result['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(result['status'])

if __name__=='__main__':main()
