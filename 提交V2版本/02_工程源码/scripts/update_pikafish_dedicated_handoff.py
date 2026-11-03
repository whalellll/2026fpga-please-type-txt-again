"""Refresh only the dedicated-trial handoff block from existing evidence; no board access."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 kit=ROOT/'build/dedicated-sd-04';board=ROOT/'build/board-trial-dedicated-02'
 binding=read(kit/'trial-binding.json');runtime=read(ROOT/'build/dedicated-runtime-04/result.json')
 assert sha(kit/'manifest.json')==binding['manifest_sha256']
 assert runtime['pipeline_integration']['status']=='ALL_THREE_NNUE_PIPELINE_HOOKS_VERIFIED'
 program=read(board/'result.json');boot=read(board/'sdboot.result.json');summary=read(board/'summary.json')
 coremark=read(board/'coremark/result.json')
 begin='<!-- PIKAFISH_DEDICATED_PNR_20261024_BEGIN -->';end='<!-- PIKAFISH_DEDICATED_PNR_20261024_END -->'
 lines=[begin,'## Pikafish dedicated board trial (2026-10-24)','',
  'Updated UTC: '+datetime.now(timezone.utc).isoformat()+'. User authorizes SD write and this exact version board tests; explicitly NO formal delivery. No Flash or remote push.',
  'Source '+str(ROOT)+'. Hardware ee2e710; native G:/pfpnr4/run'+binding['run_id']+'. CPU75/SYS49.5/1080p30;44073LUT/32305FF/64APM/134DRM. Final STA FAIL CPU setup -0.181ns/TNS-0.358ns/2 endpoints; SYS setup+1.868ns, CPU hold+0.104ns, SYS hold+0.074ns. All native/failure inputs preserved.',
  'Current SD04: '+str(kit/'sd-root')+'; exact sbit '+binding['bitstream_sha256']+'. Manifest SHA256 '+binding['manifest_sha256']+'. Eight-file hashes and18 offline loader cases PASS; physical write/readback H:/fpga_archives/Pikafish_Dedicated_Trial_20261024/sd-backups/disk3-20261024-022340-231/write-result.json. Card returned confirmed; UART COM17 restored after reconnect.',
  'SD03 is superseded: initial full NNUE test failed because the build applied only the accumulator patch and omitted feature-transformer/architecture pipeline hooks; generic FC0 ioctl was rejected as designed. Original build/model-01 failure evidence retained. Corrected runtime04 applies/verifies all3 source hooks before compiling all4 programs; source-header hashes bound in pipeline-integration.json. Kernel03 and RTL unchanged.',
  'Earlier same-bitstream trial01: direct SD03 CRC/Linux/GUI startup PASS; independent conv/window/gather and timer checks PASS. Dedicated synthetic MLP driver test PASS: cold8801words/warm0, two file contexts, same-address model replacement, stale tags and removed-dense rejection. These do not establish official full-network speedup.',
  'Current trial02 program: '+program.get('status','pending')+'; SD04 boot: '+boot.get('status','pending')+'; CoreMark: '+coremark.get('status','pending')+'; summary: '+summary.get('status','pending')+'.',
  'Evidence: build/board-trial-dedicated-01 (preserved initial software failure and valid independent hardware tests), build/board-trial-dedicated-02 (current SD04), docs/Pikafish_Dedicated_PnR_20261024.md. Check live owners and actual card/board identity before resuming; never restart unrelated jobs. Next follows current trial receipts; no new PnR.',end]
 if summary:
  lines.insert(-1,'Completed measured NNUE mean CPU129.979/109.570ms -> dedicated18.753/17.758ms (cold/warm), speedup6.931/6.170; fixed-node search aggregate2.476x, all3 result/node/WDL parity. CPU search final diagnostic wrongly treats disabled mode as fallback, raw exit134 preserved and reviewed separately; no full CPU harness pass claim. GUI NEWGAME+MOVE26.82s, newgame7.207s/search14.434s despite requested movetime1000ms; application deadline remains open. Voice exact3clips, conv/gather,60s mixed960000audio samples0overflow, HDMI30.105Hz0underflow and user visual confirmation PASS. Services left running. No formal STA/delivery pass; report docs/Pikafish_Dedicated_Board_Trial_20261024.md.')
 block='\n'.join(lines)
 for p in [ROOT/'docs/CPU_Frequency_Handoff.md',ROOT.parent/'HANDOFF.md',ROOT.parent/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
  text=p.read_text(encoding='utf-8-sig');pattern=re.escape(begin)+r'[\s\S]*?'+re.escape(end)
  assert len(re.findall(pattern,text))==1,p
  p.write_text(re.sub(pattern,lambda _:block,text),encoding='utf-8')
 print('DEDICATED_HANDOFF_REFRESHED_NO_BOARD_ACCESS')
if __name__=='__main__':main()
