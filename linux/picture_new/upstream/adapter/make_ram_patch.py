"""BSDIFF-derived, CRC-bound RAM update; independent reconstruction before use."""
import argparse,bz2,gzip,hashlib,json,struct,subprocess,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--target',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
old=a.base.read_bytes();new=a.target.read_bytes();bs=a.out/'source.bsdiff'
subprocess.run(['bsdiff',str(a.base),str(a.target),str(bs)],check=True)
raw=bs.read_bytes()
def off(b):
    v=int.from_bytes(b,'little');return -(v&((1<<63)-1)) if v>>63 else v
cn,dn,nn=map(off,[raw[8:16],raw[16:24],raw[24:32]]);assert nn==len(new)
controls=bz2.decompress(raw[32:32+cn]);ops=[];pos=oldpos=0
for k in range(0,len(controls),24):
    x,y,z=[off(controls[k+j:k+j+8]) for j in (0,8,16)]
    assert x>=0 and y>=0 and pos+x+y<=len(new)
    valid0=max(0,min(x,-oldpos));valid1=max(valid0,min(x,len(old)-oldpos))
    for left,right,add in [(0,valid0,False),(valid0,valid1,True),(valid1,x,False)]:
        n=right-left
        if not n:continue
        payload=new[pos+left:pos+right]
        if add:
            payload=bytes((v-old[oldpos+left+t])&255 for t,v in enumerate(payload))
            ops.append(b'\2'+struct.pack('<II',n,oldpos+left)+payload)
        else:ops.append(b'\1'+struct.pack('<I',n)+payload)
    pos+=x;oldpos+=x
    if y:ops.append(b'\1'+struct.pack('<I',y)+new[pos:pos+y])
    pos+=y;oldpos+=z
assert pos==len(new)
patch=b'XQDP1\0\0\0'+struct.pack('<IIIII',len(old),zlib.crc32(old),len(new),zlib.crc32(new),len(ops))+b''.join(ops)
reconstructed=bytearray();cursor=28
for _ in ops:
    op=patch[cursor];n=struct.unpack_from('<I',patch,cursor+1)[0];cursor+=5
    if op in (0,2):offset=struct.unpack_from('<I',patch,cursor)[0];cursor+=4
    if op==0:reconstructed+=old[offset:offset+n]
    elif op==1:reconstructed+=patch[cursor:cursor+n];cursor+=n
    elif op==2:reconstructed+=bytes((old[offset+j]+v)&255 for j,v in enumerate(patch[cursor:cursor+n]));cursor+=n
    else:raise ValueError(op)
assert reconstructed==new and cursor==len(patch)
packed=gzip.compress(patch,mtime=0);(a.out/'gui.delta.gz').write_bytes(packed)
sha=lambda x:hashlib.sha256(x).hexdigest()
record=dict(base=str(a.base),target=str(a.target),base_sha256=sha(old),target_sha256=sha(new),patch_sha256=sha(patch),gzip_sha256=sha(packed),gzip_bytes=len(packed),roundtrip=True)
(a.out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print('RAM_PATCH_PASS',json.dumps(record),flush=True)
