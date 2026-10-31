"""Authenticate the one user-authorized CPU60 trial, never a release audit.

Original native gate JSONs remain missing. This separate profile checks the
actual pinned Git objects, materialized inputs and original timing archives.
It is usable only with the exact authorization record and exact trial image.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import subprocess

REF = '127ff9a5b517f0f298ab91492d07ef2a1cf44f5b'
RUN = 'dc951f8b1b7f4cf9962e5f509f165d0f'
IMAGE = '9ba02f105d6168e9445e9a15e2f7a1093d885229deae9e268994acdbe29f5ea1'
TRIAL = 'artifacts/integrated60_linefix_trial_20261024'
EVIDENCE = 'docs/validation/integrated60-linefix-functional-trial-20261024-02'

def sha(data): return hashlib.sha256(data).hexdigest()
def require(value, message):
    if not value: raise ValueError(message)
def git(root, path):
    return subprocess.check_output(['git','show',REF+':'+path],cwd=root,timeout=30)
def load(data): return json.loads(data.decode('utf-8-sig'))
def safe_read(root, relative):
    candidate = root/relative
    require(candidate.resolve().is_relative_to(root.resolve()), 'Input escapes trial root')
    require(not candidate.is_symlink() and candidate.is_file(), 'Missing or linked input: '+relative)
    cursor = candidate
    while cursor != root:
        require(not cursor.is_symlink() and not cursor.is_junction(), 'Linked ancestor: '+relative)
        cursor = cursor.parent
    return candidate.read_bytes()

def verify(root, directory, image):
    auth = load(safe_read(root,'docs/validation/xinyi-one-20261024/functional-board-authorization.json'))
    require(auth['status']=='USER_REQUESTED_FUNCTIONAL_BOARD_TEST_WITH_DISCLOSED_GAPS' and
            auth['user_statement']=='先实板测试，把那些任务都给完成' and
            auth['bitstream_sha256']==IMAGE and auth['run_id']==RUN and
            auth['functional_only'] is True and auth['native_records_may_remain_missing_for_this_trial'] is True and
            auth['formal_sta_gate_unchanged'] is True and auth['formal_delivery'] is False and auth['flash_authorized'] is False,
            'Unknown functional authorization')
    require(directory.resolve().is_relative_to((root/'build').resolve()), 'Trial material must remain under repository build/')
    require(not image.is_symlink() and image.suffix.lower()=='.sbit' and
            image.stat().st_size==3791112 and sha(image.read_bytes())==IMAGE, 'Exact CPU60 trial image required')
    manifest_bytes=git(root,TRIAL+'/manifest.json'); manifest=load(manifest_bytes)
    require(safe_read(directory,'manifest.json')==manifest_bytes, 'Trial manifest differs from pinned Git object')
    require(manifest['run_id']==RUN and manifest['bitstream']['sha256']==IMAGE and
            manifest['sta_pass'] is False and manifest['formal_delivery'] is False and
            manifest['cpu_hz']==60000000 and manifest['sys_hz']==49500000, 'Wrong trial manifest')
    archives={}
    for name,expected in manifest['evidence_sha256'].items():
        original=git(root,EVIDENCE+'/'+name)
        require(sha(original)==expected, 'Original archive hash mismatch: '+name)
        if name.endswith('.gz'):
            raw=gzip.decompress(original)
            require(safe_read(directory,'archive/'+name[:-3])==raw, 'Expanded original report mismatch: '+name)
        archives[name]=expected
    snapshot=load(git(root,EVIDENCE+'/build_snapshot.json'))
    require(snapshot['run_id']==RUN and len(snapshot['inputs'])==491, 'Wrong input snapshot')
    requests=''.join(REF+':'+name+'\n' for name in snapshot['inputs']).encode()
    objects=subprocess.run(['git','cat-file','--batch'],input=requests,capture_output=True,cwd=root,timeout=60,check=True).stdout
    cursor=0
    for name,expected in snapshot['inputs'].items():
        end=objects.index(b'\n',cursor); header=objects[cursor:end].split()
        require(len(header)==3 and header[1]==b'blob', 'Missing original input object: '+name)
        size=int(header[2]); raw=objects[end+1:end+1+size]; cursor=end+size+2
        require(sha(raw)==expected, 'Original Git input differs from physical snapshot: '+name)
        require(sha(safe_read(directory,'source/'+name))==expected, 'Materialized physical input mismatch: '+name)
    require(cursor==len(objects),'Unexpected Git batch tail')
    # Report bytes above must equal the exact pinned original, not a newly
    # generated or edited report. The original PS checker parses the XML and
    # verifies all clock/exception/coverage/skew rows after this identity gate.
    violations=manifest['violations']
    require(len(violations)==2 and
        [(v['corner'],v['kind'],v['clocks'],v['wns_ns'],v['tns_ns'],v['violating_endpoints'],v['endpoints']) for v in violations]==[
            ('slow','hold',['sys_clk','sys_clk'],-.029,-.029,1,65567),
            ('fast','hold',['sys_clk','sys_clk'],-.017,-.017,1,65567)],
        'Unexpected pinned trial timing scope')
    return dict(status='EXACT_CPU60_FUNCTIONAL_TRIAL_IDENTITY_PASS_NOT_RELEASE',source_ref=REF,run_id=RUN,
        bitstream_sha256=IMAGE,input_count=491,archive_sha256=archives,
        authorization_sha256=sha(safe_read(root,'docs/validation/xinyi-one-20261024/functional-board-authorization.json')),
        firmware_binary_sha256=snapshot['inputs']['artifacts/bootloader.bin'],
        cpu_rtl_sha256=snapshot['inputs']['rtl/cpu/CoreTop.sv'],
        cpu_source_manifest_sha256=snapshot['inputs']['rtl/cpu/source.json'],
        pds_snapshot_sha256=manifest['evidence_sha256']['build_snapshot.json'],
        missing_original_native_gate_records=4,native_preflight_complete=False,formal_sta_pass=False,
        formal_delivery=False,violations=violations)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--trial-directory',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(args.root.resolve(),args.trial_directory.resolve(),args.image.resolve()),ensure_ascii=False))
