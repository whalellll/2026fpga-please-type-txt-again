"""Program only accepted CPU120 volatile CRAM after fresh unique device scan."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,re,socket,subprocess,threading,time
import serial,serial.tools.list_ports
from verify_cpu120_zbc_board_release import verify,sha,BIT,RUN
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--pds',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',default='COM17');p.add_argument('--jtag-port',type=int,default=65426);p.add_argument('--host-gcc',required=True);a=p.parse_args()
 root=a.root.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tmp=out/'tmp';tmp.mkdir();env=dict(os.environ,TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1')
 record=dict(status='PREFLIGHT',started_utc=datetime.now(timezone.utc).isoformat(),bitstream_sha256=BIT,native_run=RUN,board_programmed=False,program_attempted=False,flash_written=False,sd_written=False)
 def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 verify(root,'docs/validation/cpu120-zbc-fc1-20261101/release-manifest.json',out/'source-contract',a.host_gcc)
 bit=root/'artifacts/soc_top.sbit';assert sha(bit)==BIT
 assert any(q.device==a.port for q in serial.tools.list_ports.comports()),'UART absent'
 stop=threading.Event();capture=bytearray();errors=[];server=None;streams=[];uart=None;thread=None
 def listen():
  try:
   with (out/'program.uart').open('xb') as log:
    cancelled=False
    while not stop.is_set():
     data=uart.read(uart.in_waiting or 1)
     if data:
      capture.extend(data);log.write(data);log.flush();assert len(capture)<4*1024**2
      if not cancelled and b'Flash autoboot in 3s' in capture:uart.write(b'\x1b');cancelled=True
  except Exception as error:errors.append(repr(error))
 def start_server(tag):
  nonlocal server
  with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',a.jtag_port))!=0,'JTAG port already owned'
  stdout=(out/(tag+'-server.stdout')).open('xb');stderr=(out/(tag+'-server.stderr')).open('xb');streams.extend([stdout,stderr])
  server=subprocess.Popen([str(a.pds/'bin/cdt_js.exe'),'-port',str(a.jtag_port),'-work_dir',str(out)],cwd=a.pds/'bin',env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
  record['jtag_server_pid']=server.pid;save()
  for _ in range(50):
   with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',a.jtag_port))==0:return
   assert server.poll() is None;time.sleep(.2)
  raise TimeoutError('Owned JTAG server startup')
 def close_server():
  if server and server.poll() is None:
   try:server.wait(5)
   except subprocess.TimeoutExpired:server.terminate();server.wait(10)
 def cfg(tag,commands):
  script=out/(tag+'.tcl');script.write_text('\n'.join(commands)+'\n')
  assert not re.search(r'\bcfg_\w*(?:flash|erase|otp|security)\w*\b',script.read_text(),re.I)
  command=[str(a.pds/'bin/cdt_cfg_shell.exe'),'-file',str(script),'-work_dir',str(out),'-report_dir',str(out)]
  with (out/(tag+'.stdout')).open('xb') as log:code=subprocess.run(command,cwd=a.pds/'bin',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW).returncode
  text=(out/(tag+'.stdout')).read_text(errors='replace');assert code==0 and not re.search(r'(?m)^\s*E:',text)
  return text
 base=['cfg_set_tcl_break -flag true',f'cfg_connect -ip 127.0.0.1 -port {a.jtag_port}','cfg_scan_chain','after 1000','cfg_read_device_property -mode 0 -device_index 0'];tail=['cfg_disconnect','cfg_close']
 try:
  save();uart=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5);uart.port=a.port;uart.dtr=False;uart.rts=False;uart.open();thread=threading.Thread(target=listen);thread.start()
  start_server('scan');text=cfg('scan',base+tail)
  assert len(re.findall(r'(?im)^\s*PG2L100H\s*$',text))==1 and len(re.findall(r'(?im)^\s*The ID value is:\s*0x00602899\s*$',text))==1 and text.count('This device configure situation')==1
  record.update(status='FRESH_UNIQUE_PG2L100H_ID_PASS',device_id='0x00602899',device_count=1);save();close_server()
  assert sha(bit)==BIT;start_server('program');record.update(status='PROGRAMMING_VOLATILE_CRAM',program_attempted=True);save()
  text=cfg('program',base+[f'cfg_assign_file -file {{{bit.as_posix()}}} -device_index 0','cfg_program -device_index 0','cfg_read_device_property -mode 3 -device_index 0']+tail)
  assert 'cfg_program -device_index 0 successfully.' in text and re.search(r'(?m)^Bit 12:\s+1\s+done\s*$',text)
  record.update(board_programmed=True,done=1);save();time.sleep(4)
  for cmd in ['', 'info']:uart.write((cmd+'\r').encode());time.sleep(2)
  assert sha(bit)==BIT and not errors and all(v in capture for v in [b'120000000',b'49500000',b'DDR',b'soc> '])
  record['status']='CPU120_PACKAGED_CRAM_DONE1_CPU120_SYS49_5_BOOT_CONTRACT_PASS_SD_BOOT_PENDING'
 except Exception as error:record.update(status='FAILED_ACTUAL_PROGRAM_STATE_PRESERVED',error=repr(error));raise
 finally:
  stop.set()
  if thread:thread.join(5)
  if uart:uart.close()
  close_server()
  for stream in streams:stream.close()
  record.update(completed_utc=datetime.now(timezone.utc).isoformat(),uart_sha256=sha(out/'program.uart') if (out/'program.uart').exists() else None,capture_errors=errors);save();print(json.dumps(record),flush=True)
if __name__=='__main__':main()
