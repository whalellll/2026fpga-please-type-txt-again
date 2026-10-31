"""Real geometry mid-filter cancel -> release9/IDLE -> new complete request.

Real frozen graph and geometry, independent mocked device/drain. Explicitly
authorized saved inputs stay private. Not a board/FPGA or latency acceptance.
"""
import argparse,hashlib,json,os,select,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['output','models','frame','request','reference-result']:ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--native',action='store_true')
    ap.add_argument('--geometry-fused',action='store_true')
    a=ap.parse_args()
    if os.name=='nt':
        from picture_workspace import workspace_path,wsl_path
        assert a.output.absolute().is_relative_to(ROOT/'build');workspace_path(a.output)
        raw=a.output.absolute().as_posix();out='/mnt/'+raw[0].lower()+raw[2:]
        args=['wsl.exe','-d','Ubuntu-22.04','--','python3',wsl_path(Path(__file__)),'--native','--output',out]
        if a.geometry_fused:args+=['--geometry-fused']
        for name in ['models','frame','request','reference_result']:args+=['--'+name.replace('_','-'),wsl_path(getattr(a,name))]
        r=subprocess.run(args,timeout=240);assert not r.returncode;return
    assert a.native and a.output.absolute().is_relative_to(ROOT/'build')
    out=a.output;assert not out.exists();out.mkdir(parents=True)
    sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
    inputs={q:sha(q) for q in [a.frame,a.request,a.reference_result]}
    assert a.frame.stat().st_size==1843200
    build=(ROOT/'linux/picture_new/build_native_coach.sh').read_text()
    needle='"$coach/coach_driver_guard.c"';assert build.count(needle)==1
    (out/'guard-stub.c').write_text('int xqcoach_driver_quiescent(void){return 1;}\n')
    build=build.replace(needle,'"'+str(out/'guard-stub.c')+'" "$coach/test_e42_model_mock.c" "$coach/test_geometry_cancel_notify.c"')
    needle='"$cc" $flags -DXQ_NATIVE_VISION32';assert build.count(needle)==1
    build=build.replace(needle,'"$cc" $flags -include "$coach/test_geometry_cancel_notify.h" -DXQ_NATIVE_VISION32')
    needle='-Wl,--wrap=ioctl ';assert build.count(needle)==1
    build=build.replace(needle,'-Wl,--wrap=ioctl,--wrap=open,--wrap=close,--wrap=mmap,--wrap=munmap ')
    (out/'build.sh').write_text(build)
    flags=['XQ_HWC_DETECTOR','XQ_HWC_TAIL_COLUMNS','XQ_HWC_CONCAT_VIEW','XQ_GRID_RECOVERY','XQ_GRID_PLAN_FAST','XQ_GRID_MODEL_GUARD',
        'XQ_GEOMETRY_CANCEL','XQ_GEOMETRY_FAST','XQ_GEOMETRY_ARITH','XQ_GEOMETRY_COMPACT',
        'XQ_GEOMETRY_SELECTIVE','XQ_GEOMETRY_SEED_BOUND','XQ_FAST_FP32_BILINEAR','XQ_HWC_WORD_INPUT','XQ_HWC_RGB8_DIRECT','XQ_BOARD_CORNER_TABLE']
    if a.geometry_fused:flags+=['XQ_GEOMETRY_FUSED']
    with (out/'build.log').open('xb') as f:
        r=subprocess.run(['env',*[q+'=1' for q in flags],'sh',str(out/'build.sh'),str(ROOT),str(out/'worker'),str(a.models),'host'],stdout=f,stderr=subprocess.STDOUT,timeout=120)
    assert not r.returncode,'build failed; receipt retained'
    service=out/'service';service.mkdir();(service/'frame.rgb565').write_bytes(a.frame.read_bytes())
    request=service/'request.txt';packet=service/'result.txt'
    fields=a.request.read_text().split();assert len(fields)==5
    env=dict(os.environ,XQGC_TEST_REQUEST=str(request))
    proc=subprocess.Popen([str(out/'worker/xq-coach-worker'),'--driver','--models',str(a.models),'--serve',str(service)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
    os.set_blocking(proc.stdout.fileno(),False);raw=bytearray();pending=b'';lines=[]
    def read():
        nonlocal pending
        if select.select([proc.stdout],[],[],.05)[0]:
            data=os.read(proc.stdout.fileno(),8192)
            if data:raw.extend(data);pending+=data
            assert len(raw)<131072,'bounded transcript'
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1);lines.append(line)
    def wait_line(prefix,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            while lines:
                line=lines.pop(0)
                if line.startswith(prefix):return
            assert proc.poll() is None,'worker ended prematurely';read()
        raise AssertionError('deadline waiting '+repr(prefix))
    def put(token):
        fresh=fields.copy();fresh[1]=str(token)
        (service/'request.tmp').write_text(' '.join(fresh)+'\n');os.replace(service/'request.tmp',request)
    result=dict(status='FAILED_PRESERVED',hardware_used=False,device_and_drain_mocked=True,
        geometry_fused=a.geometry_fused)
    try:
        wait_line(b'XQ_COACH_IDLE');put(7101)
        wait_line(b'GEOMETRY_CANCEL_TEST_REAL_PREFIX_STARTED');request.unlink()
        wait_line(b'XQ_COACH_IDLE');cancelled=packet.read_bytes().splitlines()[0].split()
        assert cancelled[1]==b'7101' and cancelled[5:8]==[b'9',b'0',b'00000000']
        put(7102);end=time.monotonic()+60;ordinary=None
        while time.monotonic()<end:
            read()
            if packet.exists():
                data=packet.read_bytes();header=data.splitlines()[0].split()
                if header[1]==b'7102' and header[5]==b'0':ordinary=data;break
            assert proc.poll() is None
        assert ordinary,'new generation did not finish'
        reference=a.reference_result.read_bytes();header,body=reference.split(b'\n',1)
        parts=header.split();parts[1]=b'7102';assert ordinary==b' '.join(parts)+b'\n'+body
        request.unlink();wait_line(b'XQ_COACH_IDLE');released=packet.read_bytes().splitlines()[0].split()
        assert released[1]==b'7102' and released[5]==b'9'
        proc.send_signal(signal.SIGTERM);proc.wait(timeout=10);assert proc.returncode==0
        assert all(sha(q)==h for q,h in inputs.items())
        result.update(status='REAL_GEOMETRY_MID_PREFIX_CANCEL_RELEASE9_IDLE_NEW_GENERATION_FULL_PACKET_PASS_NOT_BOARD',
            real_frozen_graph_and_geometry=True,mid_filter_request_removal=True,no_stale_ordinary_result=True,
            same_process_next_generation_exact_reference_packet=True,normal_term_exit=True,inputs_unchanged=True)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        while select.select([proc.stdout],[],[],0)[0]:
            data=os.read(proc.stdout.fileno(),8192)
            if not data:break
            raw.extend(data)
        (out/'worker.log').write_bytes(raw)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],flush=True)
if __name__=='__main__':main()
