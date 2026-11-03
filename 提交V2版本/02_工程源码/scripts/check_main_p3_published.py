"""Authenticate the one published P3 image for a functional CRAM assignment.

This is independent of Project release replay. Original native reports are
checked, but absent/foreign local PDS databases never become a replay PASS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from verify_integrated_opt60_main import verify

REF='e7288be9e49f348b37832a65415b6989c444384c'
SOFTWARE_REF='1ab3bcbaf1c583dd0f35c155d4b71a0cc5cab8ec'
IMAGE='6565ad378524f3e2a34f6cdba6fcc46b2f928eb3677c0fe80971e05e8ec2ebdd'
RUN='06a580c5937e413fbf7e3d843e465594'
EXTRA_SCRIPTS={
 'scripts/build_picture_loader.ps1','scripts/build_picture_roi_kernel.ps1',
 'scripts/build_picture_roi_linux.ps1','scripts/build_picture_sd_console_boot.ps1',
 'scripts/build_picture_sd_installer.ps1','scripts/build_picture_whole_fast.py',
 'scripts/build_xinyi_coremark_compare.py','scripts/build_xinyi_cpu60_loader.ps1',
 'scripts/build_xinyi_cpu60_loader.py','scripts/build_xinyi_kernel.py',
 'scripts/build_xinyi_nnue.sh','scripts/build_xinyi_sd_install.ps1'}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def blob(root,ref,name):
    return subprocess.check_output(['git','-C',str(root),'show',ref+':'+name],timeout=20)
def pinned(root,name,ref=REF):
    expected=hashlib.sha256(blob(root,ref,name)).hexdigest()
    require(digest(root/name)==expected,'Published file changed: '+name)
    return expected

def check(root,image):
    require(not image.is_symlink() and not image.is_junction(),'Linked image is not accepted')
    root=root.resolve();image=image.resolve()
    require(image==root/'artifacts/soc_top.sbit','Only in-repository published soc_top.sbit is accepted')
    require(not image.is_symlink() and digest(image)==IMAGE,'Wrong P3 bitstream')
    for name in ['scripts/verify_integrated_opt60_main.py','scripts/build_snapshot.ps1',
                 'scripts/timing_scope.ps1','scripts/timing_scope_pixel_grid.ps1',
                 'scripts/clock_policy.ps1','scripts/audit_project.ps1']:
        pinned(root,name)
    pinned(root,'artifacts/INTEGRATED_OPT60_MAIN.json')
    snapshot_sha=pinned(root,'artifacts/build_snapshot.json')
    evidence_sha=pinned(root,'artifacts/build_evidence.json')
    snap=json.loads((root/'artifacts/build_snapshot.json').read_text(encoding='utf-8-sig'))
    require(snap['run_id']==RUN and len(snap['inputs'])==495,'Foreign P3 snapshot')
    for name,expected in snap['inputs'].items():
        require(digest(root/name)==expected,'Frozen input changed: '+name)
    for name in EXTRA_SCRIPTS:pinned(root,name,SOFTWARE_REF)
    publication=verify(root)
    require(publication['bitstream_sha256']==IMAGE,'Foreign publication')
    native=root/'docs/validation/integrated-opt60-board-20261025/native/physical-launch.json'
    original=json.loads(native.read_text(encoding='utf-8-sig'))
    require(original['status']=='ROUTED_FULL_STA_PASS_NOT_BOARD' and original['run_id']==RUN,'Foreign original native receipt')
    return dict(status='EXACT_MAIN_P3_PUBLISHED_IDENTITY_PASS_NOT_FORMAL_RELEASE',
        source_ref=REF,run_id=RUN,bitstream_sha256=IMAGE,
        firmware_binary_sha256=digest(root/'artifacts/bootloader.bin'),
        cpu_rtl_sha256=digest(root/'rtl/cpu/CoreTop.sv'),
        cpu_source_manifest_sha256=digest(root/'rtl/cpu/source.json'),
        pds_snapshot_sha256=snapshot_sha,pds_build_evidence_sha256=evidence_sha,
        frozen_inputs=495,extra_software_inputs=sorted(EXTRA_SCRIPTS),
        inherited_function_sources={name:digest(root/name) for name in
            ['rtl/mac_accel/mac_conv_weight_dma.v','sim/tb_conv_weight_fold.sv']},
        upstream_sta_pass=True,native_database_replay_complete=False,formal_release=False,
        scope='Exact published main P3 identity and portable original evidence; independent raw STA/clock review required by wrapper. Project/CPU80/CPU60FunctionalTrial gates unchanged.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--image',type=Path,required=True)
    a=p.parse_args();print(json.dumps(check(a.root,a.image),separators=(',',':')))
