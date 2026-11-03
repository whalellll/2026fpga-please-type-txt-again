"""Bind checked SD files to the exact dedicated trial bitstream; no board or delivery claim."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from build_cpu80_conv_sd import cpio_entries
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--sd-kit',type=Path,required=True);ap.add_argument('--native',type=Path,required=True)
 a=ap.parse_args();kit=a.sd_kit.resolve();native=a.native.resolve()
 manifest=read(kit/'manifest.json');snapshot=read(native/'pds/build_snapshot.json')
 assert manifest['status']=='VOICE_NNUE_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING'
 assert len(manifest.get('pipeline_integration_sha256') or '')==64,'Missing complete official-source pipeline integration proof'
 assert len(manifest['tests'])==18 and len(set(manifest['tests']))==18
 for name in manifest['tests']:assert 'HOST_TEST_PASS ' in (kit/'evidence'/name).read_text(errors='replace'),name
 names={'Image','Image.mmode','fw_jump.bin','rootfs.cpio','soc.dtb','mmode.dtb','pikafish.pff','pikafish.atk'}
 assert set(manifest['sd_root_files'])==names
 assert {p.name for p in (kit/'sd-root').iterdir()}==names|{'SHA256SUMS.txt'}
 for n,item in manifest['sd_root_files'].items():
  p=kit/'sd-root'/n;assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],n
 assert manifest['cpu_hz']==75000000 and manifest['sys_hz']==49500000
 assert manifest['clock_sha256']==sha(ROOT/'config/clocks.json')==snapshot['inputs']['config/clocks.json']
 checked={}
 for name,h in snapshot['inputs'].items():
  if name.startswith(('rtl/','ip/','config/')) or name.endswith(('.fdc','.rcf','.pcf')):
   assert sha(ROOT/name)==h and sha(native/name)==h,name
   checked[name]=h
 assert len(checked)>50
 rows={r['name'].removeprefix('./'):r for r in cpio_entries((kit/'sd-root/rootfs.cpio').read_bytes())}
 for n,h in manifest['runtime_sha256'].items():assert rows[n]['sha256']==h,n
 assert rows['opt/xqvoice/sd77-candidate.xqt']['sha256']=='10186411d091dc85efefc921f29300e49a1e5de7b308f6e8d49602ea349ee41a'
 receipts=list((native/'pds/input-snapshots').glob('*/physical-result.json'));assert len(receipts)==1
 physical=read(receipts[0]);assert physical['run_id']==snapshot['run_id']
 assert physical['status']=='ROUTED_STA_FAILED_NOT_BOARD'
 source=native/'pds/generate_bitstream/soc_top.sbit'
 assert sha(source)==physical['reports']['generate_bitstream/soc_top.sbit']
 target=kit/'soc_top.sbit';assert not target.exists();shutil.copyfile(source,target);assert sha(target)==sha(source)
 result=dict(status='PIKAFISH_DEDICATED_SD_OFFLINE_READY_BOARD_PENDING_STA_FAILED',
  created_utc=datetime.now(timezone.utc).isoformat(),run_id=snapshot['run_id'],
  manifest_sha256=sha(kit/'manifest.json'),bitstream_sha256=sha(target),
  physical_receipt_sha256=sha(receipts[0]),checked_hardware_inputs_sha256=checked,
  software_boot_files=manifest['sd_root_files'],offline_loader_tests=18,
  final_cpu_setup_wns_ns=-0.181,board_tested=False,physical_sd_written=False,
  delivery=False,remote_pushed=False,flash_written=False,
  scope='User-authorized trial only. Native final CPU STA failed. Software files ready; real SD readback, boot and board correctness/performance remain pending.')
 (kit/'trial-binding.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(result['status']);print(kit/'sd-root')
if __name__=='__main__':main()
