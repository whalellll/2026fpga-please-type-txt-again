"""Bind unchanged offline-tested boot files to the exact full-STA-pass bit."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, shutil
from board_integrated_opt60 import ROOT, preflight
from build_cpu80_conv_sd import cpio_entries

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-kit',type=Path,required=True)
    ap.add_argument('--native-root',type=Path,required=True)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--rootfs-evidence',type=Path,default=ROOT/'build/opt60-rootfs-extract-02/result.json')
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();base=a.base_kit.resolve();out=a.output.resolve();assert not out.exists()
    bit,proof=preflight(a.native_root.resolve(),'8aae985849f8f44e3c898dbcf31234a8df680f95')
    candidate=read(a.candidate/'manifest.json');m=read(base/'manifest.json')
    assert candidate['status']=='INTEGRATED_OPT60_FULL_NATIVE_STA_PASS_NOT_BOARD' and candidate['final_sta_pass']
    assert proof['run_id']==candidate['run_id']=='06a580c5937e413fbf7e3d843e465594'
    assert sha(a.candidate/'soc_top.sbit')==sha(bit)==candidate['bitstream']['sha256']
    assert m['status']=='INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING'
    assert m['cpu_hz']==60000000 and m['sys_hz']==49500000 and m['sbi_ratio']==[33,40]
    assert m['optimization_candidate'] and m['voice_quant_enabled'] and m['original_picture_weights']
    assert m['clock_sha256']==sha(ROOT/'config/clocks.json')
    names={'Image','Image.mmode','fw_jump.bin','mmode.dtb','pikafish.atk','pikafish.pff','rootfs.cpio','soc.dtb'}
    assert set(m['sd_root_files'])==names and len(set(m['tests']))==len(m['tests'])==18
    for name,item in m['sd_root_files'].items():
        p=base/'sd-root'/name;assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],name
    for name in m['tests']:
        assert Path(name).name==name and name not in ('.','..')
        assert 'HOST_TEST_PASS' in (base/'evidence'/name).read_text(errors='replace'),name
    extraction=read(a.rootfs_evidence)
    assert extraction['status']=='OPT60_ACTUAL_RV32_BUSYBOX_EXTRACTION_MODELS_AND_AB_TOOLS_PASS_NOT_BOARD'
    assert extraction['rootfs_sha256']==sha(base/'sd-root/rootfs.cpio')
    assert extraction['manifest_sha256']==sha(base/'manifest.json')
    rows={r['name'].removeprefix('./'):r for r in cpio_entries((base/'sd-root/rootfs.cpio').read_bytes())}
    for name,h in dict(extraction['checked_files'],**m['runtime_sha256']).items():assert rows[name]['sha256']==h,name
    out.mkdir();(out/'sd-root').mkdir();(out/'evidence').mkdir()
    for name in sorted(names|{'SHA256SUMS.txt'}):shutil.copyfile(base/'sd-root'/name,out/'sd-root'/name)
    for name in m['tests']:shutil.copyfile(base/'evidence'/name,out/'evidence'/name)
    for name,item in m['sd_root_files'].items():assert sha(out/'sd-root'/name)==item['sha256']
    m.update(binding_status='OPT60_P3_EXACT_NATIVE_IDENTICAL_SOFTWARE_BOUND_NOT_BOARD',
             bound_utc=datetime.now(timezone.utc).isoformat(),candidate_run_id=proof['run_id'],
             candidate_bitstream_sha256=sha(bit),candidate_manifest_sha256=sha(a.candidate/'manifest.json'),
             candidate_source_commit=proof['source_commit'],base_software_manifest_sha256=sha(base/'manifest.json'),
             software_bytes_unchanged=True,native_preflight=proof,physical_media_written=False,board_tested=False)
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    (out/'binding.json').write_text(json.dumps(dict(status=m['binding_status'],manifest_sha256=sha(out/'manifest.json'),
        bitstream_sha256=sha(bit),base_manifest_sha256=sha(base/'manifest.json'),reused_loader_tests=18,
        rootfs_extraction_sha256=sha(a.rootfs_evidence),
        checked_runtime_model_files=len(extraction['checked_files']),script_sha256=sha(Path(__file__)),
        physical_media_written=False,board_tested=False,formal_delivery=False),indent=2)+'\n')
    print(m['binding_status'])

if __name__=='__main__':main()
