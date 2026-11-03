"""Decode the read-only GUI RGB565/RLE stream into a local PNG."""
import argparse
import hashlib
from pathlib import Path
import struct
import zlib

def decode(raw):
    if len(raw)<20 or raw[:8]!=b'XYFBRL1\0' or (len(raw)-16)%4:
        raise ValueError('Invalid GUI readback header/length')
    width,height=struct.unpack_from('<II',raw,8)
    if (width,height)!=(640,360):raise ValueError('Unexpected GUI readback dimensions')
    pixels=bytearray()
    for pos in range(16,len(raw),4):
        count,pixel=struct.unpack_from('<HH',raw,pos)
        if not count or len(pixels)//2+count>width*height:raise ValueError('Invalid RLE run')
        pixels.extend(struct.pack('<H',pixel)*count)
    if len(pixels)!=width*height*2:raise ValueError('Incomplete GUI readback')
    return width,height,pixels

def png(width,height,pixels):
    rgb=bytearray()
    for y in range(height):
        rgb.append(0)
        for x in range(width):
            value=struct.unpack_from('<H',pixels,2*(y*width+x))[0]
            r,g,b=(value>>11)&31,(value>>5)&63,value&31
            rgb.extend(((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2)))
    def chunk(name,data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rgb,9))+chunk(b'IEND',b'')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--expected-sha256');p.add_argument('--fixture',action='store_true')
    a=p.parse_args();raw=a.input.read_bytes()
    if a.output.exists():raise ValueError('Preserve previous readback')
    if not a.fixture and (not a.expected_sha256 or hashlib.sha256(raw).hexdigest()!=a.expected_sha256):
        raise ValueError('Actual readback requires matching board-reported file SHA256')
    width,height,pixels=decode(raw)
    if a.fixture:
        colors=(0xf800,0x07e0,0x001f,0xffff,0,0xffe0,0x07ff,0xf81f)
        for y in (0,179,359):
            for x in range(width):
                if struct.unpack_from('<H',pixels,2*(y*width+x))[0]!=colors[x//80]:raise ValueError('Fixture pixel mismatch')
    a.output.write_bytes(png(width,height,pixels))
    print('GUI_READBACK_DECODE_PASS',width,height,'fixture_not_board='+str(a.fixture))
