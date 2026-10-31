"""Bounded CRAM-only approved CPU80 / merged-main CPU70 CoreMark ABAB."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,statistics,subprocess,threading,time
import serial
from workspace_paths import workspace_path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--resume',type=Path,help='Preserve a failed owner and reuse its fully verified first A/B groups')
    ap.add_argument('--program-with-uart-closed',action='store_true',help='Controlled JTAG recovery; capture fresh ROM info after programming')
    a=ap.parse_args();out=workspace_path(a.output);assert not out.exists();out.mkdir(parents=True)
    temporary=out/'tmp';temporary.mkdir();env=dict(os.environ,TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary))
    record=dict(status='RUNNING_COREMARK_ABAB',started_utc=datetime.now(timezone.utc).isoformat(),owner_pid=os.getpid(),batches=[],per_mhz_absolute_decrease_limit=.05,total_score_gate=False,flash_written=False,sd_written=False)
    def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    def run(command,log,timeout=900):
        with log.open('xb') as f:
            p=subprocess.Popen(list(map(str,command)),cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
            try:code=p.wait(timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True);raise
        assert code==0,(command,log)
    reference=Path('G:/fpga/m80c');candidate=Path('G:/fpga/m70d')
    tool=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File']
    start=0
    if a.resume:
        old=read(a.resume/'result.json');assert old['status']=='FAILED_PRESERVED'
        assert [x['label'] for x in old['batches'][:2]]==['control-a','candidate-a']
        assert old['batches'][2]['label']=='control-b' and old['batches'][2]['status']=='PROGRAMMING'
        for batch in old['batches'][:2]:
            assert batch['status']=='PASS' and sha(Path(batch['program_receipt']))==batch['program_sha256']
            assert sha(Path(batch['coremark_result']))==batch['coremark_sha256']
            record['batches'].append(batch)
        record['failed_owner_receipt']=str(a.resume/'result.json');record['failed_owner_sha256']=sha(a.resume/'result.json')
        record['recovery']='UART closed for JTAG; initial A/B samples retained, failed control-b scan did not assign/program or measure'
        start=2
    record['program_with_uart_closed']=a.program_with_uart_closed
    save()
    try:
        for index,(label,root,cpu,script,profile) in enumerate([
            ('control-a',reference,80000000,'program_with_approved_gate.ps1','CPU80Approved'),
            ('candidate-a',candidate,70000000,'program_cram.ps1','Main70Candidate'),
            ('control-b',reference,80000000,'program_with_approved_gate.ps1','CPU80Approved'),
            ('candidate-b',candidate,70000000,'program_cram.ps1','Main70Candidate')]):
            if index<start:continue
            folder=out/label;folder.mkdir();item=dict(label=label,status='PROGRAMMING',cpu_hz=cpu,source_root=str(root));record['batches'].append(item);save()
            bit=root/'artifacts/soc_top.sbit';firmware=root/'artifacts/bootloader.bin'
            command=tool+[root/'scripts'/script,'-Program','-AuditProfile',profile,'-PdsRoot','G:/fpga/PDS_2022.2-SP6.4','-SbitPath',bit,'-JtagServerPort',str(65430+index),'-LogPath',folder/'program.log','-EvidencePath',folder/'program.json']
            if profile=='Main70Candidate':command+=['-TrialDirectory',ROOT/'build/main70-20261027-02']
            port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2);port.port='COM17';port.dtr=False;port.rts=False
            stop=threading.Event();errors=[]
            def capture():
                try:
                    with (folder/'boot.uart').open('xb') as f:
                        total=0
                        while not stop.is_set():
                            chunk=port.read(port.in_waiting or 1);total+=len(chunk);assert total<4*1024*1024
                            if chunk:f.write(chunk);f.flush()
                except Exception as e:errors.append(repr(e))
            if a.program_with_uart_closed:
                run(command,folder/'program-host.log',600)
                port.open();data=bytearray();port.write(b'\r');time.sleep(.2);port.write(b'info\r');deadline=time.monotonic()+3
                while time.monotonic()<deadline:data+=port.read(port.in_waiting or 1)
                port.close();(folder/'boot.uart').write_bytes(data)
                assert b'soc>' in data,'Fresh ROM prompt missing after UART-closed programming'
            else:
                port.open();thread=threading.Thread(target=capture);thread.start()
                try:run(command,folder/'program-host.log',600);time.sleep(2)
                finally:stop.set();thread.join(5);port.close()
            assert not errors,errors
            assigned=read(folder/'program.json');assert assigned['status']=='PASS' and assigned['bitstream_sha256']==sha(bit)
            item.update(status='MEASURING',program_receipt=str(folder/'program.json'),program_sha256=sha(folder/'program.json'));save()
            run(tool+[ROOT/'scripts/measure_coremark.ps1','-Port','COM17','-CpuHz',str(cpu),'-Optimization','O2','-CompilerVersion','16.2.0','-BitstreamPath',bit,'-FirmwarePath',firmware,'-OutputDirectory',folder/'coremark'],folder/'measure.log')
            measured=read(folder/'coremark/result.json')
            assert measured['status']=='PASS' and measured['board_acceptance'] and len(measured['runs'])==4
            assert measured['bitstream']['sha256']==sha(bit) and measured['firmware']['sha256']==sha(firmware)
            assert all(x['validated'] and x['duration_seconds']>=10 and x['cpu_hz']==cpu for x in measured['runs'])
            item.update(status='PASS',coremark_result=str(folder/'coremark/result.json'),coremark_sha256=sha(folder/'coremark/result.json'));save()
        summaries={}
        for side in ['control','candidate']:
            samples=[x for batch in record['batches'] if batch['label'].startswith(side) for x in read(Path(batch['coremark_result']))['runs'] if x['mode']=='performance']
            assert len(samples)==6
            summaries[side]=dict(samples=samples,mean_coremark_per_mhz=statistics.mean(x['coremark_per_mhz'] for x in samples),mean_coremark=statistics.mean(x['iterations_per_second'] for x in samples))
        drop=summaries['control']['mean_coremark_per_mhz']-summaries['candidate']['mean_coremark_per_mhz']
        record.update(summaries=summaries,coremark_per_mhz_absolute_decrease=drop,final_program_receipt=record['batches'][-1]['program_receipt'])
        assert drop<=.05,'CoreMark/MHz absolute mean decrease exceeds0.05'
        record['status']='MAIN70_COREMARK_ABAB_ALL_SAMPLES_CRC_TIME_PER_MHZ_PASS_LINUX_PENDING'
    except Exception as e:
        record.update(status='FAILED_PRESERVED',error=repr(e));raise
    finally:record['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(record['status'])

if __name__=='__main__':main()
