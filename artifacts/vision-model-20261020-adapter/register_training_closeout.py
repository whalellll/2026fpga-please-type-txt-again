"""Register r19-r23 reports and attribution identities without inference or extraction.

Photographs, selection crops, prelabels and game2 materials are never opened.
ZIP SHA identifies the transport; CRC/SHA verification covers explicitly selected
non-image members only. r19 is a report-level dispatch-copy receipt, not a claim
to possess or authenticate its absent original ZIP.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,re,stat,zipfile
from collections import Counter

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REGISTRY=HERE/'evaluation/training_closeout_r19_r23.json'
CLOSED='closed-unmet: r19-r23 attribution/QAT concluded; INT 68/84 below 73/84'
ARCHIVES={
 'r20':('train_side_r20.zip','4cca4d316525d7fc7f744feecf41b39edef95bdd4ccbdd517b156208df7fdf1d'),
 'r21':('training_side_20261024_r21.zip','2fadf8044fe96fde4359be5a0672e8b5b8e40a34bf14d24edea707c5bd9decf9'),
 'r22':('training_side_20261025_r22.zip','2354fcafbfc6539e60cf33be996a47ef1a0406f6a07a2768a5e6e9391da4e4cb'),
 'r23':('training_side_20261025_r23.zip','2755994217c76ee6df8c41526ac4098d5b713dcccd6b9d81006a188d01de8f50')}

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def identity(data):return dict(bytes=len(data),sha256=sha(data))
def tree_digest(rows):
    return sha(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def baseline(config):
    p=config['profiles']['working-r14']
    return dict(selected=config['selected'],default_profile=config['default_profile'],default_backend=config['default_backend'],
        models={k:v['sha256'] for k,v in p['models'].items()},quantized_graph_sha256=p['quantized_graph_sha256'],
        candidate_filter=p['candidate_filter'],refinement=p['refinement'],quantized_gate=p['quantized_gate'],production_ready=config['production_ready'])
def apply_metadata():
    """Also usable after the historical r14 reconstruction; only status metadata."""
    if not REGISTRY.is_file():return False
    record=load(REGISTRY);path=HERE/'working_combination.json';config=load(path)
    require(baseline(config)==record['baseline'],'Closeout belongs to a different selected model set')
    config['integer_acceptance']=CLOSED;config['profiles']['working-r14']['integer_acceptance']=CLOSED
    config['profiles']['rollback-v3d']['integer_acceptance']='closed-historical: r13 rollback is unselected; no ongoing attribution/QAT'
    config['training_closeout_registry']='evaluation/training_closeout_r19_r23.json'
    candidate_path=HERE/config['registration'];candidate=load(candidate_path)
    require(candidate['model_sha256']==record['baseline']['models'] and not candidate['quantized_gate'] and not candidate['production_ready'],'Candidate identity/gate changed')
    candidate.update(integer_acceptance=CLOSED,training_line_status='closed-after-second-QAT-failure',
        game2_decision_window='closed-unused',training_closeout_registry='evaluation/training_closeout_r19_r23.json')
    write(path,config);write(candidate_path,candidate)
    rollback_path=HERE/'candidates/candidate_r13_e_v3d/registration.json';rollback=load(rollback_path)
    require(not rollback['selected_for_work'] and not rollback['quantized_gate'] and not rollback['production_ready'],'Historical rollback became selected')
    rollback.update(integer_acceptance='closed-historical: r13 rollback is unselected; no ongoing attribution/QAT',
        training_closeout_registry='evaluation/training_closeout_r19_r23.json')
    write(rollback_path,rollback)
    infrastructure_path=HERE/'training_infrastructure.json';infrastructure=load(infrastructure_path)
    infrastructure['closeout_registry']='evaluation/training_closeout_r19_r23.json'
    infrastructure['classification']='archived reusable infrastructure; training line closed after r23'
    write(infrastructure_path,infrastructure)
    return True

def collect(archive_dir,dispatch,private):
    config=load(HERE/'working_combination.json');before=baseline(config)
    require(before['default_profile']=='working-r14' and before['default_backend']=='fp32' and not before['quantized_gate'] and not before['production_ready'],'Unexpected active baseline')
    for item in config['profiles']['working-r14']['models'].values():
        require(sha((ROOT/config['profiles']['working-r14']['root']/item['path']).read_bytes())==item['sha256'],'Selected FP32 weight changed')
    profile=config['profiles']['working-r14']
    require(sha((ROOT/profile['quantized_candidate']/'integer_graph.json').read_bytes())==profile['quantized_graph_sha256'],'Selected exact-int graph changed')
    candidates={};assets={};private_rows={};payload={};dispatch_checked=0
    for rnd,(name,expected) in ARCHIVES.items():
        archive=archive_dir/name;archive_before=identity(archive.read_bytes())
        require(archive_before['sha256']==expected,'Archive SHA mismatch: '+rnd)
        with zipfile.ZipFile(archive,metadata_encoding='gbk') as z:
            entries={};seen=set()
            for i in z.infolist():
                p=PurePosixPath(i.filename)
                require(not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and ':' not in i.filename and
                    not stat.S_ISLNK(i.external_attr>>16) and i.filename.casefold() not in seen,'Unsafe or duplicate ZIP path')
                seen.add(i.filename.casefold())
                if not i.is_dir():entries[i.filename]=i
            selected={}
            for n,i in entries.items():
                if re.search(r'game[ _-]?2',n,re.I):continue
                if rnd=='r21':
                    allowed=(n.startswith('补交归档/truth_v2_camv2/') or n=='补交归档/matrix_v2.json' or
                        n=='test_gradient_fix.py' or (n.count('/')==0 and n.endswith('.md')))
                else:allowed=Path(n).suffix.lower() in ('.md','.json','.jsonl','.py')
                if not allowed:continue
                require(Path(n).suffix.lower() in ('.md','.json','.jsonl','.py'),'Non-text payload is outside report intake')
                raw=z.read(i) # ZIP library checks CRC; no extraction, import or execution.
                local=dispatch/('train_side_'+rnd)/n
                require(local.is_file() and local.read_bytes()==raw,'Dispatch copy differs or is absent: '+rnd)
                dispatch_checked+=1;selected[n]=identity(raw);payload[(rnd,n)]=raw
            reports={n:v for n,v in selected.items() if n.endswith('.md')}
            require(len(reports)==1,'Expected one report: '+rnd)
            candidates[rnd]=dict(source_kind='original_zip_and_matching_dispatch_copy',archive=name,**archive_before,
                archive_members=len(entries),selected_text_members=len(selected),
                selected_members_digest=tree_digest(selected),reports=reports,
                zip_namespace_verified=True,selected_members_crc_verified=True,publisher_whole_file_manifest=False,
                full_payload_intake_claimed=False,unopened_members=len(entries)-len(selected))
            private_rows[rnd]=selected
        require(identity(archive.read_bytes())==archive_before,'Archive changed during intake')
    r19=dispatch/'train_side_r19/train_side_r19'
    report=next(r19.glob('00_*.md'));recal=r19/'matrix_v2_detrecal.json'
    candidates['r19']=dict(source_kind='dispatch_report_snapshot',original_archive_available=False,archive_sha256=None,
        report=dict(path=report.relative_to(ROOT).as_posix(),**identity(report.read_bytes())),
        recalibration_report=dict(path=recal.relative_to(ROOT).as_posix(),**identity(recal.read_bytes())),
        full_payload_intake_claimed=False,supplementary_assets_transport='r21')
    for rnd,prefix in [('r20','train_side_r20/truth_v2_camv2/'),('r21','补交归档/truth_v2_camv2/')]:
        group={n.removeprefix(prefix):v for n,v in private_rows[rnd].items() if n.startswith(prefix)}
        labels=[n for n in group if re.fullmatch(r'IMG[0-9]+\.json',n)]
        require(len(group)==181 and len(labels)==178,'Truth directory coverage mismatch')
        versions=Counter(json.loads(payload[(rnd,prefix+n)]).get('version') for n in labels)
        assets['truth_'+rnd]=dict(transport=rnd,member_prefix=prefix,files=len(group),frames=len(labels),
            directory_digest=tree_digest(group),observed_version_counts=dict(sorted(versions.items())),
            local_path=(dispatch/('train_side_'+rnd)/prefix).relative_to(ROOT).as_posix(),
            role='attribution-only',selected_for_model_runtime=False,
            release='truth-v2-final/1' if rnd=='r21' else 'provisional-superseded-by-r21')
    # r21 updates precisely the 16 residual-case files. The other 162 preserve
    # their original version field; the collection release is declared by r21.
    require(assets['truth_r21']['observed_version_counts']=={
        'camera-v2-truth-v2-final/1':16,'camera-v2-truth-v2/1':162},'Final truth version distribution mismatch')
    assets['truth_r21'].update(release_authority='r21 finalization report',
        zero_rule_violations='reported by training/user review; not independently re-evaluated',
        per_frame_version_fields_preserved=True)
    official=json.loads(payload[('r21','补交归档/truth_v2_camv2/fen_truth_official.json')])
    corrections=json.loads(payload[('r21','补交归档/truth_v2_camv2/corrections_log.json')])
    require(len(official)==len(corrections)==178,'Truth summary coverage mismatch')
    matrix_member='补交归档/matrix_v2.json';matrix_raw=payload[('r21',matrix_member)];matrix=json.loads(matrix_raw)
    require(matrix['_meta']['metric']=='agreement vs all-FP32' and matrix['_meta']['game2_contact']=='NONE','Matrix metric/contact mismatch')
    aggregates={}
    for key,expected in [('cls_int',176),('det_int',161),('board_int',175),('all_int',156)]:
        row=matrix[key];require(row['frames']==178 and row['fen_equal_vs_fp32']==expected,'Matrix aggregates changed')
        aggregates[key]={k:row[k] for k in ['fen_equal_vs_fp32','frames','crop_class_agree']}
    assets['matrix_v2']=dict(transport='r21',member=matrix_member,**identity(matrix_raw),
        local_path=(dispatch/'train_side_r21'/matrix_member).relative_to(ROOT).as_posix(),
        role='attribution-only',metric='agreement_vs_all_FP32',independent_accuracy=False,aggregates=aggregates)
    assets['r21_gradient_fix_test']=dict(transport='r21',member='test_gradient_fix.py',
        **identity(payload[('r21','test_gradient_fix.py')]),role='archived-training-side-test',
        reported_result='PASS',executed_by_engineering=False,selected_for_model_runtime=False)
    qat={}
    for rnd,eval_member in [('r22','qat_eval_v3.json'),('r23','eval_results.json')]:
        training=json.loads(payload[(rnd,'training_config.json')]);results=json.loads(payload[(rnd,eval_member)])
        require(all(row['fen_eq']==17 and row['frames']==60 for row in results.values()),'QAT aggregate mismatch')
        qat[rnd]=dict(result='failed',metric='agreement_vs_FP32_on_selection_set',fen_equal=17,frames=60,
            epochs=training['epochs'],gradient_norm=training['grad_norm'],wrapped_modules=training['wrapped'],
            root_cause_source='training-side reports; not independently retrained')
    qat['r22']['reported_root_cause']='MSE distillation optimized feature differences instead of detection loss'
    qat['r23'].update(reported_root_cause='Correct ComputeLoss still diverged under IQConv STE gradients and the stated budget',
        learning_rate=3e-6,batch=4,reported_gradient_clip=5.0,reported_epoch1_weight_delta=27.36,
        reported_epoch40_weight_delta=27.20,reported_loss_start=18.10,reported_loss_end=3.51)
    out=dict(schema_version=1,status='ARCHIVAL_CLOSEOUT_REGISTERED_NOT_MODEL_OR_BOARD_ACCEPTANCE',date='2026-10-25',
        source_spec='docs/PictureNew_r19-r23接收_收官登记_工程提示词_20261025.md',
        baseline=before,deliveries={k:candidates[k] for k in ['r19','r20','r21','r22','r23']},attribution_assets=assets,
        training_line=dict(status='closed-after-second-QAT-failure',third_round=False,new_weight_selection=False,
            game2_decision_window='closed-unused',future_game2_reopening_requires_new_authorization=True,
            future_game2_policy='zero engineering contact; single independent external decision only',
            integer_quality_gap='closed-unmet',reported_INT_correct=68,frames=84,
            required_correct=73,reported_FP32_correct=75,reported_FP32_conflicts=0,
            reported_r19_scale_recalibration=dict(dev37_before=36,dev37_after=35,frames=37,
                detector_agreement_before=161,detector_agreement_after=154,attribution_frames=178),
            reported_r16_gradient_break='ties_even_div interrupted gradients; r21 training-side unit tests report PASS',
            qat=qat),
        policy=dict(production_ready=False,full_integer_pipeline=False,quantized_gate=False,
            photographs_opened=0,game2_sealed_materials_opened=0,inference_runs=0,training_runs=0,hardware_used=False,
            copied_weights=False,truth_FEN_or_frame_identifiers_committed=False,
            accuracy_claim_from_matrix=False,original_failures_preserved=True),
        verification=dict(dispatch_text_files_compared=dispatch_checked,archive_metadata_encoding='gbk for legacy names; UTF8-flagged names remain UTF8',
            payload_scripts_executed=False,r19_original_archive_sha_verified=False,
            scope='Original ZIP transport hashes plus selected text CRC/SHA and dispatch-byte equality; r19 report hashes only'))
    if private:
        require(private.is_relative_to(ROOT/'build') and not private.exists(),'Fresh private build/ output required')
        private.mkdir(parents=True);write(private/'selected-members.private.json',private_rows);write(private/'registry.json',out)
    require(baseline(load(HERE/'working_combination.json'))==before,'Baseline changed during registration')
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archives',type=Path,default=Path(os.environ.get('USERPROFILE','~'))/'Desktop')
    p.add_argument('--dispatch',type=Path,default=ROOT/'build/dispatch_handover_20261023')
    p.add_argument('--output',type=Path)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--check',type=Path,help='Compare against an existing registry without modifying it')
    a=p.parse_args();record=collect(a.archives.resolve(),a.dispatch.resolve(),a.output.resolve() if a.output else None)
    if a.check:require(record==load(a.check),'Registered report or policy differs from verified inputs')
    if a.apply:write(REGISTRY,record);require(apply_metadata(),'Metadata application failed')
    print('R19_R23_ARCHIVAL_IDENTITIES_TRUTH_MATRIX_AND_UNCHANGED_MODEL_BASELINE_PASS_NOT_BOARD')

if __name__=='__main__':main()
