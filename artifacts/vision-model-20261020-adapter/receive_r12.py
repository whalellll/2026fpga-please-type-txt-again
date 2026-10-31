"""Verify all r12 bytes; archive authorized formal truth/report without running game 2."""
import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from receive_r08 import unique_object

REPO=Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def receive(archive,out,evidence):
    out=out.resolve();evidence=evidence.resolve()
    if not out.is_relative_to(REPO/'build') or out.exists() or evidence.exists():
        raise ValueError('fresh build delivery and evidence directories required')
    if not evidence.is_relative_to(REPO/'docs/validation'):
        raise ValueError('evidence must be under docs/validation')
    with zipfile.ZipFile(archive) as source:
        members={};seen=set()
        for entry in source.infolist():
            name=entry.filename;path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or stat.S_ISLNK(entry.external_attr>>16) or name.casefold() in seen:
                raise ValueError('unsafe/duplicate ZIP path')
            seen.add(name.casefold())
            if not entry.is_dir():members[name]=entry
        manifests=[n for n in members if n.endswith('/manifest.json')]
        if len(manifests)!=1:raise ValueError('one root manifest required')
        root=manifests[0].removesuffix('manifest.json')
        if not root.startswith('training_side_20261022_r12_') or root.count('/')!=1:
            raise ValueError('unexpected root')
        raw=source.read(root+'manifest.json')
        manifest=json.loads(raw,object_pairs_hook=unique_object)
        if manifest['schema']!='training-side-delivery/20261022-r12':raise ValueError('wrong schema')
        if set(members)!={root+n for n in manifest['files']}|{root+'manifest.json'}:
            raise ValueError('manifest coverage mismatch')
        for name,item in manifest['files'].items():
            data=source.read(root+name)
            if len(data)!=item['bytes'] or digest(data)!=item['sha256']:
                raise ValueError('SHA/size mismatch: '+name)
        out.mkdir(parents=True)
        for name in members:
            target=out/name.removeprefix(root)
            if not target.resolve().is_relative_to(out):raise ValueError('path escape')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read(name))
    evidence.mkdir(parents=True)
    archived={}
    truth=next(out.glob('*/truth_v2'))
    records=sorted(truth.glob('*.json'))
    assert len(records)==86
    for path in records:
        # Structural archival check only: never use these labels as model inputs,
        # tuning signals or failure-analysis data. Embedded photographs forbidden.
        document=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique_object)
        if isinstance(document,dict) and 'imageData' in document:
            assert document['imageData'] is None
        target=evidence/'truth_v2'/path.name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path,target)
        archived[target.relative_to(evidence).as_posix()]=dict(source=path.relative_to(out).as_posix(),sha256=digest(path.read_bytes()))
    for path in [out/'official_acceptance_game2.json',out/'game1_pack_numbers.json',*out.glob('*.md')]:
        target=evidence/path.name;shutil.copyfile(path,target)
        archived[target.name]=dict(source=path.relative_to(out).as_posix(),sha256=digest(path.read_bytes()))
    shutil.copyfile(out/'manifest.json',evidence/'delivery-manifest.json')
    official=json.loads((out/'official_acceptance_game2.json').read_text(encoding='utf-8'))
    # Only aggregate formal fields are consumed; per-frame rows remain opaque.
    summary={}
    for name,item in official.items():
        if name.startswith('_'):continue
        summary[name]={k:item[k] for k in ('frames','fen_exact','fen_rate','strict_usable','strict_rate','status_counts')}
        summary[name]['reported_quality_gate_pass']=item['fen_exact']/item['frames']>=.85
    assert summary['E_v1_640_v3c']['fen_exact']==summary['E_v1_640_v3c']['strict_usable']==73
    assert summary['E_v1_640_v3c']['status_counts']==dict(candidate_board=83,cell_conflict=1)
    intake=dict(status='PASS',schema_version=1,manifest_payloads_verified=len(manifest['files']),
        full_manifest_coverage=True,archive_bytes=archive.stat().st_size,
        archive_sha256=digest(archive.read_bytes()),manifest_sha256=digest(raw),
        archived_payloads=archived,game2_images_read=0,game2_inference_runs=0,
        game2_training_or_failure_analysis=False,formal_truth_and_report_archival_authorized=True,
        training_scripts_executed=False,hardware_used=False,production_ready=False)
    (evidence/'intake.json').write_text(json.dumps(intake,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    policy=dict(status='USER_SELECTED_E_FP32_WORKING_BASELINE',selected='E_v1_640_v3c',
        formal_source='official_acceptance_game2.json',truth_version='truth_v2',
        aggregate_metrics=summary,candidate_board_does_not_imply_truth_correct=True,
        clarification='A and E both pass the reported 85% FEN gate; E is selected with fewer conflicts, not the sole numerically passing combination',
        supersedes=official['_meta']['supersedes'],second_game_policy='archival and aggregate official numbers only; no image access, inference, training, tuning or failure analysis',
        parallel_512_training='training-side on games 1/3 only; no engineering training run',
        latency_waiver_granted=False,latency_cap_s=5,latency_goal_s=3,
        r11_provisional_results_superseded=True,quantized_v3c_available=False,production_ready=False)
    (evidence/'policy-and-official-summary.json').write_text(json.dumps(policy,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('R12_INTAKE_AND_FORMAL_ARCHIVE_PASS',len(manifest['files']),'payloads',len(archived),'archived')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args();receive(args.archive,args.out,args.evidence)
