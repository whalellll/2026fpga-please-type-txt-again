"""Curate source-bound CPU70 evidence and SD8 for prepublication verification.

No ZIP, remote push, board or removable-media access. Original receipts remain
unchanged; only selected software/evidence paths in the candidate are created.
"""
from pathlib import Path
import argparse,hashlib,json,shutil
from workspace_paths import workspace_path

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);a=ap.parse_args()
    work,root=workspace_path(a.work),workspace_path(a.source)
    base=root/'docs/validation/main70-release-20261027';payload=root/'artifacts/main70_20261027'
    assert not base.exists() and not payload.exists();base.mkdir(parents=True);payload.mkdir()
    copied={}
    def cp(src,dst):
        src=Path(src);dst=Path(dst);assert src.is_file() and not src.is_symlink() and not dst.exists()
        assert src.resolve().is_relative_to(Path('G:/fpga').resolve())
        dst.parent.mkdir(parents=True,exist_ok=True);h=sha(src);shutil.copyfile(src,dst)
        assert sha(dst)==h;copied[dst.relative_to(root).as_posix()]=h
        return dict(path=dst.relative_to(root).as_posix(),sha256=h)
    def tree(src,dst,keep=lambda p:True):
        for p in sorted(src.rglob('*')):
            if p.is_file() and keep(p):cp(p,dst/p.relative_to(src))
    native=work.parent/'main70-20261027-02/result.json'
    manifest=dict(schema=1,kind='main70-prepackage-release',run_id='6d01c26066a1467690d01ca479739158',
        bitstream_sha256='24226a3a2cf41e96554e4f4ea677f133964cbf942993cb1f751c60c5928a8a02',
        hardware_source_commit='c50bb15873dda846cce2863d99c92ff9aa665167',
        gui_source_commit='8f4de1c7d26d5f8ec9c2ccf6bc8fca3da7bf1e34',
        coremark_policy=dict(per_mhz_absolute_decrease_limit=.05,total_score_gate=False,all_valid_samples=True))
    manifest['native_result']=cp(native,base/'native-result.json')
    manifest['coremark_batches']=[]
    for row in read(work/'coremark-abab-02/result.json')['batches']:
        label=row['label'];target=base/'coremark'/label;prog=Path(row['program_receipt']);cm=Path(row['coremark_result'])
        role,batch=label.split('-');item=dict(role=role,batch=batch)
        for key,src,name in [('program',prog,'program.json'),('program_log',prog.with_suffix('.log'),'program.log'),
                ('preflight_log',prog.with_suffix('.preflight.log'),'program.preflight.log'),
                ('result',cm,'result.json'),('uart',cm.parent/'uart.log','uart.log')]:item[key]=cp(src,target/name)
        manifest['coremark_batches'].append(item)
    cp(work/'coremark-abab-02/result.json',base/'coremark/combined-result.json')
    cp(work/'coremark-abab/result.json',base/'preserved-failures/coremark-first-owner.json')
    cp(work/'coremark-abab/control-b/program.json',base/'preserved-failures/control-b-first-scan.json')
    tree(work/'model-comparison-01',base/'model-comparison')
    p=base/'model-comparison/result.json';manifest['model_performance']=dict(path=p.relative_to(root).as_posix(),sha256=sha(p))
    groups={name:(work/'board-tests-02'/name) for name in ['clock','nnue','search','vision','voice','mixed','microphone']}
    groups.update({'linux-coremark':work/'linux-coremark-02','gui':work/'gui-delta-02/transfer'})
    manifest['board_groups']={}
    for name,src in groups.items():
        manifest['board_groups'][name]={key:cp(src.with_suffix(ext),base/'board'/(name+ext))
            for key,ext in [('result','.result.json'),('uart','.uart')]}
    for name in ['user-physical-01.json','engine-service-01.result.json','engine-service-01.uart']:
        src=work/name
        if src.is_file():cp(src,base/'board'/name)
    manifest['initial_sd_boot']=dict(result=cp(work/'boot-01/result.json',base/'board/initial-sd-boot.json'),
        uart=cp(work/'boot-01/uart.log',base/'board/initial-sd-boot.uart'),
        sd_write=cp(work/'sd-write-01/result.json',base/'board/initial-sd-write.json'),
        kit_manifest=cp(work/'kit-02/manifest.json',base/'board/initial-kit-manifest.json'))
    manifest['physical_feedback']=cp(work/'user-physical-02.json',base/'board/physical-feedback.json')
    manifest['regression']=cp(work/'regression-01/result.json',base/'regression/result.json')
    manifest['regression_log']=cp(work/'regression-01/regression.log',base/'regression/regression.log')
    manifest['regression_inputs']=cp(work/'regression-01/inputs.json',base/'regression/inputs.json')
    for kind,src in [('runtime',root/'build/voice-restart-runtime-02'),('ui',root/'build/voice-restart-ui-02')]:
        if kind=='runtime':
            cp(src/'result.json',base/'gui-tests/runtime-result.json');cp(src/'run.log',base/'gui-tests/runtime.log')
        else:cp(root/'build/voice-restart-ui-02.host.log',base/'gui-tests/ui.log')
    for name in ['assembly.json','manifest.json','software-build.json']:cp(work/'kit-04'/name,payload/'sd-kit'/name)
    for name in ['sd-root','support','evidence']:
        tree(work/'kit-04'/name,payload/'sd-kit'/name,lambda p:p.suffix not in ['.img','.o','.vvp'])
    p=payload/'sd-kit/manifest.json';manifest['sd_kit_manifest']=dict(path=p.relative_to(root).as_posix(),sha256=sha(p))
    manifest['cpu_source_archive']=cp(work/'cpu-source-05c7ef96.tar.gz',payload/'cpu-source-05c7ef96.tar.gz')
    tree(work/'kernel-original-inputs',payload/'kernel-original-inputs')
    kernel=work.parent/'board-functional-20261026-01/kernel'
    for name in ['build.json','base.config','kernel.config','embedded.config']:
        if (kernel/name).is_file():cp(kernel/name,payload/'kernel'/name)
    for name in ['xinyi-one-stripped','cpu-hz.txt','source-before.sha256','source-after.sha256','compiler.txt']:
        cp(root/'build/gui70-restart-01'/name,payload/'gui'/name)
    source_map={}
    for line in (payload/'gui/source-before.sha256').read_text().splitlines():
        h,n=line.split(None,1);prefix='/mnt/g/fpga/m70d/';assert n.startswith(prefix)
        rel=n[len(prefix):];assert sha(root/rel)==h
        if rel in source_map:assert source_map[rel]==h
        source_map[rel]=h
    gui=dict(software_source_commit=manifest['gui_source_commit'],cpu_hz=70000000,
             source_files_sha256=source_map,elf_sha256=sha(payload/'gui/xinyi-one-stripped'))
    (payload/'gui/source-files.json').write_text(json.dumps(gui,indent=2)+'\n')
    p=payload/'gui/source-files.json';manifest['gui_build']=dict(path=p.relative_to(root).as_posix(),sha256=sha(p))
    p=base/'gui-tests/runtime-result.json';manifest['gui_runtime_test']=dict(path=p.relative_to(root).as_posix(),sha256=sha(p))
    cp(work/'opensbi/result.json',payload/'firmware/build.json')
    # Promote only SD runtime files, never any native FPGA input/output.
    snap=read(root/'artifacts/build_snapshot.json');native_outputs=read(root/'artifacts/build_evidence.json')['outputs']
    prior=work/'linux-boot-before-promotion';prior.mkdir()
    for n,item in read(payload/'sd-kit/manifest.json')['sd_root_files'].items():
        src=payload/'sd-kit/sd-root'/n;dst=root/'linux/boot'/n;rel=dst.relative_to(root).as_posix()
        assert rel not in snap['inputs'] and rel not in native_outputs and sha(src)==item['sha256']
        if dst.exists() and sha(dst)==sha(src):continue
        if dst.exists():
            old=prior/n;shutil.copyfile(dst,old);assert sha(old)==sha(dst)
        shutil.copyfile(src,dst);assert sha(dst)==sha(src)
    (root/'MAIN70_RELEASE.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (base/'curation.json').write_text(json.dumps(dict(status='HASH_VERIFIED_EVIDENCE_CURATED_NOT_FORMAL_PACKAGE',files_sha256=copied),indent=2)+'\n')
    print('MAIN70_SOURCE_SD_AND_EVIDENCE_CURATED_PREPUBLICATION_NO_ZIP')

if __name__=='__main__':main()
