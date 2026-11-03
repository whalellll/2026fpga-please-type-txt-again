"""Real fixed-input CPU70 Linux/model checks after the matching direct SD boot."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys
from workspace_paths import workspace_path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--compute-only',action='store_true',help='Explicitly leave GUI failed/pending; test unchanged model paths independently')
    ap.add_argument('--output-name',default='board-tests-01')
    a=ap.parse_args();work=workspace_path(a.work);assert Path(a.output_name).name==a.output_name;out=work/a.output_name;assert not out.exists();out.mkdir()
    boot=read(work/'boot-01/result.json');assert boot['status']=='MAIN70_DIRECT_SD6_PAYLOAD_CRC_LINUX_ROOT_PASS_APPLICATIONS_PENDING'
    kit=read(work/'kit-02/manifest.json');record=dict(status='RUNNING_CURRENT_SD_BOARD_CHECKS',owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),boot_receipt_sha256=sha(work/'boot-01/result.json'),kit_manifest_sha256=sha(work/'kit-02/manifest.json'),checks=[],physical_hdmi_confirmed=False,gui_restored=False)
    sources={str(p):sha(p) for p in [Path(__file__),ROOT/'scripts/board_console.py',ROOT/'scripts/board_boot_contract.py']}
    def save():(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    def c(command,timeout=90,markers=(),allowed=(0,)):
        assert len(command.encode())+80<=900
        return dict(command=command,timeout=timeout,markers=list(markers),allowed_exit=list(allowed))
    def group(name,commands,timeout=600):
        spec=out/(name+'-spec.json');spec.write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(name+'.host.log')).open('xb') as log:
            p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/board_console.py'),'commands','--port','COM17','--pace-bytes','2','--log',str(out/(name+'.uart')),'--spec',str(spec)],stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        result=read(out/(name+'.result.json'));record['checks'].append(dict(name=name,status=result['status'],exit=p.returncode,result_sha256=sha(out/(name+'.result.json'))));save()
        assert p.returncode==0 and result['status']=='BOARD_COMMAND_SPEC_PASS',name
        return (out/(name+'.uart')).read_text(errors='replace').replace('\r',''),result
    save();stopped=False
    try:
        identity=[
            c('uname -a; cat /etc/pikafish-sw-build.json',30,['cpu_hz','70000000',kit['candidate_bitstream_sha256']]),
            c('test "$(busybox devmem 0x1fe00314)" = 0x042C1D80 && test "$(busybox devmem 0x1fe00318)" = 0x02F34F60 && echo MAIN70_MMIO_CLOCK_PASS',30,['MAIN70_MMIO_CLOCK_PASS']),
            c('ps; ls -l /dev/pango*; /usr/bin/pikafish-batch-check',30,['PIKAFISH_BATCH_CAPABILITY_PASS']),
            c('sha256sum /usr/bin/xinyi-one /usr/bin/xq-coach-worker; cat /etc/main-current-cram.sha256',90,[sha(work/'product/xinyi-one-stripped'),'1953b37d6511e21fe5eb0675dbee7285a1e06b42b3b43e60cd8edda0c6220de3',kit['candidate_bitstream_sha256']]),
        ]
        if not a.compute_only:identity.append(c('for main_i in $(seq 1 90); do grep -q XINYI_GUI_FIRST_PRESENTED /run/main-xinyi.log && break; sleep 1; done; cat /run/main-xinyi.log; grep -q XINYI_GUI_FIRST_PRESENTED /run/main-xinyi.log',110,['XINYI_GUI_FIRST_PRESENTED']))
        group('identity',identity,350)
        if not a.compute_only:
            group('stop-gui',[c('p=$(cat /run/main-xinyi.pid); test "$(readlink /proc/$p/exe)" = /usr/bin/xinyi-one && kill -TERM $p; for main_i in $(seq 1 90); do kill -0 $p 2>/dev/null || break; sleep 1; done; ! kill -0 $p 2>/dev/null && echo MAIN70_GUI_STOPPED',110,['MAIN70_GUI_STOPPED']),c('! pidof xinyi-one xinyi-engine xq-coach-worker xinyi-speech-worker && echo MAIN70_PRODUCT_CHILDREN_IDLE',30,['MAIN70_PRODUCT_CHILDREN_IDLE'])],180)
            stopped=True
        else:
            group('product-idle',[c('! pidof xinyi-one xinyi-engine xq-coach-worker xinyi-speech-worker && echo MAIN70_PRODUCT_CHILDREN_IDLE',30,['MAIN70_PRODUCT_CHILDREN_IDLE'])],60)
            record['gui_acceptance']='FAILED/PENDING; compute-only groups do not accept GUI'
        _,timing=group('clock',[c('sleep 5; echo MAIN70_SLEEP5_DONE',15,['MAIN70_SLEEP5_DONE'])],40)
        elapsed=timing['commands'][0]['host_response_seconds'];assert 4.5<=elapsed<=7.0,('Linux timer/host mismatch',elapsed)
        record['linux_sleep5_host_seconds']=elapsed;save()
        rows=[]
        for resident in [0,1]:
            for trial in range(3):rows.append(c(f'echo MAIN70_NNUE enabled={resident} trial={trial}; PIKAFISH_ACCUM_RESIDENT={resident} /usr/bin/run-pikafish-sw-bench 200',180,['NNUE_LATENCY_CORRECTNESS_PASS','fallbacks=0 mismatches=0',f'NNUE_ACCUM_RESIDENT phase=warm enabled={resident}'],(0,2)))
        group('nnue',rows,1250)
        group('search',[c(f'. /etc/pikafish-batch.env; PIKAFISH_ACCUM_RESIDENT={resident} PIKAFISH_PHASE4_NODES=128 /usr/bin/timeout 240 /usr/bin/pikafish-pipeline-search',260,['PIKAFISH_PIPELINE_SEARCH_PASS mode=1 cases=3 nodes=128']) for resident in [0,1]],600)
        old=ROOT/'build/board-functional-20261026-01/board-tests-03'
        vision=read(old/'vision-spec.json');group('vision',vision,1500)
        group('voice',read(old/'voice-spec.json'),450)
        group('mixed',read(old/'mixed-spec.json'),700)
        group('microphone',read(old/'microphone-spec.json'),70)
        # Bare-metal official CoreMark already has its full ABAB gate. This
        # extra Linux/UI port check is reported separately, without replacing it.
        group('linux-coremark',[c('/usr/bin/timeout 90 /usr/bin/xinyi-coremark --target-ms 30000 --cpu-hz 70000000 --identity '+kit['candidate_bitstream_sha256'],110,['XY_CM_RESULT kind=riscv32-linux valid=1'])],150)
        record.update(status='MAIN70_DIRECT_SD_FIXED_MODELS_SEARCH_CONCURRENCY_AND_LINUX_TIMER_GROUPS_PASS_PHYSICAL_IO_PENDING',nnue_10ms_goal='Inspect UART; exit2 is a preserved goal miss, not correctness failure',picture_30fps_goal='Not established by these fixed-input tests',coach_worker='User-authorized original PN07 binary',voice_3_merged=False)
    except Exception as error:record.update(status='FAILED_PRESERVED',error=repr(error));raise
    finally:
        if stopped:
            try:
                group('restore-gui',[c('/usr/bin/start-main-xinyi </dev/null >/run/main-xinyi.log 2>&1 & echo $! >/run/main-xinyi.pid; echo MAIN70_GUI_RESTARTED',20,['MAIN70_GUI_RESTARTED']),c('for main_i in $(seq 1 90); do grep -q XINYI_GUI_FIRST_PRESENTED /run/main-xinyi.log && break; sleep 1; done; tail -n 10 /run/main-xinyi.log; grep -q XINYI_GUI_FIRST_PRESENTED /run/main-xinyi.log',110,['XINYI_GUI_FIRST_PRESENTED'])],160)
                record['gui_restored']=True
            except Exception as error:record['restore_error']=repr(error)
        assert all(sha(Path(p))==h for p,h in sources.items()),'Board runner source changed during tests'
        record['sources_sha256']=sources;record['completed_utc']=datetime.now(timezone.utc).isoformat();record['evidence_sha256']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='result.json'};save();print(record['status'])

if __name__=='__main__':main()
