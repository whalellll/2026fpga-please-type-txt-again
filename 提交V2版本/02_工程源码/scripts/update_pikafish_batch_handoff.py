"""Refresh this candidate's bounded handoff block; read-only to build/board."""
from pathlib import Path
from datetime import datetime,timezone
import json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
def main():
 status=read(ROOT/'build/batch60-status.json');clock=read(ROOT/'config/clocks.json')
 begin='<!-- PIKAFISH_BATCH60_20261024_BEGIN -->';end='<!-- PIKAFISH_BATCH60_20261024_END -->'
 branch=subprocess.check_output(['git','-C',str(ROOT),'branch','--show-current'],text=True).strip()
 block='\n'.join([begin,'## Pikafish batch evaluation / CPU60 (2026-10-24)','',
  'User authorizes a separate branch implementing combined StageA/local accumulators/NNUE and synthesis/place/route at exact CPU60. Source '+str(ROOT)+'; branch '+branch+'; parent792008d. Independent integrated60 merge is untouched.',
  'Current UTC '+datetime.now(timezone.utc).isoformat()+'; status '+status.get('status','IMPLEMENTING_NOT_SYNTHESIZED_NOT_ROUTED_NOT_BOARD')+'. CPU'+str(clock['cpu_hz'])+'Hz, SYS49500000Hz,1080p30. Existing mode4 PLL1080MHz/18,encoded divisor36; FDC16.650ns/SYS20.202ns. CPU/CoreTop unchanged; new firmware/DTS binding required.',
  'Up to8 dependent StageA updates,16KiB local SRAM and optional exact MLP in one transaction; rollback snapshots exported at batch completion. CPU feature generation and PSQT remain; persistent cross-evaluation hardware-only rollback is not claimed. Keep model ownership, per-fd snapshots, descriptor checks and drain-before-reuse.',
  'Native final focus '+json.dumps(status.get('physical_focus',{}),separators=(',',':'))+'; scope '+json.dumps(status.get('timing_scope',{}),separators=(',',':'))+'. Bitstream '+json.dumps(status.get('bitstream',{}),separators=(',',':'))+'. P2 run15fbc4bd/tool freeze829d915, implementation763ddd8; current own physical owner '+str(status.get('physical_owner_pid'))+', exit '+str(status.get('physical_exit_code'))+'. Router200ps auxiliary hold target has unmet margins but final actual hold slack is positive. Baseline187 external I/O gaps remain disclosed. Independent integrated VISION32 ABI collides on capabilitybit10/ioctl0x0a; reconcile before merging and keep paired kernels/runtimes.',
  'Latest SD instruction: prepare files only; DO NOT WRITE PHYSICAL SD. Offline SD preparation '+json.dumps(status.get('sd_preparation',{}),separators=(',',':'))+'. See docs/Pikafish_Batch_CPU60_SD_Preparation_20261024.md. No media/board/Flash action authorized by this preparation request.',
  'Evidence build/batch60-*/result.json; native preflight G:/pfb60s1, current physical '+status.get('native_physical','G:/pfb60p2')+' (inspect receipts/live owner before action). P1 ce2ba46f failed before placement because old CPU checker did not traverse native PMA page export; frozen failure retained. New checker proves producer, hierarchy,1024 consumer cases and unchanged original CPU oracle; five native fault mutations rejected. Pixel scope precision fix tested with negative STA and synthetic mutation fixtures. Report docs/Pikafish_Batch_CPU60_20261024.md. Prior CPU75 STA-0.181ns and SD04 board results remain separate. No board,SD,Flash,push or delivery for this task.',end])
 for p in [ROOT/'docs/CPU_Frequency_Handoff.md',ROOT.parent/'HANDOFF.md',ROOT.parent/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
  s=p.read_text(encoding='utf-8-sig');pattern=re.escape(begin)+r'[\s\S]*?'+re.escape(end)
  matches=re.findall(pattern,s);assert len(matches)<=1
  s=re.sub(pattern,lambda _:block,s) if matches else s.split('\n',1)[0]+'\n\n'+block+'\n'+s.split('\n',1)[1]
  p.write_text(s,encoding='utf-8')
 print('PIKAFISH_BATCH60_HANDOFF_REFRESHED_NO_BOARD_ACCESS')
if __name__=='__main__':main()
