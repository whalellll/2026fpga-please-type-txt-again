"""Compare all5 model traces for batch vs paced-stream feature acquisition."""
from pathlib import Path
import argparse,hashlib,json,re,struct,wave,math
from test_voice2_model import command,lin
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
o=a.output.resolve();o.mkdir(parents=True,exist_ok=False);u=R/'linux/voice2/upstream'
src=[u/n for n in ['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c','xqvoice_capture.c','xqvoice_profile.c']]+[R/'linux/voice2/voice_small_backend.c',R/'sim/voice2_device_mock.c']
bound=src+list(u.glob('*.h'))+list(u.glob('*.inc'))+[R/'linux/voice2/balanced24.bin']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
command('gcc -std=gnu11 -O2 -fwrapv -Wall -Wextra -Werror -pthread -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 '+
        ' '.join("'"+lin(p)+"'" for p in src)+" -Wl,--wrap=open,--wrap=close,--wrap=ioctl -o '"+lin(o/'runtime')+"'",o,'build')
cases=[]
for ms in [500,2000]:
    wav=o/f'{ms}.wav';samples=ms*16
    with wave.open(str(wav),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'))
        f.writeframes(struct.pack('<'+'h'*samples,*[int(12000*math.sin(i*2*math.pi*440/16000)) for i in range(samples)]))
    traces=[];feature_crcs=set()
    for backend in ['cpu','mac','mac-verify']:
        for mode in ['wav','wav-batch','wav-stream']:
            name=f'{ms}-{backend}-{mode}';trace=o/(name+'.trace')
            command(f"set +e; '{lin(o/'runtime')}' '{lin(R/'linux/voice2/balanced24.bin')}' '{lin(wav)}' '{lin(trace)}' {backend} {mode}; rc=$?; test $rc = 0 -o $rc = 25",o,name)
            traces.append(trace.read_bytes())
            log=(o/(name+'.log')).read_text(errors='replace')
            if mode!='wav':
                m=re.search(r'VOICE_STREAM_TIMING (.*)',log);assert m,log
                fields=dict(re.findall(r'(\w+)=([^\s]+)',m[1]))
                assert fields['source']=='wav-replay' and fields['paced']=='1'
                assert fields['streamed']==str(int(mode=='wav-stream'))
                feature_crcs.add(fields['feature_crc'])
                assert int(fields['endpoint_to_result_us'])>=int(fields['feature_tail_us'])
    assert traces[0] and all(t==traces[0] for t in traces) and len(feature_crcs)==1
    cases.append(dict(audio_ms=ms,trace_sha256=hashlib.sha256(traces[0]).hexdigest(),feature_crc=feature_crcs.pop()))
command(f"set +e; VOICE2_NO_CAPABILITY=1 '{lin(o/'runtime')}' '{lin(R/'linux/voice2/balanced24.bin')}' '{lin(wav)}' /dev/null mac wav-stream; test $? = 6",o,'strict-no-device')
assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
result=dict(status='VOICE2_STREAM_BATCH_ALL5_LAYERS_INTEGER_PARITY_STRICT_BACKEND_PASS_NOT_BOARD',cases=cases,inputs_sha256=hashes,scope='Host device arithmetic mock and actual paced feature threads; no board/real-speech latency claim.')
(o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
