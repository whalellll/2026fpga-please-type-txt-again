"""Run the prespecified720p/1080p CoreMark A/B/A/B experiment in volatile CRAM."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, statistics, subprocess, threading, time
from verify_gui1080_native import validate, sha, read
from verify_sdboot_native import validate as control_validate

CONTROL_BIT='30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['root','work','plan','output']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--control-root',type=Path,default=Path('G:/fpga/c80audio_unpack_20261022_r3/SOC'))
    ap.add_argument('--control-work',type=Path,default=Path('G:/fpga/c80audio_unpack_20261022_r3/SOC/docs/validation/cpu80-conv-sdboot-20261022/attempt-03'))
    ap.add_argument('--control-audit-root',type=Path,default=Path('G:/fpga/c80audio_unpack_20261022_r3/SOC'))
    ap.add_argument('--port',default='COM17');a=ap.parse_args()
    source=Path(__file__).resolve().parents[1];out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
    result=dict(status='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),scope='Volatile CRAM and production ROM CoreMark only; no SD/Flash write',batches=[])
    def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(cmd,log,timeout):
        with log.open('xb') as stream:p=subprocess.run(list(map(str,cmd)),cwd=source,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        assert p.returncode==0,log
    def control_program(folder):
        folder.mkdir();stop=threading.Event();errors=[];captured=bytearray()
        import serial
        serial_port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=5)
        serial_port.port=a.port;serial_port.dtr=False;serial_port.rts=False;serial_port.open()
        def capture():
            try:
                with (folder/'program.uart').open('xb') as stream:
                    cancelled=False
                    while not stop.is_set():
                        data=serial_port.read(serial_port.in_waiting or 1)
                        if data:
                            stream.write(data);stream.flush();captured.extend(data)
                            assert len(captured)<4*1024*1024
                            if not cancelled and b'Flash autoboot in 3s' in captured:
                                serial_port.write(b'\x1b');cancelled=True
            except Exception as error:errors.append(repr(error))
        thread=threading.Thread(target=capture);thread.start()
        try:
            run(['G:/py/ana/python.exe','-B',source/'scripts/program_repaired_rom.py','--root',a.control_root,'--work',a.control_work,'--output',folder,'--attempt','1'],folder/'owner.log',700)
            time.sleep(3)
        finally:
            stop.set();thread.join(timeout=5);serial_port.close()
        assert not thread.is_alive() and not errors,errors
        proof=read(folder/'program-01-binding.json');program=read(folder/'program-01.json')
        assert proof['status']=='REPAIRED_ROM_CRAM_PROGRAM_PASS_BOARD_TESTS_PENDING'
        assert program['status']=='PASS' and program['device_id']=='0x00602899' and program['bitstream_sha256']==CONTROL_BIT
        return folder/'program-01-binding.json'
    save()
    try:
        plan=read(a.plan);result['plan_sha256']=sha(a.plan)
        assert plan['coremark_order']==['control-a','candidate-a','control-b','candidate-b']
        assert plan['coremark_per_batch']==dict(performance=3,validation=1,minimum_seconds=10)
        assert plan['coremark_total_gate'] is False and plan['coremark_per_mhz_absolute_decrease_limit']==.05
        result['candidate']=validate(a.root,a.work);result['control']=control_validate(a.control_root,a.control_work)
        assert result['candidate']['run_id']==plan['candidate_native_run']
        assert result['candidate']['soc_implementation_commit']==plan['candidate_implementation']
        assert result['control']['bitstream_sha256']==CONTROL_BIT==plan['accepted_control_bitstream_sha256']
        assert sha(a.control_audit_root/'artifacts/soc_top.sbit')==CONTROL_BIT
        assert sha(a.control_audit_root/'artifacts/bootloader.bin')==sha(a.control_root/'artifacts/bootloader.bin')
        # Full accepted project audit supplements the original immutable native verifier.
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',a.control_audit_root/'scripts/audit_cpu80_approved.ps1','-Root',a.control_audit_root],out/'accepted-control-audit.log',240)
        for label in plan['coremark_order']:
            root=a.control_root if label.startswith('control') else a.root
            entry=dict(label=label,status='PROGRAMMING');result['batches'].append(entry);save()
            folder=out/label
            if label.startswith('control'):program_receipt=control_program(folder)
            else:
                run(['G:/py/ana/python.exe','-B',source/'scripts/program_gui1080_candidate.py','--root',a.root,'--work',a.work,'--output',folder,'--port',a.port,'--program'],out/(label+'-program-owner.log'),900)
                program_receipt=folder/'result.json'
                assert read(program_receipt)['status']=='GUI1080_CRAM_PROGRAM_PASS_RUNTIME_BOOT_PENDING'
            entry.update(status='MEASURING',program_receipt=str(program_receipt),program_receipt_sha256=sha(program_receipt));save()
            measure=folder/'coremark'
            run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',source/'scripts/measure_coremark.ps1','-Port',a.port,'-CpuHz','80000000','-Optimization','O2','-BitstreamPath',root/'artifacts/soc_top.sbit','-FirmwarePath',root/'artifacts/bootloader.bin','-OutputDirectory',measure],folder/'measure-owner.log',900)
            record=read(measure/'result.json')
            assert record['status']=='PASS' and record['board_acceptance'] and len(record['runs'])==4
            assert record['bitstream']['sha256']==sha(root/'artifacts/soc_top.sbit')
            assert record['firmware']['sha256']==sha(root/'artifacts/bootloader.bin')
            assert record['log_sha256']==sha(measure/'uart.log')
            entry.update(status='PASS',coremark_result=str(measure/'result.json'),coremark_result_sha256=sha(measure/'result.json'));save()
        comparisons={}
        for side in ['control','candidate']:
            runs=[]
            for entry in result['batches']:
                if entry['label'].startswith(side):runs.extend(read(Path(entry['coremark_result']))['runs'][:3])
            assert len(runs)==6
            comparisons[side]={key:dict(all_values=[float(r[key]) for r in runs],mean=statistics.mean(float(r[key]) for r in runs)) for key in ['iterations_per_second','coremark_per_mhz']}
        drop=comparisons['control']['coremark_per_mhz']['mean']-comparisons['candidate']['coremark_per_mhz']['mean']
        result.update(comparisons=comparisons,coremark_per_mhz_absolute_decrease=drop,per_mhz_limit=.05,total_score_gate=False,final_program_receipt=result['batches'][-1]['program_receipt'])
        assert drop<=.05,'CoreMark/MHz exceeds the user limit; preserve all samples'
        result['status']='GUI1080_COREMARK_ABAB_ALL_SAMPLES_CRC_TIME_PER_MHZ_PASS_LINUX_PENDING'
    except Exception as error:
        result.update(status='FAILED_COREMARK_ABAB_PRESERVED_ACTUAL_BOARD_STATE',error=repr(error));raise
    finally:
        result['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(json.dumps(result),flush=True)

if __name__=='__main__':main()
