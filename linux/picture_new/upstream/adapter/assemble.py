"""Copy R1 patch sources unchanged and bind both immutable deliveries."""
import hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    output=HERE/'adapter_manifest.json'
    if output.exists():raise SystemExit('adapter manifest exists; verify it rather than overwrite provenance')
    r1=REPO/'artifacts/board_detect_v2_round1';r2=REPO/'artifacts/vision-model-20261020'
    registry=json.loads((r1/'manifest.json').read_text(encoding='utf-8'))['files_sha256']
    assert all(digest(r1/n)==h for n,h in registry.items()),'R1 identity failure'
    files={}
    def copy(source,name,reason):
        dest=HERE/name
        assert not dest.exists(),name
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        files[name]={'source_package':'r1','source_path':source.relative_to(r1).as_posix(),
                     'bytes':dest.stat().st_size,'sha256':digest(dest),'reason':reason}
    for p in (r1/'geometry_fallback').rglob('*'):
        if p.is_file():copy(p,'geometry_fallback/'+p.relative_to(r1/'geometry_fallback').as_posix(),'Required piece_fit algorithm and synthetic vectors; stays disabled')
    # R1 stores the C implementation beside, not inside, geometry_fallback.
    for p in (r1/'geometry/c_ref').rglob('*'):
        if p.is_file():copy(p,'geometry_fallback/c_ref/'+p.relative_to(r1/'geometry/c_ref').as_posix(),'Delivered C piece_fit implementation and harness dependencies')
    for p in (r1/'geometry').glob('*.py'):
        copy(p,'geometry/'+p.name,'Unchanged Python geometry dependency for R1 evaluation protocol')
        copy(p,'geometry_fallback/'+p.name,'Resolve piece_fit relative imports without editing delivered Python')
    copy(r1/'geometry_fallback/piece_fit.py','geometry/piece_fit.py','R1 test evaluator geometry dependency')
    copy(r1/'tools/test_eval_t1.py','evaluation/r1_test_eval_t1.py','Frozen R1 scoring protocol; adapter calls functions, not its CUDA main')
    copy(r1/'report/dataset_corrections.json','dataset_corrections.json','Authoritative 81 corrections, including game 3; R2 subset is insufficient')
    copy(r1/'report/fen_gt.json','fen_gt.json','1042 frame truth for later acceptance/regression')
    corrections=json.loads((HERE/'dataset_corrections.json').read_text(encoding='utf-8'))
    truth=json.loads((HERE/'fen_gt.json').read_text(encoding='utf-8'));assert len(corrections['corrections'])==81 and len(truth)==1042
    intake=json.loads((REPO/'docs/validation/picture-p20-combined-20261020/intake.json').read_text(encoding='utf-8'))
    m={'schema_version':1,'scheme':'board-detect-v2','base_format_profile':'training-handoff-current-three-model-v1',
       'purpose':'R2 three-model candidate + R1 evaluation/corrections/fallback patch; NOT M0 acceptance',
       'piece_fit_enabled':False,'sources':{key:{'directory':'../'+directory.name,'manifest_sha256':digest(directory/'manifest.json'),
           'archive_sha256':intake[key]['archive_sha256']} for key,directory in [('r1',r1),('r2',r2)]},'files':files,
       'correction_count':81,'fen_record_count':1042,
       'c_reference_location_note':'R1 geometry_fallback contains Python/vectors; actual geom_piece_fit C body is geometry/c_ref/geometry_ref.c, copied unchanged',
       'independence_note':'R2 training_manifest explicitly marks existing game 3 as reused failure-analysis data; numerical replay does not establish independence'}
    output.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('P20_ADAPTER_ASSEMBLED',len(files),'provenance-bound copies; piece_fit disabled')
if __name__=='__main__':main()
