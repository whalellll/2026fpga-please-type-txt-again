"""Serve only the hash-checked1080p runtime through the bundled read-only TFTP server."""
from pathlib import Path
import argparse,hashlib,json,sys
import tftp_server

def validate(kit):
    kit=Path(kit).resolve();m=json.loads((kit/'manifest.json').read_text(encoding='utf-8'))
    assert m['status']=='GUI1080_CPU80_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING'
    assert m['display']==dict(width=1920,height=1080,pixel_hz=148500000,theme='light')
    assert m['gui_sha256']=='583c94b4b60e508933b18d0d267e9054a13d5ac7e84f7559e1f3b7ad5998e448'
    assert len(m['tests'])==18 and len(m['sd_root_files'])==8
    for name,item in m['sd_root_files'].items():
        assert '/' not in name and '\\' not in name and name not in ['.','..']
        p=kit/'sd-root'/name
        assert p.is_file() and not p.is_symlink() and p.stat().st_size==item['bytes']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],name
    for name in m['tests']:
        assert '/' not in name and '\\' not in name and 'HOST_TEST_PASS' in (kit/'evidence'/name).read_text(errors='replace')
    return dict(status='GUI1080_TFTP_RUNTIME_HASHES_PASS_NOT_BOARD',root=str(kit/'sd-root'),
                files=8,board_tested=False,physical_media_written=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--kit',type=Path,required=True)
    ap.add_argument('--bind');ap.add_argument('--port',type=int,default=69);ap.add_argument('--check-only',action='store_true');a=ap.parse_args()
    proof=validate(a.kit);print(json.dumps(proof),flush=True)
    if not a.check_only:
        assert a.bind,'An explicit directly connected host address is required'
        tftp_server.ALLOWED_FILES={'fw_jump.bin','Image','rootfs.cpio','soc.dtb','pikafish.pff','pikafish.atk'}
        sys.argv=['tftp_server.py','--root',proof['root'],'--bind',a.bind,'--port',str(a.port)]
        tftp_server.main()
