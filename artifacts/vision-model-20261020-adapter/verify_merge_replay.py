"""Current-profile CLI/peer and native RGB565 replay on an allowlisted game-3 frame."""
import hashlib,json,subprocess,sys,zlib,os
from pathlib import Path
import cv2,numpy as np
HERE=Path(__file__).resolve().parent;R=HERE.parents[1];B=R/'build/picture-merge-20261023';E=R/'docs/validation/picture-merge-20261023'
def main():
 out=B/'replay-r02';out.mkdir(exist_ok=False)
 inputs=json.loads((R/'build/picture-r11-20261022/adapter-inputs/game3-inputs.json').read_text());item=inputs['frames'][0]
 assert inputs['game']==3 and 152<=item['index']<=234
 source=R/item['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256']
 image=cv2.imread(str(source));assert image.shape==(720,1280,3)
 raw=(((image[:,:,2].astype(np.uint16)>>3)<<11)|((image[:,:,1].astype(np.uint16)>>2)<<5)|(image[:,:,0].astype(np.uint16)>>3)).astype('<u2').tobytes()
 path=out/'frame.rgb565';path.write_bytes(raw);crc=zlib.crc32(raw)
 def run(cmd,name,allowed=(0,)):
  env=dict(os.environ,OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
  p=subprocess.run(cmd,cwd=R,capture_output=True,timeout=180,env=env);(out/(name+'.log')).write_bytes(p.stdout+p.stderr);assert p.returncode in allowed,(name,p.stderr[-1000:]);return p
 for backend in ('fp32','quantized-mac'):
  target=out/(backend+'.json')
  run([sys.executable,'-B',str(HERE/'recognize_working.py'),'--backend',backend,'--input',str(path),'--width','1280','--height','720','--output',str(target)],backend)
  result=json.loads(target.read_text());assert result['working_profile']=='working-r14' and result['selected_classifier']=='v3d-QAT'
  assert result['models']['classifier']['sha256'].startswith('d1476f80') and not result['production_ready']
  if backend=='quantized-mac':assert result['quantized_gate'] is False and result['integer_oracle']=='r08-exact-int64'
  else:assert 'integer_oracle' not in result
 request=out/'request';request.write_text(f'XQ_MODEL_REQUEST_V1 1 1 {crc:08x} pc-quantized-mac\n')
 packet=out/'native.packet';run([str(B/'native-host-final/xq-native-worker'),'--models',str(B/'native-models'),'--cpu-reference','--request',str(request),'--input',str(path),'--output',str(packet)],'native',(0,1))
 header=packet.read_text().splitlines()[0].split();native_usable=int(header[5])==0
 reference=json.loads((out/'quantized-mac.json').read_text());assert native_usable==reference['can_use_as_candidate']
 if native_usable:assert packet.read_text().splitlines()[1].split()[0]==reference['board_placement_fen']
 for backend,okay in [('pc-fp32',True),('pc-quantized-mac',False)]:
  req=out/(backend+'.request');req.write_text(f'XQ_MODEL_REQUEST_V1 1 1 {crc:08x} {backend}\n');target=out/(backend+'.packet')
  run([sys.executable,'-B',str(HERE/'recognize_peer.py'),'--request',str(req),'--input',str(path),'--output',str(target),'--result-json',str(out/(backend+'.result.json'))],backend,(0,) if okay else (1,2))
  assert target.exists()==okay
 report=dict(status='PASS',scope='one authorized training game3 RGB565 replay; engineering conformance only',current_default='working-r14 FP32',quantized_gate=False,native_CPU_REFERENCE_vs_exact_strict_usable_equal=True,native_status=int(header[5]),peer_default_FP32_and_wrong_backend_rejection_pass=True,game2_images_opened=0,game2_inference_runs=0,hardware_used=False,production_ready=False)
 (E/'entrypoints-and-replay.json').write_text(json.dumps(report,indent=2)+'\n');print('CURRENT_PROFILE_AND_RGB565_REPLAY_PASS')
if __name__=='__main__':main()
