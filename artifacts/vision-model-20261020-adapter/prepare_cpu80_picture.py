"""Stage a CPU80/r14 PN02 boot candidate without accessing removable media."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;R=HERE.parents[1];B=R/'build/picture-merge-20261023'
sys.path.insert(0,str(R/'scripts'))
from prepare_picture_candidate import tokens
from sd_namespace import identity,stage,CPU80_CONV
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--rootfs',type=Path,required=True);p.add_argument('--kernel-dir',type=Path,required=True);a=p.parse_args()
 ram=B/'cpu80-ram';assert not ram.exists();ram.mkdir()
 hw=load(R/'CPU80_CONV_CANDIDATE.json');assert hw['bitstream_sha256']==CPU80_CONV
 kit=R/'artifacts/cpu80_audio_service_20261022/sd-kit';km=load(kit/'manifest.json')
 assert km['candidate_bitstream_sha256']==CPU80_CONV and km['sbi_ratio']==[99,160]
 for item in km['payloads']:
  if item['name'] in ('fw_jump.bin','pikafish.pff','pikafish.atk'):
   actual=identity(kit/'sd-root'/item['name']);assert all(actual[k]==item[k] for k in ('bytes','sha256','crc32'))
 assert a.rootfs.stat().st_size<=0x1000000
 blob=bytearray((a.kernel_dir/'soc.dtb').read_bytes());header,props,_=tokens(blob)
 assert props['/cpus/cpu@0/clock-frequency'][0]==struct.pack('>I',80000000)
 assert props['/cpus/timebase-frequency'][0]==struct.pack('>I',80000000)
 assert props['/reserved-memory/mac-accel@1b000000/reg'][0]==struct.pack('>II',0x1b000000,0x100000)
 assert props['/reserved-memory/accel-guard@1b100000/reg'][0]==struct.pack('>II',0x1b100000,0x100000)
 assert props['/reserved-memory/snapshot@1b600000/reg'][0]==struct.pack('>II',0x1b600000,0x200000)
 size=a.rootfs.stat().st_size;position=props['/chosen/linux,initrd-end'][1];struct.pack_into('>I',blob,header[2]+position,0x03000000+size)
 _,after,_=tokens(blob);expected={k:v[0] for k,v in props.items()};expected['/chosen/linux,initrd-end']=struct.pack('>I',0x03000000+size)
 assert {k:v[0] for k,v in after.items()}==expected
 dtb=ram/'br.dtb';dtb.write_bytes(blob)
 files={'brfw.bin':kit/'sd-root/fw_jump.bin','Image':a.kernel_dir/'Image','brfs2.bin':a.rootfs,'br.dtb':dtb,'pikafish.pff':kit/'sd-root/pikafish.pff','pikafish.atk':kit/'sd-root/pikafish.atk'}
 contract=dict(schema_version=1,scope='offline CPU80-conv/r14 Picture candidate; no BoardRelease',hardware_profile='cpu80-conv-34338722',cpu_hz=80000000,sys_hz=49500000,fixed_sbit_sha256=CPU80_CONV,files={k:identity(v) for k,v in files.items()},production_ready=False,full_integer_pipeline=False,board_validated=False,cold_boot_board_validated=False,sd_written=False,flash_written=False,latency_waiver_granted=True,demo_latency_cap_s=10,engineering_targets_s=[5,3],integer_acceptance='待新局归因; r14 reported68/84 below73/84',model_registration='candidate_r14_e_v3dqat',sbi_ratio=[99,160])
 (ram/'sd_contract.json').write_text(json.dumps(contract,indent=2,ensure_ascii=False)+'\n')
 result=stage(ram,B/'PN02','PN02');assert not result['sd_written']
 print('CPU80_PICTURE_PN02_STAGED rootfs_bytes=',size,'no_media_written=true')
if __name__=='__main__':main()
