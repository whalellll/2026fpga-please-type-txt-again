"""Prepare a six-file create-only PN15 installer. No real media access."""
from pathlib import Path
import argparse,json,zlib
from picture_workspace import ROOT,workspace_path
from prepare_xinyi_cpu60_kit import identity,require


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--original-installer',type=Path,required=True)
    a=ap.parse_args();out=workspace_path(a.output);require(not out.exists(),'Fresh output required')
    c=a.candidate.resolve();manifest=json.loads((c/'manifest.json').read_text())
    require(manifest['prefix']=='PN15','Exact PN15 candidate required')
    out.mkdir(parents=True);support=out/'support';support.mkdir();payload=out/'payloads';payload.mkdir()
    inputs={}
    def read(p):
        p=p.resolve();d=p.read_bytes();inputs[str(p)]=identity(d);return d
    read(Path(__file__));read(c/'manifest.json')
    read(ROOT/'scripts/build_xinyi_sd_install.ps1');read(ROOT/'scripts/check_xinyi_sd_install.py')
    for p in sorted((a.original_installer/'support').iterdir()):
        if p.is_file() and p.name!='install_payloads.h':(support/p.name).write_bytes(read(p))
    require(b'0x00010001' in (support/'target.h').read_bytes(),'Exact version guard required')
    with (support/'target.h').open('ab') as f:f.write(b'\n#define XINYI_TEST_KEEP_PN08 1\n#define XINYI_TEST_KEEP_PN09 1\n')
    records=[]
    names=['PN15.DTB','PN15UPD.GZ','PN15.JSN','PN15BOOT.BIN','PN15.SHA','PN15SRC.JSN']
    for i,name in enumerate(names):
        data=read(c/'sd-update'/name);(payload/name).write_bytes(data)
        records.append(dict(name=name,address=0x06000000+i*0x00800000,aliases=[],**identity(data)))
    require(records[1]['bytes']<0x00800000,'Receive apertures must not overlap')
    header='#include <stdint.h>\n'
    for i,row in enumerate(records):
        data=(payload/row['name']).read_bytes()
        header+=f'static const uint32_t slice_crc_{i}[]={{'+','.join(f'0x{zlib.crc32(data[n:n+65536]):08x}u' for n in range(0,len(data),65536))+'};\n'
    header+=('typedef struct {const char *name,*short_name;uint32_t address,bytes,crc;'
             'const char *aliases[4];int ready,exists;const uint32_t *slice_crc;uint32_t offset;} item_t;\nstatic item_t items[]={\n')
    for i,row in enumerate(records):
        stem,ext=row['name'].split('.');short=stem.ljust(8)+ext.ljust(3)
        require(len(short)==11,'Strict FAT 8.3 required')
        header+=f'{{"{row["name"]}","{short}",0x{row["address"]:08x}u,{row["bytes"]}u,0x{row["crc32"]}u,{{0}},0,0,slice_crc_{i},0}},\n'
    header+='};\n#define INSTALL_COUNT 6u\n#define INSTALL_BOOT_INDEX 3u\n#define INSTALL_SECTORS 62333952u\n#define INSTALL_PARTITION 32u\n'
    (support/'install_payloads.h').write_text(header,newline='\n')
    for p in sorted(support.iterdir()):read(p)
    require(all(identity(Path(n).read_bytes())==v for n,v in inputs.items()),'Source drift')
    contract=dict(status='PN15_CREATE_ONLY_INSTALLER_PREPARED_NOT_INSTALLED',prefix='PN15',
        bitstream_sha256=manifest['target_bitstream_sha256'],media_sectors=62333952,
        partition_lba=32,cluster_bytes=32768,files=records,source_inputs=inputs,
        existing_files_preserved=True,selector_modified=False,sd_written=False,flash_written=False)
    (out/'install_contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    print('PN15_SIX_CREATE_ONLY_FILES_PREPARED')


if __name__=='__main__':main()
