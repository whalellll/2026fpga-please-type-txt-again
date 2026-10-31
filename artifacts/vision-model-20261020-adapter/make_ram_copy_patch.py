"""Create a copy/literal RAM patch, independent of the preserved BSDIFF tool."""
import argparse
import gzip
import hashlib
import json
import struct
import zlib
from pathlib import Path


def make(old,new):
    index={}
    for i in range(0,len(old)-15,4):
        key=old[i:i+16]
        if key not in index:index[key]=i
    patch=bytearray(b'XQPATCH1'+struct.pack('<4I',len(old),zlib.crc32(old),len(new),zlib.crc32(new)))
    literal=bytearray();at=0;check=bytearray();copies=0
    def flush():
        if literal:
            patch.extend(b'\1'+struct.pack('<I',len(literal))+literal)
            check.extend(literal);literal.clear()
    while at<len(new):
        where=index.get(new[at:at+16]) if at+16<=len(new) else None
        if where is None:literal.append(new[at]);at+=1;continue
        n=16
        while where+n<len(old) and at+n<len(new) and old[where+n]==new[at+n]:n+=1
        flush();patch.extend(b'\0'+struct.pack('<II',n,where));check.extend(old[where:where+n]);copies+=n;at+=n
    flush();assert bytes(check)==new
    return bytes(patch),copies


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('base',type=Path);p.add_argument('target',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();assert not a.out.exists()
    old,new=a.base.read_bytes(),a.target.read_bytes();patch,copies=make(old,new)
    with a.out.open('xb') as f:f.write(gzip.compress(patch,mtime=0))
    receipt=dict(status='PASS',base_sha256=hashlib.sha256(old).hexdigest(),target_sha256=hashlib.sha256(new).hexdigest(),
        patch_sha256=hashlib.sha256(a.out.read_bytes()).hexdigest(),target_bytes=len(new),patch_bytes=a.out.stat().st_size,copied_bytes=copies)
    a.out.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('RAM_PATCH_GENERATED',json.dumps(receipt))


if __name__=='__main__':main()
