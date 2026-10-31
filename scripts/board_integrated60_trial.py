"""Exact user-authorized original-model timing candidate, volatile CRAM only."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess,threading,time
import serial
from serial.tools.list_ports import comports
R=Path(__file__).resolve().parents[1];N=Path('G:/i60pnr3')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def preflight(kit,write_root,line_fix=False,functional_trial=False,compatible_sd=False):
 assert not functional_trial or line_fix
 assert not compatible_sd or line_fix
 native=Path('G:/i60pnr4') if line_fix else N
 candidate=R/('artifacts/integrated60_linefix_trial_20261024' if functional_trial else 'artifacts/integrated60_linefix_20261024' if line_fix else 'artifacts/integrated60_20261024');m=read(candidate/'manifest.json')
 sd=read(kit/'manifest.json')
 snap=read(native/'pds/build_snapshot.json')
 if functional_trial:
  assert m['status']=='INTEGRATED60_LINEFIX_FUNCTIONAL_TRIAL_STA_FAILED_NOT_RELEASE'
  assert m['functional_trial_authorized'] and not m['sta_pass'] and not m['strict_original_flow_pass']
  assert m['run_id']==snap['run_id']=='dc951f8b1b7f4cf9962e5f509f165d0f'
  evidence=R/m['evidence_root']
  for rel,h in m['evidence_sha256'].items():assert sha(evidence/rel)==h,rel
  proof_path=evidence/'functional-coverage.json';proof=read(proof_path)
  assert proof['status']=='FUNCTIONAL_TRIAL_COVERAGE_CHECKED_STA_FAILED_NOT_RELEASE' and not proof['timing_pass']
  assert proof['run_id']==m['run_id'] and proof['scope']['summary_rows']==116
  for group in ['inputs_sha256','final_gates_sha256']:
   for path,h in proof[group].items():assert sha(Path(path))==h,path
  receipt=read(native/'physical-launch.json')
  assert receipt['status']=='ROUTED_STA_FAILED_NOT_BOARD' and receipt['run_id']==m['run_id']
  for rel,h in receipt['reports'].items():assert sha(native/'pds'/rel)==h,rel
  assert m['violations']
  for row in m['violations']:
   assert row['kind']=='hold' and row['clocks'] in [['cpu_clk','cpu_clk'],['sys_clk','sys_clk']] and -.05<=row['wns_ns']<0
  assert sd['voice_stream_enabled']
 elif line_fix:
  proof_path=native/'artifacts/build_evidence.json';proof=read(proof_path)
  assert m['sta_pass'] and m['strict_original_flow_pass'] and m['native_line_fix']
  assert m['run_id']==snap['run_id']==proof['run_id']=='dc951f8b1b7f4cf9962e5f509f165d0f'
  assert proof['timing']=='All Constraints Met' and proof['max_skew_verified'] and proof['timing_scope_verified']
  receipt=read(native/'physical-launch.json')
  assert receipt['status']=='ROUTED_FULL_STA_PASS_NOT_BOARD' and receipt['run_id']==m['run_id']
  for rel,h in receipt['reports'].items():assert sha(native/'pds'/rel)==h,rel
  assert sha(proof_path)==m['evidence_sha256']['build_evidence.json']
  assert sd['voice_stream_enabled']
 else:
  proof_path=R/'docs/validation/integrated60-physical-20261024/independent-reviewed-scope.json';review=read(proof_path)
  assert m['sta_pass'] and m['independent_review_pass'] and not m['strict_original_flow_pass']
  assert m['run_id']==snap['run_id']==review['run_id']=='866e820244ee4303a0295d68fe190076'
  assert review['status']=='ROUTED_STA_AND_REVIEWED_PIXEL_SCOPE_PASS_NOT_BOARD'
  for path,h in review['inputs_sha256'].items():assert sha(Path(path))==h,path
 hardware={}
 for rel,h in snap['inputs'].items():
  assert sha(native/rel)==h,rel
  if not rel.startswith('scripts/') and rel!='VERSION':
   assert sha(R/rel)==sha(native/rel)==h,rel;hardware[rel]=h
 assert len(hardware)==407
 assert sd['status']=='INTEGRATED60_RUNTIME_18_OFFLINE_TESTS_PASS_NATIVE_BOARD_PENDING' and len(sd['tests'])==18
 assert sd['cpu_hz']==60000000 and sd['original_picture_weights']
 compatibility={}
 if compatible_sd:
  original=R/'artifacts/integrated60_20261024';old_snap=read(N/'pds/build_snapshot.json')
  assert sd['candidate_manifest_sha256']==sha(original/'manifest.json')
  assert sd['candidate_run_id']==old_snap['run_id']=='866e820244ee4303a0295d68fe190076'
  assert sd['candidate_bitstream_sha256']==read(original/'manifest.json')['bitstream']['sha256']==sha(original/'soc_top.sbit')
  changed={rel for rel in hardware if old_snap['inputs'].get(rel)!=snap['inputs'][rel]}
  assert changed=={'rtl/mac_accel/vision32_layer.v'},changed
  assert sd['sys_hz']==49500000 and sd['clock_sha256']==snap['inputs']['config/clocks.json']
  assert sd['sbi_ratio']==[33,40] and sd['display']['refresh_hz']==30
  compatibility=dict(status='EXACT_SAME_SD_PAYLOADS_COMPATIBLE_WITH_VISION_DMA_BOUNDARY_FIX',
   original_sd_hardware_run=sd['candidate_run_id'],new_hardware_run=m['run_id'],
   original_candidate_manifest_sha256=sd['candidate_manifest_sha256'],new_candidate_manifest_sha256=sha(candidate/'manifest.json'),
   hardware_changed=sorted(changed),unchanged_hardware_inputs=len(hardware)-len(changed),
   payloads=sd['sd_root_files'],scope='Same CPU, ROM, clocks, driver ABI, MMIO and boot inputs; original SD write receipt retained unchanged.')
 else:assert sd['candidate_manifest_sha256']==sha(candidate/'manifest.json')
 for n,v in sd['sd_root_files'].items():assert sha(kit/'sd-root'/n)==v['sha256'],n
 writes=[]
 for p in write_root.glob('*/write-result.json'):
  d=read(p)
  if d['ManifestSHA256'].lower()==sha(kit/'manifest.json'):writes.append(p)
 assert len(writes)==1 and read(writes[0])['Status']=='SD_FILES_WRITTEN_READBACK_HASH_PASS_BOARD_PENDING'
 bit=native/'pds/generate_bitstream/soc_top.sbit';assert sha(bit)==sha(candidate/'soc_top.sbit')==m['bitstream']['sha256']
 return bit,dict(run_id=m['run_id'],bitstream_sha256=sha(bit),sd_manifest_sha256=sha(kit/'manifest.json'),
  sd_write_receipt=str(writes[0]),sd_write_sha256=sha(writes[0]),review_sha256=sha(proof_path),
  hardware_inputs_sha256=hardware,original_native_flow_status='ROUTED_STA_FAILED_NOT_BOARD' if functional_trial else 'ROUTED_FULL_STA_PASS_NOT_BOARD' if line_fix else 'FAILED_PIXEL_PRECISION_RECEIPT_UNCHANGED',
  native_sta_and_independent_review_pass=not functional_trial,functional_trial_sta_failed=functional_trial,sta_violations=m.get('violations',[]),software_sd_compatibility=compatibility,original_picture_weights=True,cpu_hz=60000000,sys_hz=49500000,
  flash_written=False,formal_delivery=False,scope='User Oct24 requests SD update and board model timing, then confirms card/power/UART/JTAG reconnected. Only exact CRAM candidate; no Flash.')
def main():
 p=argparse.ArgumentParser();p.add_argument('--program',action='store_true');p.add_argument('--line-fix',action='store_true');p.add_argument('--timing-failed-functional-trial',action='store_true');p.add_argument('--compatible-software-sd',action='store_true');p.add_argument('--port',default='COM17');p.add_argument('--sd-kit',type=Path,default=R/'build/integrated-sd-kit-04');p.add_argument('--write-root',type=Path,default=R/'build/integrated-sd-write-04');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert not a.output.exists();bit,result=preflight(a.sd_kit,a.write_root,a.line_fix,a.timing_failed_functional_trial,a.compatible_software_sd);a.output.mkdir(parents=True)
 result.update(status='INTEGRATED60_PREFLIGHT_PASS_NOT_PROGRAMMED',started_utc=datetime.now(timezone.utc).isoformat())
 save=lambda:(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 save()
 if not a.program:print(result['status']);return
 assert any(p.device==a.port and p.vid==0x10c4 and p.pid==0xea60 for p in comports()),'Fresh expected UART absent'
 uart=None;thread=None;stop=threading.Event();errors=[];captured=bytearray()
 try:
  uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5);uart.port=a.port;uart.dtr=False;uart.rts=False;uart.open()
  def capture():
   try:
    with (a.output/'program.uart').open('xb') as log:
     cancelled=False
     while not stop.is_set():
      data=uart.read(uart.in_waiting or 1)
      if data:
       log.write(data);log.flush();captured.extend(data);assert len(captured)<4*1024*1024
       if not cancelled and b'Flash autoboot in 3s' in captured:uart.write(b'\x1b');cancelled=True
   except Exception as e:errors.append(repr(e))
  thread=threading.Thread(target=capture);thread.start()
  command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(R/'scripts/program_cram.ps1'),'-Program','-AllowExternalSbit','-SbitPath',str(bit),'-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-LogPath',str(a.output/'program.log'),'-EvidencePath',str(a.output/'program.json')]
  result.update(status='INTEGRATED60_PROGRAMMING',command=command,port=a.port);save()
  with (a.output/'owner.log').open('xb') as log:child=subprocess.run(command,cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  assert child.returncode==0,'Programming failed: inspect native log'
  proof=read(a.output/'program.json')
  assert proof['status']=='PASS' and proof['device_id']=='0x00602899' and proof['device_count']==1 and proof['operation']=='CRAM' and proof['bitstream_sha256']==result['bitstream_sha256']
  time.sleep(3)
  for cmd in ['','info','sdinfo']:uart.write((cmd+'\r').encode());time.sleep(2)
  assert not errors
  result.update(status='INTEGRATED60_CRAM_DONE_PASS_SD_BOOT_PENDING',program_receipt_sha256=sha(a.output/'program.json'))
 except Exception as e:result.update(status='INTEGRATED60_PROGRAM_FAILED_ACTUAL_BOARD_STATE_PRESERVED',error=repr(e));raise
 finally:
  stop.set()
  if thread:thread.join(5)
  if uart:uart.close()
  result.update(completed_utc=datetime.now(timezone.utc).isoformat(),capture_errors=errors)
  if (a.output/'program.uart').exists():result['uart_sha256']=sha(a.output/'program.uart')
  save();print(result['status'],flush=True)
if __name__=='__main__':main()
