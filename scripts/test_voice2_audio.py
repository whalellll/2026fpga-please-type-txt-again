"""Complete synthetic WAV frontend/CNN/CTC parity and strict failure handling."""
from pathlib import Path
import argparse,hashlib,json,math,random,struct,subprocess,wave
from test_voice2_model import command,lin
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 u=R/'linux/voice2/upstream';model=R/'linux/voice2/balanced24.bin'
 src=[u/n for n in ['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_decode.c','xqvoice_capture.c','xqvoice_profile.c']]+[R/'linux/voice2/voice_small_backend.c',R/'sim/voice2_device_mock.c']
 hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in src}
 command("gcc -std=gnu11 -O2 -Wall -Wextra -Werror -DXQV_HOP_SAMPLES=320u -DXQV_CTC_BEAM=8 -pthread "+' '.join("'"+lin(p)+"'" for p in src)+" -Wl,--wrap=open,--wrap=close,--wrap=ioctl -o '"+lin(o/'runtime')+"'",o,'build')
 cases=[];rng=random.Random(440)
 for n,samples in enumerate([6400,32000]):
  pcm=[int(12000*math.sin(2*math.pi*440*i/16000))+rng.randrange(-1000,1001) for i in range(samples)]
  wav=o/f'{n}.wav'
  with wave.open(str(wav),'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(struct.pack('<'+'h'*samples,*pcm))
  for backend in ['cpu','mac','mac-verify']:
   command(f"set +e; '{lin(o/'runtime')}' '{lin(model)}' '{lin(wav)}' '{lin(o/(str(n)+'-'+backend+'.trace'))}' {backend} wav; rc=$?; test $rc = 0 -o $rc = 25",o,f'{n}-{backend}')
  data=(o/f'{n}-cpu.trace').read_bytes()
  assert all((o/f'{n}-{b}.trace').read_bytes()==data for b in ['mac','mac-verify'])
  cases.append({'samples':samples,'trace_sha256':hashlib.sha256(data).hexdigest()})
 for env in ['VOICE2_MODEL_FAIL','VOICE2_TILE_TIMEOUT']:
  command(f"set +e; {env}=1 '{lin(o/'runtime')}' '{lin(model)}' '{lin(o/'0.wav')}' /dev/null mac wav; rc=$?; test $rc = 22",o,env)
 assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in src}
 result={'status':'VOICE2_WAV_MODEL_PARITY_AND_NO_FALLBACK_PASS_NOT_BOARD','cases':cases,'rejected_failures':['model I/O','tile timeout'],'inputs_sha256':hashes,'scope':'Synthetic WAV CPU frontend/CTC plus device arithmetic mock; not real speech accuracy or board latency.'}
 (o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'cases':len(cases)}))
if __name__=='__main__':main()
