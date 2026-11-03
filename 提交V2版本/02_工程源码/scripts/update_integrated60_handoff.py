"""Update only the integrated60 section, preserving independent sessions."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
R=Path(__file__).resolve().parents[1];W=R.parent
ap=argparse.ArgumentParser();ap.add_argument('--phase',required=True);ap.add_argument('--native-root',default='G:/i60pnr4');a=ap.parse_args()
checks={}
for p in (R/'build').glob('integrated-*/result.json'):
 d=json.loads(p.read_text(encoding='utf-8-sig'));checks[p.parent.name]=dict(status=d.get('status'),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
for p in (R/'build').glob('voice-stream-*/result.json'):
 d=json.loads(p.read_text(encoding='utf-8-sig'));checks[p.parent.name]=dict(status=d.get('status'),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
for name,relative in [('kernel02','integrated-kernel-02/build.json'),('native-resources','integrated-resources-01.json'),('physical03','integrated-physical-03.json'),('independent-scope-review','integrated-reviewed-scope-03.json')]:
 p=R/'build'/relative
 if p.exists():checks[name]=dict(status=json.loads(p.read_text(encoding='utf-8-sig'))['status'],sha256=hashlib.sha256(p.read_bytes()).hexdigest())
state=dict(updated_utc=datetime.now(timezone.utc).isoformat(),phase=a.phase,source_root=R.as_posix(),source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),cpu_hz=60000000,sys_hz=49500000,display='1080p30',checks=checks,native_root=a.native_root,failed_native_roots=['G:/i60pnr1','G:/i60pnr2'],board=False,push=False,delivery=False)
native=Path(state['native_root']);launch=native/'physical-launch.json';snapshot=native/'pds/build_snapshot.json'
if launch.exists():
 d=json.loads(launch.read_text(encoding='utf-8-sig'));state['physical']={k:d.get(k) for k in ['status','owner_powershell_pid','started_utc','source_commit','run_id','pnr_started','pnr_complete','error']}
 state['physical']['receipt_sha256']=hashlib.sha256(launch.read_bytes()).hexdigest()
if snapshot.exists():
 d=json.loads(snapshot.read_text(encoding='utf-8-sig'));state['native_snapshot']=dict(run_id=d['run_id'],sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),started_utc=d['started_utc'])
history=native/'pnr-history.json'
if history.exists():
 d=json.loads(history.read_text(encoding='utf-8-sig'));run=state.get('native_snapshot',{}).get('run_id')
 state['observed_pnr_history']=[row for row in d.get('attempts',[]) if row.get('run_id')==run]
artifact=R/'artifacts/integrated60_linefix_20261024/manifest.json'
if not artifact.exists():artifact=R/'artifacts/integrated60_linefix_trial_20261024/manifest.json'
if not artifact.exists():artifact=R/'artifacts/integrated60_20261024/manifest.json'
if artifact.exists():
 d=json.loads(artifact.read_text(encoding='utf-8-sig'))
 state['candidate_artifact']=dict(status=d['status'],manifest=artifact.relative_to(R).as_posix(),sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
sd_revision='05' if (R/'build/integrated-sd-kit-05/manifest.json').exists() else '04'
sd_relative=f'build/integrated-sd-kit-{sd_revision}/manifest.json'
stream_writes=sorted((R/'build/integrated-stream-sd-write-01').glob('disk*/write-result.json'))
if stream_writes:
 sd_relative='build/integrated-stream-sd-kit-01/manifest.json'
 p=stream_writes[-1];d=json.loads(p.read_text(encoding='utf-8-sig'))
 state['stream_sd_write']=dict(status=d['Status'],path=p.relative_to(R).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),manifest_sha256=d['ManifestSHA256'].lower(),board=False)
board_revision='03' if (R/'build/integrated-board-program-03/result.json').exists() else '02'
for name,relative in [('sd_kit',sd_relative),('original_model_assets','build/integrated-real-timing-assets-02/manifest.json'),('board_trial',f'build/integrated-board-program-{board_revision}/result.json'),('sd_boot',f'build/integrated-board-program-{board_revision}/sdboot.result.json'),('stream_software','docs/validation/voice2-stream-cpu60-offline-20261024/result.json'),('joint_preparation','build/joint60-preparation-01/result.json')]:
 p=R/relative
 if p.exists():
  d=json.loads(p.read_text(encoding='utf-8-sig'))
  state[name]=dict(status=d.get('status'),path=relative,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
joint=R/'docs/validation/integrated60-joint-board-20261024/summary.json'
if joint.exists():
 d=json.loads(joint.read_text(encoding='utf-8-sig'))
 state['joint_board']=dict(status=d['status'],path=joint.relative_to(R).as_posix(),sha256=hashlib.sha256(joint.read_bytes()).hexdigest())
 state['board_functional_tests_pass']=d['status']=='JOINT60_BOARD_FUNCTIONAL_PASS_PERFORMANCE_MEASURED_STA_FAILED_NOT_RELEASE'
published=R/'docs/validation/integrated60-temporary-branch-push-20261024/receipt.json'
if published.exists():
 d=json.loads(published.read_text(encoding='utf-8-sig'))
 assert d['status']=='TEMPORARY_BRANCH_IMPLEMENTATION_COMMIT_AND_BOUND_ARTIFACT_HASHES_READBACK_PASS'
 state['push']=True
 state['temporary_branch_push']=dict(branch=d['branch'],verified_implementation_commit=d['remote_commit'],receipt=published.relative_to(R).as_posix(),sha256=hashlib.sha256(published.read_bytes()).hexdigest(),main_merged=False)
(R/'build/integrated60-status.json').write_text(json.dumps(state,indent=2)+'\n')
begin='<!-- INTEGRATED60_20261024_BEGIN -->';end='<!-- INTEGRATED60_20261024_END -->'
block=f'''{begin}
## Integrated voice2 / Picture_new / dedicated Pikafish CPU60 candidate

Updated UTC {state['updated_utc']}. CPU60/SYS49.5/1080p30. Latest Oct24 steering authorizes SD update and board timing, then requests existing model files instead of arbitrary weights. Existing original board192/detector640/classifier32 graphs recovered from SD PN02FS.BIN/native-models.tar.gz; byte hashes match its manifest, all80 quantized layers retained. Voice uses genuine balanced24. SD eight files written/read back; user confirms card/power/UART/JTAG reconnected. Volatile CRAM only, no Flash or formal release.

Source `{R.as_posix()}`, branch feature/integrated-voice-vision-cpu60-20261024, HEAD at refresh {state['source_head']}. Parents: dedicated792008d, voice7bec718, vision376b05f. Preserve official StageA/direct MLP/single-bucket cache; legacy H128/dense absent. Voice uses balanced24 four-product CNN, CPU FFT/requant/CTC. Vision P4xOC8 DMA supports640 dimensions; new ioctl/private shadow/common MAC owner and draining timeout. Picture_new retains original ties-even S16/65536 LUT and CPU float graph operators; raw I32 on V321, whole-layer when the1MiB scratch fits, hardware matrix tiling otherwise. Original model weights now recovered; accuracy and full-frame FEN have not passed. Initial candidate manifest remains immutable and describes its older interface-only stage.

CPU exact60MHz: existing27MHz reference /1080MHz VCO /CLKOUT0 divider18 (encoded36). STA target16.650ns (stricter than16.666667ns), SYS20.202ns, CDC15.85ns. CPU source unchanged. Boot ROM rebuilt; kernel/runtime/firmware bindings tracked separately.

Current phase: {a.phase}
Streamed-software SD write: {json.dumps(state.get('stream_sd_write',{}))}. Latest user order is SD first, then routing inspection. Original SD write receipts are immutable; the waiting automatic writer was stopped before any action. The board trial receipt records an explicit compatible-payload binding when using the original CPU60 software manifest with native4. Full hardware acceptance remains separate from this functional trial.
Candidate artifact: {json.dumps(state.get('candidate_artifact',{}))}
Remote temporary branch: {json.dumps(state.get('temporary_branch_push',{}))}. User explicitly authorizes this version's temporary branch after tests complete, including disclosed STA failures and missed performance goals; main merge/formal delivery are separate.
SD/model/board receipts: {json.dumps({k:state[k] for k in ['sd_kit','original_model_assets','board_trial','sd_boot','joint_board'] if k in state})}. Board functional tests passed: {state.get('board_functional_tests_pass',False)}. CRAM programming, physical SD boot, functional/performance tests and full release acceptance are separate; actual native STA failures remain failures.
Checks: {json.dumps(checks)}
Evidence: `build/integrated60-status.json`; native target `{state['native_root']}` (inspect live owner before resume). Physical launch: {json.dumps(state.get('physical',{}))}; snapshot: {json.dumps(state.get('native_snapshot',{}))}. Observed PnR history: {json.dumps(state.get('observed_pnr_history',[]))}; launcher flags can remain at their initial values until the final receipt is written. G:/i60pnr1 is retained as FAILED before PnR: unresolved PMA page export; P2 passed CPU/PLL/shift/ICache but incorrectly requested hold pads in the retired legacy conv. Current flow selects actual vision profile and proves32PE/cache plus legacy DMA absence; legacy profiles retain their original pad check. Remaining SD ownership/storage and CDC gates checked on P2 evidence. The new checker proves actual PMA producer/consumer and parent wiring, all1024 cofactors; CPU oracle is unchanged; each current candidate hardware input must match its own frozen snapshot (native4 includes the32-byte vision DMA split, implementation3fab80f). Full synthesis/PnR/final STA/sbit and software states are separate. Old CPU75 dedicated and Q32 board results do not validate this candidate. Preserve all failures and incomplete inputs. Temporary branch push follows the latest explicit user authorization and receipt above; no main merge or formal delivery package.
{end}'''
for p in [W/'HANDOFF.md',W/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md',R/'docs/CPU_Frequency_Handoff.md']:
 s=p.read_bytes().decode('utf-8');eol='\r\n' if '\r\n' in s else '\n';replacement=block.replace('\n',eol)
 if begin in s:
  left,t=s.split(begin,1);_,right=t.split(end,1);s=left+replacement+right
 else:
  i=s.find('\n');s=s[:i+1]+eol+replacement+eol+s[i+1:]
 p.write_bytes(s.encode())
for p in [R/'scripts/project_directory_catalog.json',W/'performance_soc_voice_hw/scripts/project_directory_catalog.json']:
 d=json.loads(p.read_text(encoding='utf-8-sig'))
 for pattern,role in [(R.name,'CPU60 voice2/Picture_new/dedicated Pikafish integration candidate'),('i60pnr*','Frozen native CPU60 integrated synthesis/PnR and all-corner evidence')]:
  if not any(pattern in row['patterns'] for row in d['workspace_groups']):
   d['workspace_groups'].insert(0,dict(patterns=[pattern],role=role,policy='Incomplete candidate: preserve inputs/native evidence; no board/production/delivery pass inferred'))
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=W/'PROJECT_INDEX.md';s=p.read_text(encoding='utf-8');link=R.name+'/docs/Integrated60_20261024.md'
if link not in s:
 i=s.find('\n');s=s[:i+1]+'\n- [CPU60 voice2 / Picture_new / dedicated Pikafish integration]('+link+') (candidate; original models recovered, streamed voice and image fix awaiting joint board acceptance).\n'+s[i+1:];p.write_bytes(s.encode())
print('INTEGRATED60_HANDOFF_UPDATED',a.phase)
