"""Refresh delivery progress from local evidence; never access devices."""
from pathlib import Path
import hashlib,json,re

def main():
    project=Path(__file__).resolve().parents[1];workspace=project.parent
    run=project/'build/main70-delivery-20261027-01'
    state=json.loads((run/'status.json').read_text(encoding='utf-8-sig'))
    pair=run/'coremark-abab-02/result.json'
    if not pair.is_file():pair=run/'coremark-abab/result.json'
    cm=json.loads(pair.read_text()) if pair.is_file() else {}
    rows=['<!-- MAIN70_DELIVERY_20261027_BEGIN -->','## CPU70 formal-delivery workflow in progress (2026-10-27)',
        f"Live status `{run/'status.json'}`: `{state['status']}`. Delivery is incomplete. This block supersedes earlier historical progress blocks.",
        'LATEST: User confirmed voice reply/playback/restart AND camera/recommendation/playback/Esc normal. Exact replies are user-physical-02.json. Fixed source8f4de1c7, GUI ELF a0de66f686d26608065fe9680ea028d6003a5ce279b8945fe87dd2dc8ca17b98 runs at /tmp/main70-gui-restart. Engine lacked PIKAFISH_EMBEDDED_MODEL and PIKAFISH_STAGEB_PACK; both now explicit. Safe restart added and host/RV32/renderer/pointer/Esc tests PASS; prior GUI failures preserved. Older GUI paragraphs below are historical.',
        'LATEST: linux-coremark-02 valid30000ms and GUI restore PASS. Complete regular-worktree regression at G:/fpga/m70r passed SOC_ALL_TESTS_PASS, logSHA c5e824c11261ea46a098c4504a76a9d9ed652f6839cd676ce589e59cd1118ec1. New kit04 SD18 PASS; m70d/linux/boot now equals kit04, original replacements backed up in delivery work. Kernel inputs60MHz config/DTS frozen separately; hardware513/42/47 unchanged.',
        'LATEST: G:/fpga/m70d/MAIN70_RELEASE.json binds curated docs/validation/main70-release-20261027 and artifacts/main70_20261027. Prepublication-check02 PASS (strict native+program-transcript+CRC+runtime/models+real SD boot+physical+GUI source+full regression). Check01 failed only a hash search across terminal line wraps; retained failed receipt; fresh current-process GUI readback binds replacement GUI group. No main push or formal ZIP yet. CPU merge preparation cpu70_delivery_20261027 is uncommitted merge2171ef3+05c7ef96, exact e8ae RTL.',
        'LATEST: Portable real historical SD7f0ba644 fixture in m70d/prebuilt, manifest9f592ff9, patched Gitless test PASS. Local bundled CPU80 policy fixture passed59 cases. Reviewable package inventory closure10699 files/2.84GB before new payloads. G free about4.7GB; H absent, preserve originals. Use a fresh NTFS-compressed G extraction to limit physical space. Still to do: actual Main70 package/program entry tooling, skills review/binding, final current docs/index/audit; commit/push accepted mains and reread; seal ZIP, independent extraction/full regression, SD8/readback/program extracted bit/user return-reset/direct boot/apps/ZIP-bound completion. Do not touch unaccepted other-thread vision-driver-opt docs/source.',
        'Native hardware c50bb158/run6d01c260: CPU70/SYS49.5, final all-corner STA PASS, bitstream24226a3a. Existing187 external I/O constraint gaps retained.',
        'Regular short worktree G:/fpga/m70d contains identical513 native inputs,42 reports,47 outputs and snapshot files. It avoids Windows MAX_PATH without a link. Failed main70_board junction was removed; original native tree is unchanged.',
        'JTAG fresh65421/PDSbin scan: uniquePG2L100H ID00602899, DONE0 before programming. COM17 CP210x healthy. Earlier empty-cable scan and full-project audit failures are preserved.',
        'Full project audit remains pending: inherited README references missing build/hwc-acceptance-kit/README.md. Exact Main70Candidate CRAM gate separately proves all frozen inputs, ROM, final STA and outputs, with8 identity corruptions rejected. It explicitly does not certify formal release documentation/board/performance/package.',
        'Software-only frequency sync: GUI exact60/70 build guards, CPU70 OpenSBI99/140, DTB70, normal SD loader MAIN70. Host+RV32 clock/timer and boot-negative checks passed; SD18 loader scenarios passed. Original word-I/O kernel reused only with matching integration-source hashes; BULK/driver optimization candidate excluded. PN07 worker1953b37d remains explicitly authorized reuse; no PN08 geometry-source rebuild.',
        f"CoreMark ABAB owner={cm.get('owner_pid','?')}, status={cm.get('status','PENDING')}; latest batches={[(x['label'],x['status']) for x in cm.get('batches',[])]}. Verify actual process/command/start time before action.",
        'Reference G:/fpga/m80c is a regular copy of the accepted CPU80 package, using its original helpers and exact approved audit adapter. Original c80audio_unpack tree untouched. CPU70 candidate has different CPU RTL from that historical control; compare actual same-round CoreMark/MHz, not inferred scores.',
        'SD write01 PASS: USB disk2 FAT32 ~31.9GB, volume5c9f349d-bc80-11f1-b996-005056c00008. Eight files+manifest flushed/reread;98 unrelated root files and user directories preserved,107-file inventory and nine backups retained. User returned card and CPU-reset; boot01 six CRC/CPU70/SBI99:140/Linux root PASS. Card currently in board.',
        'Fixed-input board groups identity/timer/NNUE/search/image/full-detector/voice/four-model concurrency/microphone PASS. NNUE10ms miss retained; detector graph89.346142s, not30fps or physical full-board latency acceptance. board-tests02 overall FAILED_PRESERVED only because extra Linux CoreMark runner requested unsupported15000ms; retry at30000ms pending. Official bare-metal ABAB passed all12 performance+4 validation runs: control5.261228090791 vs candidate5.278557703854, decrease=-0.017329613063 <=0.05; total record only.',
        'First SD GUI failed because safety code accepted batch10000 only; verified hardware reports10001. Fix accepts only both known versions and retains ID/busy guards, host/RV32 tests PASS. GUI ELF3da37696 runs from /tmp diagnostic; FIRST_PRESENTED and worker observed after preserved transfer wait timeout. kit03 contains that fixed ELF and passed18 offline cases. Physical GUI/camera/Esc/mic/speaker feedback and final formal SD direct boot remain pending; RAM diagnostic is not delivery boot acceptance.',
        'CPU paired-source check PASS at clean G:/fpga/src_cpu80_gui1080_mulsigned_20261023 commit05c7ef96 with RTL e8ae2811; do not substitute fefd9305. G:/fpga/m70r is a regular independent regression worktree; recheck actual process before actions. Current source freeze7154be11. No main push/formal ZIP yet.',
        'GUI auto-start no longer requires a manually injected RAM stamp. With no observed CRAM assignment receipt, GUI CoreMark remains unavailable; a real PASS assignment receipt must be embedded for the final kit. Never fabricate a current-bitstream hash.',
        'No Flash authorization or write. No main push or formal ZIP before correctness/STA/real-board/CoreMark/model/concurrency gates. After passing: commit/merge/push and reread commit/hash, package, independent extraction/full regression, SD8 reread/direct SD boot/app acceptance bound to ZIP, then H archive of confirmed unused files. H unavailable currently; keep G originals.',
        '<!-- MAIN70_DELIVERY_20261027_END -->']
    block='\n'.join(rows)
    for doc in [workspace/'HANDOFF.md',project/'docs/CPU_Frequency_Handoff.md',workspace/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
        raw=doc.read_bytes();text=raw.decode('utf-8-sig').replace('\r\n','\n')
        pat=r'<!-- MAIN70_DELIVERY_20261027_BEGIN -->[\s\S]*?<!-- MAIN70_DELIVERY_20261027_END -->'
        if re.search(pat,text):text=re.sub(pat,lambda _:block,text,count=1)
        else:
            head,_,tail=text.partition('\n');text=head+'\n\n'+block+'\n\n'+tail
        if b'\r\n' in raw:text=text.replace('\n','\r\n')
        doc.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+text.encode())
    print(json.dumps(dict(status='MAIN70_DELIVERY_HANDOFF_REFRESHED',hardware_accessed=False,formal_delivery=False)))

if __name__=='__main__':main()
