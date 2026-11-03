"""Read-only evidence refresh; updates only this candidate's handoff section."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
START='<!-- VOICE_NNUE_CPU75_IMPLEMENTATION_BEGIN -->'
END='<!-- VOICE_NNUE_CPU75_IMPLEMENTATION_END -->'
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--native',default='G:/fpga/v75q32p2')
 ap.add_argument('--phase',default='Q32 actual-source correctness/regression running; native map/route/STA and board pending')
 a=ap.parse_args();native=Path(a.native)
 evidence={}
 for directory in ['q32-validation-01','q32-validation-01/quarter','q32-validation-01/s16',
                   'q32-validation-01/official0','q32-validation-01/official1','q32-validation-01/soc']:
  p=ROOT/'build'/directory/'result.json'
  if p.exists():
   result=json.loads(p.read_text(encoding='utf-8-sig'))
   evidence[directory]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'status':result['status']}
 snap=native/'pds/build_snapshot.json';run=json.loads(snap.read_text())['run_id'] if snap.exists() else 'pending'
 state={'updated_utc':datetime.now(timezone.utc).isoformat(),'source':str(ROOT),'native':str(native),
        'native_run':run,'phase':a.phase,'cpu_hz':75000000,'sys_hz':49500000,'display':'1080p30 /74.25MHz',
        'evidence':evidence,'board':'NOT_RUN','speedup':'NOT_MEASURED','push':'NOT_DONE','delivery':'NOT_DONE'}
 state['branch']=subprocess.check_output(['git','rev-parse','--abbrev-ref','HEAD'],cwd=ROOT).decode().strip()
 state['dense_profile']=2;state['mac_int8_per_cycle']=32
 status_path=ROOT/'docs/validation/voice-nnue75-current.json';status_path.write_text(json.dumps(state,indent=2)+'\n')
 block=f'''{START}
## CPU75 voice / direct NNUE implementation (active)

- Updated UTC: {state['updated_utc']}. User requested implementation and board testing, including direct Pikafish stage links.
- Source: `{ROOT.as_posix()}`; branch `{state['branch']}`, parent54074f6. CPU75/SYS49.5/1080p30; Q32 dense MAC; H128 off. Native Q32/p1 synthesis verified dense40APM,47981LUT/35137FF/129DRM; this is not final routing or timing acceptance.
- Native: `{native.as_posix()}`; run `{run}`. Current phase: {a.phase}. Recheck live PID/command/start before resuming.
- Implemented StageA local cache -> exact feature transform -> FC0 -> dual activations -> FC1 -> FC2, sharing the existing PE. CPU keeps search, accumulator rollback copies, PSQT and final evaluation merge.
- Offline isolated Q32:130 differential cases/22 reset cuts,8394 S16 dot/square words,32 official positions/all16 buckets and real AXI StageA-to-score plus conv0/1 pass. Actual-source replays are build/q32-validation-01; read each status. Small dense160 exceeds the old half143; S16 max22168 under the declared Q32 bound22248. Old failed cycle gate is preserved, not reclassified as unchanged performance.
- Kernel/runtime/voice and SD04 files are byte-identical to parent54074f6. Original source worktree retains linux-voice-frozen-01, pipeline-runtime-02, voice-runtime-05 and sd-runtime-04 receipts. All18 loader tests passed for this unchanged eight-file set, now in this candidate linux/boot. No physical media access. Rootfs16314368 bytes; kernel Image and ABI unchanged.
- Runtime perspective0/1 hints preserve the other accumulator view; intermediate cache updates use legacy gather without evicting either view. Runtime-context06 verifies direct StageA calls need zero full-view reuploads. This is software evidence; actual board speedup is pending.
- Full Q32 regression is build/full-regression-q32-01.log with its actual child exit/hash receipt. Q32/p1 stopped before PnR: the frozen DI checker counted eight paired write decoders as additional data pads. The original FAIL receipt remains unchanged. The revised checker preserves all18 pad identities/1024 DI checks and proves2048 decoder truth cases plus1024 RAM WE connections. New frozen p2 is required; no checker replacement inside p1. Final routing/timing remain pending. Earlier voice proofs remain bound to unchanged sources in the original worktree.
- Preserve earlier r1/r2/r3/p1/p2 evidence and p3 routing interruption. P3 run9f216be573f34d68a82d414c440fd585 stopped with3808 unresolved at625, versus best2314 at228. All474 frozen inputs/logs retained and owner processes exited; no final STA. See original build/p3-congestion-stop-01. No failed image programmed.
- No new board measurements, speedup, acceptance, remote push or formal delivery. Original300ms VAD endpoint remains; natural speech-end10ms is not achieved by these offline tests.
- Evidence/status: `performance_soc_voice_nnue75_q32_20261023/docs/validation/voice-nnue75-current.json`; implementation: `performance_soc_voice_nnue75_q32_20261023/docs/Voice_NNUE75_Q32_20261023.md`. User requests notification after routing/final timing before connecting the board.
{END}'''
 for p in [ROOT.parent/'HANDOFF.md',ROOT.parent/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
  text=p.read_bytes().decode('utf-8');eol='\r\n' if '\r\n' in text else '\n'
  if START in text:
   left,right=text.split(START,1);_,right=right.split(END,1);text=left+block.replace('\n',eol)+right
  else:text=block.replace('\n',eol)+eol+text
  p.write_bytes(text.encode('utf-8'))
 print(json.dumps({'status':'VOICE_NNUE75_HANDOFF_UPDATED_NO_HARDWARE_ACTION','run':run,'evidence':len(evidence)}))
if __name__=='__main__':main()
