"""Exercise the actual resident CNN worker over XQW1; device arithmetic is mocked."""
from pathlib import Path
import argparse, hashlib, json, queue, subprocess, threading, time

ROOT=Path(__file__).resolve().parents[1]
def lin(p):
    s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--rv32',action='store_true')
    ap.add_argument('--distro',default='Ubuntu-22.04');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    model=ROOT/'linux/voice_ctc/balanced24.bin';case=out/'features.bin'
    case.write_bytes((7).to_bytes(4,'little')+bytes((i*37+11)&255 for i in range(7*40)))
    command=['wsl','-d',a.distro,'--',*(['qemu-riscv32'] if a.rv32 else []),
             lin(a.runtime),'--worker',lin(model),'mac','/dev/null']
    p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    messages=queue.Queue();transcript=[];errors=[]
    def read_stdout():
        while True:
            line=p.stdout.readline(4097)
            if not line:messages.put(None);return
            messages.put(line)
    def read_stderr():
        while True:
            chunk=p.stderr.read(1024)
            if not chunk:return
            errors.append(chunk)
    readers=[threading.Thread(target=read_stdout,daemon=True),threading.Thread(target=read_stderr,daemon=True)]
    for thread in readers:thread.start()
    def receive(prefix):
        until=time.monotonic()+30
        while True:
            line=messages.get(timeout=max(.01,until-time.monotonic()))
            assert line is not None,'worker EOF'
            assert len(line)<=4096 and line.endswith(b'\n'),'unbounded worker frame'
            transcript.append(line);text=line.decode('ascii').strip()
            assert text.startswith('XQW1 '),text
            if text.startswith(prefix):return text
            assert not text.startswith('XQW1 ERROR '),text
    def send(text):p.stdin.write(text.encode('ascii'));p.stdin.flush()
    def result(identifier,cancel=False):
        path=lin(case).encode().hex();send(f'XQW1 V {identifier} {path}\n'+(f'XQW1 C {identifier} -\n' if cancel else ''))
        line=receive(f'XQW1 RESULT {identifier} ');parts=line.split()
        values=dict(word.split('=',1) for word in parts[5:])
        assert int(parts[3])==(26 if cancel else 25) or (not cancel and int(parts[3])==0),line
        assert values['model_loads']==values['model_checks']==values['mac_opens']=='1'
        assert values['tail_valid']=='0' # Feature replay is never microphone endpoint evidence.
        assert int(values['jobs'])==0 if cancel else int(values['jobs'])>0
        assert receive(f'XQW1 IDLE {identifier}')==f'XQW1 IDLE {identifier}'
        return dict(code=int(parts[3]),jobs=int(values['jobs']),tail_valid=int(values['tail_valid']))
    results=[];status='FAILED_PRESERVED'
    try:
        receive('XQW1 READY ')
        results.append(result(1));results.append(result(2,True))
        send('XQW1 C 1 -\n') # A cancellation from an earlier generation is harmless.
        results.append(result(3));assert results[0]==results[2]
        send('XQW1 Q 0 -\n');receive('XQW1 BYE');p.stdin.close()
        assert p.wait(timeout=10)==0
        status='VOICE_RESIDENT_REAL_PROTOCOL_REUSE_CANCEL_AND_LATE_GENERATION_PASS_NOT_BOARD'
    finally:
        if p.poll() is None:p.kill();p.wait(timeout=10)
        for thread in readers:thread.join(timeout=2)
        (out/'worker.stdout').write_bytes(b''.join(transcript));(out/'worker.stderr').write_bytes(b''.join(errors))
        record=dict(status=status,rv32=a.rv32,actual_board=False,runtime_sha256=sha(a.runtime),
                    model_sha256=sha(model),results=results,stdout_sha256=sha(out/'worker.stdout'),
                    stderr_sha256=sha(out/'worker.stderr'),scope='Actual resident process; synthetic features and explicit device arithmetic mock')
        (out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':status,'rv32':a.rv32}),flush=True)
if __name__=='__main__':main()
