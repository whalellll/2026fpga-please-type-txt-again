"""Verify an offline CPU80 convolution candidate without accessing a device."""
import argparse,hashlib,json,struct
from pathlib import Path
from build_cpu80_conv_sd import cpio_entries,fdt_properties
from verify_cpu80_delivery import timing

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def need(value,message):
 if not value:raise ValueError(message)
def validate(root):
 root=Path(root).resolve();m=read(root/'CPU80_CONV_CANDIDATE.json')
 need(m['status']=='CPU80_CONV_OFFLINE_CANDIDATE_BOARD_PENDING','Wrong candidate status')
 need(m['cpu_hz']==80000000 and m['sys_hz']==49500000 and m['sbi_ratio']==[99,160],'Wrong clock/boot contract')
 need(m['board_tested'] is False and m['remote_pushed'] is False,'Offline candidate misrepresents hardware acceptance')
 source=read(root/'rtl/cpu/source.json')
 need(source['source_reference_commit']==m['cpu_implementation_commit']=='fefd93052c4974c5a45fcebb7a34cc3d44f9a8d9','CPU implementation changed')
 need(sha(root/'rtl/cpu/CoreTop.sv')==source['sha256']=='95a5a197b07719948c36941b3a64308183704297d3cb4702347dc985ad2708f0','CPU source/RTL differs')
 snapshot=read(root/'artifacts/build_snapshot.json');evidence=read(root/'artifacts/build_evidence.json')
 need(snapshot['run_id']==evidence['run_id']==m['run_id'],'Native run identity differs')
 need(sha(root/'artifacts/build_snapshot.json')==evidence['input_snapshot_sha256'],'Native snapshot hash differs')
 need(snapshot['inputs']==m['frozen_inputs_sha256'],'Native input sets differ')
 for n,h in snapshot['inputs'].items():need(sha(root/n)==h,'Frozen input differs: '+n)
 for n,h in evidence['outputs'].items():need(sha(root/n)==h,'Native output differs: '+n)
 need(sha(root/'artifacts/soc_top.sbit')==m['bitstream_sha256'],'Wrong candidate bitstream')
 for n,h in m['gate_receipts_sha256'].items():need(sha(root/n)==h,'Candidate gate receipt differs: '+n)
 need(evidence['timing']=='All Constraints Met' and evidence['max_skew_verified'] and evidence['timing_scope_verified'],'Incomplete final native gates')
 timing((root/'artifacts/final_timing_xml.xml').read_bytes())
 need('Design Summary : All Constraints Met.' in (root/'artifacts/final_timing_report.txt').read_text(),'Native final RTR failed')
 need(sha(root/'pds/bootrom.hex')==sha(root/'artifacts/bootrom.hex'),'Missing/mixed simulation ROM')
 kit=root/m['sd_kit'];sd=kit/'sd-root';manifest=read(kit/'manifest.json')
 need(manifest['candidate_run_id']==m['run_id'] and manifest['candidate_bitstream_sha256']==m['bitstream_sha256'],'SD kit not bound to selected convolution bitstream')
 expected={'Image.mmode','mmode.dtb','fw_jump.bin','Image','rootfs.cpio','soc.dtb','pikafish.pff','pikafish.atk'}
 need(set(manifest['sd_root_files'])==expected,'Incomplete SD startup contract')
 for n,item in manifest['sd_root_files'].items():need(sha(sd/n)==item['sha256'] and (sd/n).stat().st_size==item['bytes'],'SD runtime differs: '+n)
 need((sd/'mmode.dtb').read_bytes()==(sd/'soc.dtb').read_bytes(),'ROM/S-mode DTB copies differ')
 dtb=(sd/'soc.dtb').read_bytes();props=fdt_properties(dtb)
 for key in ['/cpus/timebase-frequency','/cpus/cpu@0/clock-frequency']:
  offset,size=props[key];need(size==4 and struct.unpack_from('>I',dtb,offset)[0]==80000000,'CPU/TIME DTB mismatch')
 offset,size=props['/chosen/linux,initrd-end'];need(size==4 and struct.unpack_from('>I',dtb,offset)[0]==0x03000000+(sd/'rootfs.cpio').stat().st_size,'Rootfs length does not match DTB')
 entries=cpio_entries((sd/'rootfs.cpio').read_bytes())
 extras=manifest['extra_records'];need(len(extras)==2,'Convolution self-tests missing')
 for x in extras:
  matched=[row for row in entries if row['name'].removeprefix('./')==x['name']]
  need(len(matched)==1 and matched[0]['sha256']==x['sha256'] and matched[0]['fields'][1]&0o111,'Wrong/missing convolution tool in rootfs')
 need(sha(sd/'pikafish.pff')=='de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260','Official model changed')
 need(sha(sd/'pikafish.atk')=='2235f0b1cca2e447a828bf1c7c7247237580603026d6152954da07efca2d474c','Official attack table changed')
 software=read(kit/'software-build.json');need(len(software['tests'])==18 and software['board_tested'] is False,'SD offline evidence missing/misrepresented')
 for name in software['tests']:need(b'HOST_TEST_PASS' in (kit/'evidence'/name).read_bytes(),'Missing loader test completion: '+name)
 return dict(status='CPU80_CONV_OFFLINE_CONTENT_NATIVE_STA_SD_PASS_BOARD_PENDING',run_id=m['run_id'],frozen_inputs=len(snapshot['inputs']),sd_files=8,sd_offline_tests=18,board_tested=False)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--output',type=Path);a=ap.parse_args()
 result=validate(a.root)
 if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
