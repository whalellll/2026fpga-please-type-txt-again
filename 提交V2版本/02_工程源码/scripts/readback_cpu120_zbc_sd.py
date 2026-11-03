"""ZIP-bound complete SD8 readback through a read-only volatile DDR payload."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,binascii,hashlib,json,re,time,zipfile
import serial
from verify_cpu120_zbc_board_release import BIT,RUN,sha,read

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--root',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--verification',type=Path,required=True);p.add_argument('--program',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='COM17');a=p.parse_args()
 root=a.root.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 record=dict(status='SD8_READONLY_PREFLIGHT',archive_sha256=sha(a.archive),started_utc=datetime.now(timezone.utc).isoformat(),bitstream_sha256=BIT,native_run=RUN,board_accessed=False,sd_written=False,flash_written=False,deployment_mode='Retain already-identical SD files; compare complete actual media bytes to independent extracted package')
 capture=bytearray();uart=None
 def until(pattern,seconds,echo=False):
  start=len(capture);deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:
   data=uart.read(uart.in_waiting or 1)
   if data:
    capture.extend(data)
    if echo:print(data.decode('utf-8','replace'),end='',flush=True)
   assert len(capture)<4*1024**2
   if re.search(pattern,capture[start:]):return bytes(capture[start:])
  raise TimeoutError(repr(pattern))
 def control(expected,seconds=8):
  deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:
   x=uart.read(1)
   if x:
    capture.extend(x)
    if x[0] in (6,21,24,67):assert x[0] in expected;return x[0]
  raise TimeoutError('XMODEM control')
 try:
  verification=read(a.verification);program=read(a.program)
  assert verification['status']=='CPU120_ZIP_INDEPENDENT_UNPACK_CPU134_ARCH9_SOC_FC1_38_REGRESSION_PASS_MEDIA_PENDING'
  assert verification['archive_sha256']==record['archive_sha256'] and (Path(verification['extraction'])/'SOC').resolve()==root
  assert program['board_programmed'] and program['done']==1 and program['bitstream_sha256']==BIT and program['native_run']==RUN
  kit=read(root/'software/cpu120/sd/manifest.json');expected=kit['sd_root_files'];assert len(expected)==8 and kit['bitstream_sha256']==BIT
  payload_root=root/'software/cpu120-zbc/sd8-readonly-payload-02';built=read(payload_root/'result.json')
  assert built['expected_sd_files']==expected and built['sd_flash_write_symbols_absent'] is True
  for name,digest in built['source_files_sha256'].items():assert sha(payload_root/name)==digest,name
  assert sha(payload_root/'payload.bin')==built['payload_sha256'] and built['entry']=='0x01000000' and built['buffer']=='0x03000000'
  with zipfile.ZipFile(a.archive) as z:
   manifest=json.loads(z.read('SOC/DELIVERY.json'));assert manifest['bitstream_sha256']==BIT and manifest['native_run']==RUN
   for n,info in expected.items():
    assert sha(root/'linux/boot'/n)==info['sha256'] and (root/'linux/boot'/n).stat().st_size==info['bytes']
    assert manifest['files']['SOC/linux/boot/'+n]==info
  data=(payload_root/'payload.bin').read_bytes();assert 0<len(data)<49152
  record.update(program_receipt_sha256=sha(a.program),independent_verification_sha256=sha(a.verification),payload_sha256=built['payload_sha256'],package_root=str(root),expected_sd_files=expected)
  uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5);uart.port=a.port;uart.dtr=False;uart.rts=False;uart.open();record['board_accessed']=True
  uart.write(b'\r');until(rb'soc> ',10)
  uart.write(b'loadx 0x01000000\r');until(rb'Start XMODEM-CRC transfer now\.\.\.',10);control({67})
  padded=(len(data)+1023)//1024*1024
  for offset in range(0,padded,1024):
   seq=(offset//1024+1)&255;block=data[offset:offset+1024].ljust(1024,b'\x1a');crc=binascii.crc_hqx(block,0);packet=bytes([2,seq,255-seq])+block+crc.to_bytes(2,'big')
   for attempt in range(4):
    for i in range(0,len(packet),8):uart.write(packet[i:i+8]);time.sleep(.006)
    if control({6,21})==6:break
   else:raise RuntimeError('XMODEM retry limit')
  uart.write(b'\x04');control({6});text=until(rb'soc> ',15);assert ('received '+str(padded)+' bytes').encode() in text
  uart.write(b'boot 0x01000000\r');text=until(rb'SD8_READONLY_(?:SHA256_PASS files=8|FAIL)',1200,echo=True)
  assert b'SD8_READONLY_SHA256_PASS files=8' in text and b'SD8_READONLY_FAIL' not in text
  actual={}
  for name,size,digest in re.findall(rb'SD8_FILE name=(\S+) bytes=(\d+) sha256=([0-9a-f]{64})',text):
   name=name.decode();assert name not in actual;actual[name]=dict(bytes=int(size),sha256=digest.decode())
  assert actual==expected
  cid=re.findall(rb'SD8_CID (\S+) sectors=(\d+)',text);assert len(cid)==1
  assert sha(a.archive)==record['archive_sha256']
  record.update(status='ZIP_BOUND_ACTUAL_SD8_FULL_READONLY_SHA256_CID_PASS_DIRECT_SD_BOOT_PENDING',actual_sd_files=actual,card_cid=cid[0][0].decode(),card_sectors=int(cid[0][1]),loader_restore_required=True)
 except Exception as error:record.update(status='SD8_READONLY_FAILED_ACTUAL_STATE_PRESERVED',error=repr(error));raise
 finally:
  if uart:uart.close()
  (out/'uart.bin').write_bytes(capture);record.update(completed_utc=datetime.now(timezone.utc).isoformat(),uart_sha256=sha(out/'uart.bin'))
  (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(record['status'],flush=True)
if __name__=='__main__':main()
