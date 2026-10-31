"""Collect1080p model/audio/scanout evidence after the verified ROM TFTP boot."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,re,subprocess
from verify_gui1080_native import validate,read,sha

def display(text,expected_refresh_hz=60):
    assert expected_refresh_hz in (30,60),'Unsupported1080p scanout contract'
    def number(name):
        found=re.findall(r'(?m)^'+re.escape(name)+r'=(0x[0-9A-Fa-f]+)',text)
        assert len(found)==1,(name,found)
        return int(found[0],16)
    values={name:number('FB_'+name) for name in ['10','14','18','1c','20','0c']}
    assert [values[n] for n in ['10','14','18','1c','20']]==[0x1b800000,0x1bc00000,3840,0x04380780,4147200]
    assert values['0c']&2 and not values['0c']&0x28,'Scanout inactive/underflow/DMA error'
    before=number('BEFORE_FRAME');after=number('AFTER_FRAME')
    assert number('BEFORE_UFLOW')==number('AFTER_UFLOW')==0
    times=[float(re.search(r'(?m)^'+name+r'_UPTIME=([0-9.]+)',text)[1]) for name in ['BEFORE','AFTER']]
    assert times[1]>times[0]
    hz=((after-before)&0xffffffff)/(times[1]-times[0]);assert expected_refresh_hz*29/30<=hz<=expected_refresh_hz*31/30,(hz,times)
    return dict(registers=values,frame_delta=(after-before)&0xffffffff,uptime_delta=times[1]-times[0],observed_frame_hz=hz,underflows=0)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['root','work','specs','plan','netboot-receipt','control-binding','output']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--port',default='COM17');a=ap.parse_args()
    source=Path(__file__).resolve().parents[1];out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
    result=dict(status='PREFLIGHT',started_utc=datetime.now(timezone.utc).isoformat(),checks=[],sd_used=False,hdmi_visual='USER_CONFIRMATION_PENDING',model_integrity='Host SHA256 + ROM hexcrc block checks + official model correctness; full model DDR SHA256 readback not claimed')
    save=lambda:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    save();quiet=False;restored=False
    def spec(name):return read(a.specs/name)
    def run(name,rows):
        path=out/(name+'-spec.json');path.write_text(json.dumps(rows,indent=2)+'\n')
        cmd=['G:/py/ana/python.exe','-B',source/'scripts/board_console.py','commands','--port',a.port,'--log',out/(name+'.uart'),'--spec',path]
        with (out/(name+'.host.log')).open('xb') as f:p=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT,timeout=1500)
        receipt=out/(name+'.result.json');r=read(receipt)
        result['checks'].append(dict(name=name,status=r['status'],receipt_sha256=sha(receipt)));save()
        assert p.returncode==0 and r['status']=='BOARD_COMMAND_SPEC_PASS',name
        return (out/(name+'.uart')).read_text(errors='replace').replace('\r','')
    try:
        result['native']=validate(a.root,a.work);manifest=read(a.specs/'manifest.json');plan=read(a.plan)
        assert manifest['native_run']==result['native']['run_id']==plan['candidate_native_run'] and manifest['plan_sha256']==sha(a.plan)
        for name,h in manifest['files_sha256'].items():assert sha(a.specs/name)==h,name
        boot=read(a.netboot_receipt);assert boot['status']=='GUI1080_TFTP_LINUX_ROOT_SELECTED_GUI_HASH_PASS_FUNCTIONAL_PENDING' and boot['native']==result['native']
        control=read(a.control_binding);assert sha(a.control_binding)==plan['control_models_binding_sha256']
        assert control['status']=='ACCEPTED720_CONTROL_MODEL_REFERENCE_80_NNUE_200_DENSE_SAMPLES_PASS_GUI_VOICE_RESTORED'
        result.update(status='FUNCTIONAL_RUNNING',plan_sha256=sha(a.plan),spec_manifest_sha256=sha(a.specs/'manifest.json'),netboot_receipt_sha256=sha(a.netboot_receipt),control_binding_sha256=sha(a.control_binding));save()
        run('runtime-readback',spec('runtime-readback-spec.json'))
        result['display_initial']=display(run('display-initial',spec('display-mmio-spec.json')))
        quiet=True;functional=run('functional',spec('functional-spec.json'))
        for name in ['H128_ID','H128_CONTROL']:assert re.search(r'(?m)^'+name+r'\n0x00000000$',functional),name
        batches=[]
        for label in ['nnue-a','nnue-b']:
            text=run(label,spec('nnue-spec.json'));values={}
            for phase in ['cold','warm']:
                found=re.findall(r'(?m)^NNUE_LATENCY phase='+phase+r' samples=(\d+) mean_us=(\d+)',text)
                assert len(found)==1 and int(found[0][0])==40
                values['nnue_'+phase]=dict(samples=40,mean_us=int(found[0][1]))
            for backend in ['legacy','resident']:
                found=re.findall(r'(?m)^MAC_RESIDENT_LATENCY backend='+backend+r' samples=(\d+) mean_us=(\d+)',text)
                assert len(found)==1 and int(found[0][0])==100
                values['dense_'+backend]=dict(samples=100,mean_us=int(found[0][1]))
            failures=re.findall(r'fallbacks=(\d+) mismatches=(\d+)',text)
            assert failures and all(x==('0','0') for x in failures)
            timer=read(out/(label+'.result.json'))['commands'][-1]
            assert 'sleep 2' in timer['command'] and 1.8<=timer['host_response_seconds']<=2.8,timer
            batches.append(values)
        for i in [1,2]:
            text=run('mixed-'+str(i),spec(f'mixed-{i:02d}-spec.json'))
            assert re.search(r'(?m)^PCM_TRANSPORT_PASS samples=96000 .*overflows=0(?: |$)',text)
            for role in ['resident','stageb','conv','audio']:assert re.search(r'(?m)^MIXED_WAIT role='+role+r' pid=\d+ code=0$',text),role
        result['display_after_mixed']=display(run('display-after-mixed',spec('display-mmio-spec.json')))
        gui=spec('gui-audio-spec.json');text=run('gui-search-audio',gui[:3])
        for count in [32000,96000]:assert re.search(r'(?m)^PCM_TRANSPORT_PASS samples='+str(count)+r' .*overflows=0(?: |$)',text)
        assert 'INJECT MOVE_PASS red=h2e2 black=b9c7' in text
        result['display_after_search']=display(run('display-after-search',spec('display-mmio-spec.json')))
        run('gui-normal-restored',gui[3:]);restored=True
        result['display_final']=display(run('display-final',spec('display-mmio-spec.json')))
        comparisons={}
        for name in batches[0]:
            count=sum(b[name]['samples'] for b in batches);mean=sum(b[name]['samples']*b[name]['mean_us'] for b in batches)/count;reference=control['latency'][name]['mean_us']
            comparisons[name]=dict(samples=count,mean_us=mean,control_mean_us=reference,change_percent=(mean/reference-1)*100,pass_nonregression=mean<=reference,batches=[b[name] for b in batches])
        result.update(comparisons=comparisons,model_nonregression_pass=all(v['pass_nonregression'] for v in comparisons.values()),gui_voice_restored=True)
        result['status']='GUI1080_FUNCTIONAL_MODEL_AUDIO_SCANOUT_PASS_HDMI_PENDING' if result['model_nonregression_pass'] else 'GUI1080_FUNCTIONAL_PASS_MODEL_PERFORMANCE_FAIL_HDMI_PENDING'
    except Exception as error:
        result.update(status='FAILED_BOARD_CHECKS_PRESERVED',error=repr(error));raise
    finally:
        if quiet and not restored:
            cleanup='''cd /tmp/voice-gui-display || exit 1
for role in gui-v3 voice; do
 test -f "$role.pid" || continue
 p=$(cat "$role.pid") || exit 1
 case "$p" in ''|*[!0-9]*) exit 1;; esac
 test "$p" -gt 1 || exit 1
 kill -0 "$p" 2>/dev/null || continue
 expected=/tmp/voice-gui-display/xiangqi-gui-display-v3
 test "$role" != voice || expected=/tmp/voice-gui-display/xqvoice-display
 test "$(readlink /proc/$p/exe)" = "$expected" || exit 1
done
for role in gui-v3 voice; do
 test -f "$role.pid" || continue
 p=$(cat "$role.pid") || exit 1
 kill -0 "$p" 2>/dev/null || continue
 kill "$p" || exit 1
 n=0
 while kill -0 "$p" 2>/dev/null; do sleep 1; n=$((n+1)); test "$n" -lt 15 || break; done
 ! kill -0 "$p" 2>/dev/null || exit 1
done
echo VERIFIED_FAILURE_CLEANUP_PASS'''
            try:
                run('failure-owned-cleanup',[dict(command=cleanup,timeout=45,markers=['VERIFIED_FAILURE_CLEANUP_PASS'])])
                run('failure-restore',spec('restore-normal-v2-spec.json'));result['gui_voice_restored_after_failure']=True
            except Exception as error:result['restore_error']=repr(error)
        result['completed_utc']=datetime.now(timezone.utc).isoformat();save();print(json.dumps(result),flush=True)

if __name__=='__main__':main()
