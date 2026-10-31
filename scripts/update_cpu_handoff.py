"""Refresh only the status block of the maintained CPU handoff. Read-only to builds."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


def read_json(path):
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError:
        return {'status': 'WRITING_OR_UNREADABLE_RECHECK_SOURCE'}


def refresh_vision32(status_path):
    """Record this peripheral candidate without inheriting old CPU acceptance."""
    project = Path(__file__).resolve().parents[1]
    status = read_json(status_path)
    if Path(status['source_root']).resolve() != project:
        raise ValueError('Vision status belongs to a different source tree')
    for rel, expected in status['source_sha256'].items():
        if hashlib.sha256((project/rel).read_bytes()).hexdigest() != expected:
            raise ValueError('Vision handoff source changed: '+rel)
    rows = []
    for rel in status['test_results']:
        data = read_json(project/rel)
        rows.append(f"- `{rel}`: {data.get('status', 'PENDING')}; cases={data.get('cases', '?')}")
    resources = read_json(project/'docs/validation/vision32-native-resources-20261024.json')
    block = '\n'.join([
        '<!-- VISION32_CORE_20261024_BEGIN -->',
        '## 32-MAC vision implementation candidate (2026-10-24)', '',
        f"Source: {project.as_posix()}, branch feature/vision32-core-20261024, parent07c3918, implementation={status.get('implementation_commit','UNCOMMITTED')}. CPU75/SYS49.5/1080p30, official Pikafish and voice unchanged. P4xOC8 whole-layer DMA replaces old conv; distinct V321 subdevice rejects old ABI3. Source hashes checked before this refresh.", '',
        'Implemented NHWC4 gather, K-major/OC8 resident weights, local partial sums through K1152, per-channel bias/multiplier/shift and supplied256-byte activation table, compact output and raw-I32 diagnostic mode. Accepted transactions drain on abort/timeout; no shared-AXI reset. Layer descriptor/ABI only: full W8A8 graph, Linux driver/camera ownership and10-second application acceptance remain pending.', '',
        *rows, '',
        f"Native: {status['native_root']}; {status['phase']}. Resource proof: {resources.get('status','PENDING')}; whole chip={resources.get('whole_chip',{})}. Target<=8 vision DRM and<=140 whole-chip DRM. No new PnR/board/SD/Flash/push/delivery for this candidate. Independent pfpnr4 task is untouched; inspect live owners before any later action.", '',
        'Tests use all60 layer channel/kernel/stride combinations with reduced spatial sizes, plus320-wide first-layer and adversarial cases; these are not full-model/real-image inference. See docs/Vision32_Core_20261024.md, build/vision32-status.json and native resource-evidence/result.json. Preserve failure/input/native evidence.',
        '<!-- VISION32_CORE_20261024_END -->'])
    for doc in (project/'docs/CPU_Frequency_Handoff.md', project.parent/'HANDOFF.md',
                project.parent/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'):
        text = doc.read_text(encoding='utf-8-sig') if doc.exists() else '# FPGA/SoC handoff\n'
        begin, end = '<!-- VISION32_CORE_20261024_BEGIN -->', '<!-- VISION32_CORE_20261024_END -->'
        if begin in text:
            if text.count(begin)!=1 or text.count(end)!=1:
                raise ValueError('Vision handoff marker ambiguity')
            text = re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end), lambda _:block, text, count=1)
        else:
            head, _, tail = text.partition('\n')
            text = head+'\n\n'+block+'\n\n'+tail.lstrip('\n')
        payload = text.replace('\r\n', '\n').encode('utf-8')
        if doc.exists() and b'\r\n' in doc.read_bytes():
            payload = payload.replace(b'\n', b'\r\n')
        doc.write_bytes(payload)
    print(json.dumps(dict(status='VISION32_SOURCE_BOUND_HANDOFF_REFRESHED', build_started=False, board_accessed=False, remote_pushed=False)))


def refresh_gui1080(a):
    """Refresh current SoC/display evidence without inheriting historical CPU-only acceptance."""
    attempts=sorted(a.target_work.glob('attempt-*/flow.json'))
    if not attempts:return False
    selected=attempts[-1];flow=read_json(selected)
    if 'COMBINED_' not in flow.get('status','') and flow.get('status')!='FAILED_PRESERVED_NO_PROMOTION':return False
    project=Path(__file__).resolve().parents[1]
    native=Path(flow.get('native_root') or a.target_native_root)
    snapshot=read_json(native/'pds/build_snapshot.json')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if flow.get('native_root'):
        for name,h in snapshot.get('inputs',{}).items():
            if sha(native/name)!=h or sha(a.target_soc/name)!=h:raise ValueError('Current GUI1080 frozen input differs: '+name)
    runtime=read_json(a.target_work/'runtime-02/result.json')
    display=read_json(a.target_soc/'config/display.json');clock=read_json(a.target_soc/'config/clocks.json')
    model_control=read_json(a.target_work/'board-control-models-02/binding.json')
    qualification=flow.get('resource_comparison') or read_json(a.target_work/'resource-priority-01/qualified-tradeoff.json')
    native_report=native/'pds/report_timing/soc_top.rtr'
    summary='等待最终全角 STA；尚无原生结论'
    if native_report.is_file():
        text=native_report.read_text(errors='replace');found=re.search(r'Design Summary[^\r\n]*',text)
        summary=(found[0] if found else '未找到原生 Design Summary')+'；原生报告 SHA256='+sha(native_report)
    if flow.get('status')=='COMBINED_ROM_GUI1080_NATIVE_ALL_GATES_PASS_BOARD_PENDING':summary+='；全部原生门禁已通过，板测仍待完成'
    rows=[
        ('刷新时间 UTC',datetime.now(timezone.utc).isoformat()),
        ('当前目标','80MHz 卷积与浅色 1080p60 GUI；本轮不依赖 SD 返板'),
        ('实现来源',str(a.target_soc)+'；SoC='+str(flow.get('soc_implementation_commit','尚未冻结'))),
        ('CPU 来源',str(read_json(a.target_soc/'rtl/cpu/source.json').get('source_reference_commit'))+'；RTL='+sha(a.target_soc/'rtl/cpu/CoreTop.sv')),
        ('实际配置',str(clock.get('cpu_hz'))+'Hz CPU / '+str(clock.get('sys_hz'))+'Hz SYS / '+str(display.get('pixel_hz'))+'Hz pixel；'+str(display.get('width'))+'×'+str(display.get('height'))),
        ('构建状态',str(flow.get('status'))+'；phase='+str(flow.get('phase'))+'；owner PID='+str(flow.get('pid'))+'；恢复前核对真实进程与启动时间'),
        ('原生目录',str(native)+'；run='+str(snapshot.get('run_id'))+'；inputs='+str(len(snapshot.get('inputs',{})))),
        ('资源审核',str(flow.get('resources',{}))+'；resource qualification='+str(qualification.get('status','尚未审核'))),
        ('最终全角 STA',summary),
        ('运行时离线检查',str(runtime.get('status'))+'；manifest SHA256='+str(runtime.get('sd_manifest_sha256'))),
        ('本轮板测','尚未完成；配置、启动、CoreMark、模型、采音与 HDMI 必须绑定本轮 run'),
        ('720p 模型对照',str(model_control.get('status'))+'；全部样本统计='+str(model_control.get('latency',{}))),
        ('保留失败','p1：CPU setup −0.747ns，SYS/CPU/DDR hold 失败；p2：CPU setup −0.739ns、pixel setup −0.036ns，全部 hold 通过；attempt04 资源筛选失败原样保留'),
        ('验收与推送','仅限制平均 CoreMark/MHz 绝对下降≤0.05；正确性、全角 STA 与本轮板测成功后推送 main，再制作交付包'),
        ('下一步与整理','通过原生门禁后走 ROM TFTP 网络启动；正式 SD 交付另验；完成版本交付后逐文件校验归档 H:，不使用 F:，不写 Flash'),
    ]
    table='## 来源绑定的当前状态\n\n| 项目 | 结论与证据 |\n|---|---|\n'+''.join('| '+str(k).replace('|','\\|')+' | '+str(v).replace('|','\\|')+' |\n' for k,v in rows)
    doc=project/'docs/CPU_Frequency_Handoff.md';raw=doc.read_bytes();text=raw.decode('utf-8-sig')
    begin,end='<!-- CPU_HANDOFF_STATUS_BEGIN -->','<!-- CPU_HANDOFF_STATUS_END -->'
    if text.count(begin)!=1 or text.count(end)!=1:raise ValueError('handoff status markers missing or duplicated')
    block=begin+'\n'+table+'\n'+end
    if b'\r\n' in raw:block=block.replace('\n','\r\n')
    text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1)
    doc.write_bytes(text.encode('utf-8'))
    print(json.dumps(dict(status='CPU_HANDOFF_GUI1080_SOURCE_BOUND_REFRESHED',path=str(doc),sha256=sha(doc),run_id=snapshot.get('run_id'),flow_sha256=sha(selected),build_started=False,board_accessed=False,remote_pushed=False),ensure_ascii=False))
    return True


def refresh_half80(a):
    """Refresh the isolated80MHz half-output run without promoting old evidence."""
    if a.target_hz != 80000000 or a.target_soc.name != 'performance_soc_cpu80_halfmac_gui1080_20261023':
        return False
    files = sorted(a.target_work.glob('attempt-*/flow.json'))
    if not files:
        raise ValueError('Half80 flow not started')
    flow_path = files[-1]; flow = read_json(flow_path)
    native = Path(flow['native_root']); snap = read_json(native/'pds/build_snapshot.json')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for name, value in snap.get('inputs', {}).items():
        if sha(native/name) != value or sha(a.target_soc/name) != value:
            raise ValueError('Half80 frozen input mismatch: '+name)
    final_path = a.target_work/flow.get('final_sta_filename','final-sta-01.json')
    final = read_json(final_path)
    route_audit = read_json(a.target_work/flow.get('route_audit_filename','final-native-route-audit-01.json'))
    if final:
        if final['run_id'] != snap['run_id'] or final['native_xml_sha256'] != sha(native/'pds/report_timing/rtr.db'):
            raise ValueError('Half80 final STA binding differs')
    rows = [
        ('Updated UTC', datetime.now(timezone.utc).isoformat()),
        ('Current target', 'Actual CPU80MHz / SYS49.5MHz / pixel148.5MHz,1080p60, half dense output chains8; H128 disabled; Stage A/cache/conv retained'),
        ('Source', str(a.target_soc)+'; frozen='+str(flow.get('source_commit', 'pending full regression'))),
        ('Native', str(native)+'; run='+str(snap.get('run_id'))+'; inputs='+str(len(snap.get('inputs', {})))),
        ('Controller', str(flow['status'])+'; phase='+str(flow.get('phase'))+'; owner PID snapshot='+str(flow['owner_pid'])+'; verify live command/start time before recovery'),
        ('Timing contract', 'Exact80MHz GPLL27x40/13.5; FDC12.495ns; CDC11.695ns; final all-corner STA='+str(final.get('status', 'pending'))),
        ('Final native STA', 'CPU WNS='+str(final.get('cpu_wns_ns', 'pending'))+'ns; other failing rows='+str(final.get('other_failing_summary_rows', 'pending'))+'; controller='+str(final.get('controller_status', 'still running'))+'; final receipt SHA256='+(sha(final_path) if final else 'pending')),
        ('Mapped resources', str(final.get('resources', 'Current synthesis pending; previous p2:45060LUT/33456FF/4924LUTRAM/121.5DRM/105APM'))),
        ('Current change', str(flow.get('purpose','Exact80MHz retarget; no RTL logic change'))),
        ('Final route registration', str(route_audit.get('status', 'pending'))+'; successful='+str(route_audit.get('successful', 'pending'))+'; invalid targets='+str(route_audit.get('invalid', 'pending'))+'; strict checker correctly rejects invalid constraints'),
        ('Preserved85MHz', 'c85h1080p2 / b959e3431be14872960d0311322640eb / source009aba2: final CPU WNS -0.782ns, other115 nonnegative;45103LUT/33456FF/105APM; no board/push/delivery'),
        ('Correctness', 'Hash-bound half MAC130cases/22reset cuts, S16 golden8394words and integrated64-row DMA/gather/conv checks retained. New80MHz full regression and vendor PLL evidence are in this flow phases'),
        ('Performance gates', 'Official NNUE end-to-end no regression; CoreMark/MHz pooled mean absolute decline<=0.05. Half FC0 engine106to180SYS cycles; board measurements pending'),
        ('Acceptance', 'No board/push/package. WNS>0 normal acceptance; -0.1<WNS<=0 board trial only, no delivery/main; all other domains/hold must pass'),
        ('Recovery', str(flow_path)+'; native-build.log and native input-snapshots/<run>. Keep85/full80 failed native evidence; no F writes or Flash'),
    ]
    block = '<!-- CPU80_HALF_CURRENT_BEGIN -->\n## CPU80 half-output current run\n\n| Item | Evidence |\n|---|---|\n'
    block += ''.join('| '+k+' | '+str(v).replace('|', '\\|')+' |\n' for k,v in rows)
    block += '\n<!-- CPU80_HALF_CURRENT_END -->'
    doc = Path(__file__).resolve().parents[1]/'docs/CPU_Frequency_Handoff.md'
    text = doc.read_text(encoding='utf-8-sig'); pattern = r'<!-- CPU80_HALF_CURRENT_BEGIN -->.*?<!-- CPU80_HALF_CURRENT_END -->'
    if re.search(pattern, text, re.S):
        text = re.sub(pattern, lambda _:block, text, count=1, flags=re.S)
    else:
        first, tail = text.split('\n', 1); text = first+'\n\n'+block+'\n'+tail
    doc.write_text(text, encoding='utf-8')
    print(json.dumps(dict(status='CPU80_HALF_HANDOFF_REFRESHED_NOT_ACCEPTED', path=str(doc), flow_sha256=sha(flow_path), native_run=snap.get('run_id'))))
    return True


def refresh_half85(a):
    """Source-bound status for the separate half-output experiment; read only."""
    if a.target_hz != 85000000:
        return False
    flow_path=a.target_work/'attempt-02/flow.json'
    flow=read_json(flow_path)
    if not flow:
        raise ValueError('Half-output experiment flow is missing')
    project=Path(__file__).resolve().parents[1]
    native=Path(flow['native_root']);snapshot=read_json(native/'pds/build_snapshot.json')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,h in snapshot.get('inputs',{}).items():
        if sha(native/name)!=h or sha(a.target_soc/name)!=h:
            raise ValueError('Frozen half-output input differs: '+name)
    clock=read_json(a.target_soc/'config/clocks.json')
    rows=[('Updated UTC',datetime.now(timezone.utc).isoformat()),
          ('Current experiment','Exact CPU85MHz, dense output chains16 to8,1080p60; separate from CPU80/P8'),
          ('Source',str(a.target_soc)+'; local frozen commit='+str(flow.get('source_commit'))),
          ('Native',str(native)+'; run='+str(snapshot.get('run_id'))+'; inputs='+str(len(snapshot.get('inputs',{})))),
          ('Clocks',str(clock.get('cpu_hz'))+' CPU /49500000 SYS /148500000 pixel; FDC11.760ns; CDC10.960ns'),
          ('Controller',str(flow.get('status'))+'; phase='+str(flow.get('phase'))+'; PID snapshot='+str(flow.get('owner_pid'))+'; recheck real process before recovery'),
          ('Correctness','Full project regression02 PASS; half-core130 cases/22 reset cuts; S16 independent golden8394 words; actual64-row DMA/gather/conv isolation PASS; vendor PLL85 PASS'),
          ('Performance','FC0 pure engine106 to180 SYS cycles (+1.495us). Official NNUE end-to-end no-regression remains pending and mandatory; CM/MHz decline at most0.05'),
          ('Preserved CPU80/P8','223d30a /7d0a56b96a224806b2724794fa37792c: CPU WNS -0.131ns; other115 rows nonnegative. No board/push/delivery'),
          ('Acceptance','No board, main push or delivery for this experiment yet; native resource/STA and actual model gates required. Old accepted720p/R3 is a different version'),
          ('Recovery',str(flow_path)+'; native-build.log and input-snapshots/<run> contain current commands/reports; never restart a running job or program an unknown bitstream')]
    block='<!-- CPU85_HALF_CURRENT_BEGIN -->\n## CPU85 half-output experiment current status\n\n| Item | State and evidence |\n|---|---|\n'+''.join('| '+k+' | '+str(v).replace('|','\\|')+' |\n' for k,v in rows)+'\n<!-- CPU85_HALF_CURRENT_END -->'
    doc=project/'docs/CPU_Frequency_Handoff.md';text=doc.read_text(encoding='utf-8-sig')
    pattern=r'<!-- CPU85_HALF_CURRENT_BEGIN -->.*?<!-- CPU85_HALF_CURRENT_END -->'
    if re.search(pattern,text,re.S):text=re.sub(pattern,lambda _:block,text,count=1,flags=re.S)
    else:
        head,tail=text.split('\n',1);text=head+'\n\n'+block+'\n'+tail
    doc.write_text(text,encoding='utf-8')
    print(json.dumps(dict(status='CPU85_HALF_HANDOFF_SOURCE_BOUND_REFRESHED',run_id=snapshot.get('run_id'),flow_sha256=sha(flow_path),build_started=False,board_accessed=False,remote_pushed=False)))
    return True


def main():
    project = Path(__file__).resolve().parents[1]
    if not sys.argv[1:] and (project/'docs/validation/main75-release-20261028/current-state.json').is_file():
        from update_main75_delivery_handoff import main as refresh_delivery
        refresh_delivery()
        return
    joint = read_json(project.parent/'native-result.json')
    joint_owner = read_json(project.parent/'status.json')
    if (not sys.argv[1:] and joint.get('status') ==
            'CPU75_JOINT_FULL_REGRESSION_ROUTED_ALL_CORNER_STA_AND_HASH_READBACK_PASS_NOT_BOARD'
            and Path(joint_owner.get('source_root', '.')).resolve() == project):
        from update_main75_joint_handoff import main as refresh_joint
        refresh_joint()
        return
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_hw_publish_20261025':
        import runpy
        runpy.run_path(str(Path(__file__).with_name('update_hw_publication_handoff.py')), run_name='__main__')
        return
    # This checkout has its own integrated candidate. Keep historical CPU80
    # and vision-only status blocks intact; no build/board action is invoked.
    project = Path(__file__).resolve().parents[1]
    if not sys.argv[1:] and project.name == 'performance_soc_integrated_opt60_20261024':
        from update_integrated_opt60_handoff import main as refresh_optimization
        refresh_optimization()
        return
    clock = read_json(project/'config/clocks.json')
    if not sys.argv[1:] and clock.get('cpu_hz') == 60000000:
        import runpy
        state = read_json(project/'build/integrated60-status.json')
        phase = state.get('phase','CPU60 source checkout; native and software evidence must be read before resuming')
        sys.argv = [str(project/'scripts/update_integrated60_handoff.py'),'--phase',phase]
        runpy.run_path(sys.argv[0],run_name='__main__')
        return
    if Path(__file__).resolve().parents[1].name == 'performance_soc_pikafish_dedicated_20261024' and len(sys.argv)==1:
        from update_pikafish_dedicated_handoff import main as refresh_dedicated
        refresh_dedicated()
        return
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target-hz', type=int, default=80000000)
    ap.add_argument('--target-work', type=Path, default=Path('G:/fpga/performance_soc_voice_hw/build/cpu80-halfmac-gui1080-20261023'))
    ap.add_argument('--target-cpu', type=Path, default=Path('G:/fpga/src_cpu80_gui1080_mulsigned_20261023'))
    ap.add_argument('--target-soc', type=Path, default=Path('G:/fpga/performance_soc_cpu80_halfmac_gui1080_20261023'))
    ap.add_argument('--target-native-root', type=Path, default=Path('G:/fpga/c80h1080p3'))
    ap.add_argument('--active-cpu', type=Path, default=Path('G:/fpga/src_cpu80_gui1080_mulsigned_20261023'))
    ap.add_argument('--active-work', type=Path, default=Path('G:/fpga/performance_soc_voice_hw/build/cpu80-20261020-csrcount-retry'))
    ap.add_argument('--active-description', default='直接942e2dd，仅SupervisorCsr退休计数器；Commit/其他模块保持原版')
    ap.add_argument('--active-windows', default='full-entry-csrcount-final.json')
    ap.add_argument('--active-native-root', type=Path, default=Path('G:/fpga/c80p15'))
    ap.add_argument('--active-resource-root', type=Path, default=Path('G:/fpga/c80r18'))
    ap.add_argument('--active-evidence', default='cpu80-20261020-csrcount-retry/final-native')
    ap.add_argument('--active-board-evidence', default='cpu80-20261020-csrcount-retry/board')
    ap.add_argument('--active-review-evidence', default='cpu80-20261020-csrcount-retry/review')
    ap.add_argument('--active-board-work', type=Path, default=Path('G:/fpga/performance_soc_voice_hw/build/cpu80-20261020-csrcount-retry/board-campaign-1506'))
    ap.add_argument('--native-root', type=Path, default=Path('G:/fpga/c80p13'))
    ap.add_argument('--resource-root', type=Path, default=Path('G:/fpga/c80r16'))
    ap.add_argument('--owner', default='pnr-p13-owner.json')
    ap.add_argument('--post-owner', default='post-pnr-p13.json')
    ap.add_argument('--native-evidence', default='breq-final-native')
    ap.add_argument('--full-entry', default='breq-final')
    ap.add_argument('--cpu-test', default='cpu80-breq-complete-unit.json')
    ap.add_argument('--legacy-status', action='store_true', help='Refresh the historical CPU-only table explicitly')
    ap.add_argument('--vision32-status', type=Path)
    a = ap.parse_args()
    if a.vision32_status or Path(__file__).resolve().parents[1].name == 'performance_soc_vision32_20261024':
        refresh_vision32((a.vision32_status or Path(__file__).resolve().parents[1]/'build/vision32-status.json').resolve())
        return
    if not a.legacy_status and refresh_half80(a):return
    if not a.legacy_status and refresh_half85(a):return
    if not a.legacy_status and refresh_gui1080(a):
        return
    target_records = {name: read_json(a.target_work / (name + '.json')) for name in
                      ['readbuf-mapping','readbuf-mapping-owner','readbuf-mapping-fixtures','resource-check-owner','resource-stage-wait-owner','freeze-namespace-recovery','controller-freeze-recovery','failed-endpoint-expansion-owner-v4','mapping-v10','native-capture-fixtures','solver-runtime-integrity','ftb-resource-accounting-fixtures','preparation-recovery','ftb-pack-mapping','ftb-pack-mapping-fixtures','native-ftb-pack-mapping','baseline-v2','preparation-flow-v3','resource-first-required','performance-budget-fixtures','performance-policy','reference85','rs-base-mapping','rs-base-mapping-fixtures','native-rs-base-mapping','baseline','baseline-failed-v1','baseline-failed-v2','baseline-stimulus-recovery','preparation-flow','preparation-flow-v2','baseline-v3','focus-vector','focus','generate','full','regression-recovery','regression-recovery-v3','synthesis-recovery','controller-recovery-v3','pma-tdd-before','pma-tdd-after','mapping','mapping-v2','mapping-v3','mapping-final','div-prep-mapping','div-prep-mapping-final','dc-shape-mapping','dc-shape-mapping-v2','dc-shape-mapping-v3','dc-shape-mapping-v4','dc-shape-mapping-final','dc-shape-mapping-final-fixtures','csr-decode-mapping','csr-graph-fixtures','full-source-binding-owner','full-source-archive-binding','diagnostic-preparation-recovery','failed-endpoint-expansion-owner-v3','hierarchical-vector-binding-fixtures','hierarchical-vector-control-fixtures','dc-shape-mapping-fixtures','hierarchical-mapping-fixtures','mapping-recovery','full-v2','resource','resource-v2','resource-scope','resource-scope-v2','full-entry','full-entry-v2','full-entry-v3','coremark-cycles','offline-flow','offline-flow-v2','offline-flow-v3','soc-freeze','native','native-mapping-owner','native-mapping-final','native-div-prep-mapping','native-dc-shape-mapping','native-csr-decode-mapping','final-native','post-native-offline','post-native-offline-v2','post-native-offline-v3','board']}
    # Preserve source-bound recovery and the newest mapping/board controllers in
    # the generated handoff without treating any of them as hardware acceptance.
    for name in ['trial-preflight','trial-flow','screen-resource-owner','resource-v1','resource-v2-preparation',
                 'store-pipe-native','store-pipe-native-diagnostic-v3','pma-load-native-fixtures',
                 'pma-load-contract-fixtures','revised-full-native-fixtures','pma-snapshot-contract-v2',
                 'pma-cram-contract','concurrent-rtl-v3/result','concurrent-rtl-faults-v2/result',
                 'full-soc-preparation','native-inverter-extension-binding',
                 'native-flow-v3','native-mapping-owner-v3','full-soc-flow-v5','full-soc-fixture-recovery','full-soc-stage-interruption',
                 'resume-resource-work','resource-v3','resource-v4','cachedkey-resource-audit-v3',
                 'resource-mapping-owner-v2','full-soc-flow-v3','consumer-native-fixtures',
                 'encoded-full-native-fixtures','hint-contract-fixtures','snapshot-contract-fixtures',
                 'mapping-byte-identity-recovery','full-soc-flow', 'native-readbuf-mapping',
                 'resource-first-resolution', 'board-continuation-owner',
                 'completed-cpu-flow-recovery-v2', 'mul-signed-mapping',
                 'native-mul-signed-mapping', 'prior-native-failure',
                 'mul-signed-mapping-fixtures', 'mul-vendor-waveform-v2/result',
                 'native-mul-vendor-waveform/result', 'full-preparation-recovery',
                 'soc-freeze-owner', 'native-flow-preparation',
                 'native-portable-validation', 'native-start-binding',
                 'candidate-flow', 'worktree-preflight', 'probe-slot-mapping',
                 'probe-slot-mapping-v2', 'pnr-user-authorization', 'resource-check-owner-v3', 'authorized-native-flow', 'offline-preparation-recovery',
                 'native-probe-slot-mapping', 'probe-slot-mapping-fixtures',
                 'prior-final-native', 'prior-resource-first-required']:
        obj = read_json(a.target_work / (name + '.json'))
        if obj:
            target_records[name] = obj
    required_target_phases = {'baseline','focus','generate','full','resource-v2','resource-scope-v2',
                             'mapping-final','div-prep-mapping-final','dc-shape-mapping-final','csr-decode-mapping','full-entry','coremark-cycles','offline-flow-v2','soc-freeze',
                             'native','native-mapping-owner','native-mapping-final','native-div-prep-mapping','native-dc-shape-mapping','native-csr-decode-mapping','final-native','post-native-offline-v2','board'}
    if (a.target_work / 'resource-v4.json').is_file():
        required_target_phases.difference_update({'resource-v2','resource-scope-v2'})
        required_target_phases.update({'resource-v4','cachedkey-resource-audit-v3','resource-mapping-owner-v2','full-soc-flow-v3'})
    if (a.target_work / 'store-pipe-native-diagnostic-v3.json').is_file():
        required_target_phases = {'baseline','focus','generate','full','full-source-archive-binding',
                                 'resource-v2','store-pipe-native','resource-mapping-owner-v2',
                                 'full-entry','coremark-cycles','soc-freeze','native','native-mapping-owner-v3',
                                 'final-native','post-native-offline-v2','board'}
    if (a.target_work / 'combined-preparation.json').is_file():
        required_target_phases = {'combined-preparation','focus','generate','full',
                                 'full-source-archive-binding','resource-v1','frontend-native',
                                 'rob-size-native','store-pipe-native','resource-mapping-owner-v2',
                                 'verification-preparation-v2','full-soc-flow','full-entry',
                                 'coremark-cycles','soc-freeze','native','final-native','board'}
        required_target_phases.update({'native-flow-v4','native-mapping-owner-v4',
                                       'native-imports-owner','portable-eleven-native-owner',
                                       'portable-eleven-resource-tests-v2','resource-imports-owner',
                                       'offline-sd-owner','combined-resource-profile'})
        for name in required_target_phases:
            target_records[name] = read_json(a.target_work / (name + '.json'))
    if (a.target_work / 'resource-first-analysis.json').is_file():
        required_target_phases = {'resource-first-analysis', 'baseline', 'focus', 'generate',
                                 'preparation-flow', 'preparation-recovery', 'freeze',
                                 'resource-v1', 'mul-csa-native-prefilter-v3', 'coremark-cycles',
                                 'paired-archive-verification', 'selected-preflight',
                                 'resource-mapping-selected', 'resource-imports-owner',
                                 'physical-product-checker-fixtures', 'csr-anchor-fixtures',
                                 'portable-eleven-resource-tests', 'complete-check-recovery',
                                 'full-soc-flow-v3', 'native-flow-v4', 'native-mapping-owner-v4',
                                 'native-imports-owner', 'portable-eleven-native-owner',
                                 'post-native-offline', 'readonly-review-launch', 'offline-sd-owner',
                                 'full', 'full-entry', 'soc-freeze', 'native', 'final-native', 'board'}
        for name in required_target_phases:
            target_records[name] = read_json(a.target_work / (name + '.json'))
    target_records = {name: obj for name, obj in target_records.items()
                      if obj or name in required_target_phases}
    if (a.target_work / 'baseline-binding.json').is_file():
        target_records = {name: read_json(a.target_work / (name + '.json')) for name in ['baseline-binding','interface-contract','focus-before','focus-after','full','resource','native','final-native','board','delivery']}
        if (a.target_work / 'soc-freeze.json').is_file():
            target_records = {name: read_json(a.target_work / (name + '.json')) for name in
                              ['baseline-binding', 'baseline', 'focus', 'focus-conv',
                               'functional-reference-binding', 'full', 'resource',
                               'soc-freeze', 'native-flow', 'final-native', 'package', 'offline-unpack']}
    selected_baseline = target_records.get('baseline-v2', {})
    recovery_path = a.target_work / 'edit-guard-recovery.json'
    if selected_baseline.get('status') == 'PASS' and recovery_path.is_file():
        recovery = read_json(recovery_path)
        if recovery.get('baseline_receipt_sha256') == hashlib.sha256((a.target_work / 'baseline-v2.json').read_bytes()).hexdigest():
            target_records['baseline-failed-v1'] = target_records.get('baseline', {})
            target_records['baseline'] = dict(selected_baseline, selected_receipt='baseline-v2.json', earlier_failure_preserved=True)
    target_clock = read_json(a.target_soc / 'config/clocks.json')
    recovery = target_records.get('regression-recovery', {})
    if recovery.get('status') == 'INTERRUPTED_CPU_AND_SOC_TIMEOUT_PRESERVED_RETRY_REQUIRED':
        original = a.target_work / 'full.json'
        if (original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest() ==
                recovery.get('original_receipts', {}).get('full.json')):
            target_records['full'] = dict(target_records['full'],
                status='INTERRUPTED_OWNER_ABSENT_NOT_PASS_SEE_REGRESSION_RECOVERY')
    target_pll = read_json(a.target_work / 'pll-waveform/result.json')
    target_freeze = read_json(a.target_work / 'freeze.json')
    target_snapshot = read_json(a.target_native_root / 'pds/build_snapshot.json')
    active_pair = read_json(a.active_work / 'generate.json')
    active_baseline = read_json(a.active_work / 'baseline.json')
    active_focus = read_json(a.active_work / 'focus.json')
    active_full = read_json(a.active_work / 'full.json')
    active_resource = read_json(a.active_work / 'resource.json')
    active_freeze = read_json(a.active_work / 'freeze.json')
    active_windows = read_json(a.active_work / a.active_windows)
    active_native = read_json(a.active_work / 'native.json')
    active_flow = read_json(a.active_work / 'offline-flow.json')
    active_preparation = read_json(a.active_work / 'board-preparation.json')
    root = Path(__file__).resolve().parents[1]
    active_final = read_json(root / 'docs/validation' / a.active_evidence / 'result.json')
    active_snapshot = read_json(a.active_native_root / 'pds/build_snapshot.json')
    active_resource_snapshot = read_json(a.active_resource_root / 'pds/build_snapshot.json')
    active_native_source = read_json(a.active_native_root / 'rtl/cpu/source.json')
    active_clocks = read_json(a.active_native_root / 'config/clocks.json')
    active_board = read_json(root / 'docs/validation' / a.active_board_evidence / 'result.json')
    active_delivery = read_json(root / 'docs/validation/cpu80-20261020-csrcount-retry/delivery/result.json')
    active_publication = read_json(root / 'docs/validation/cpu80-20261020-csrcount-retry/publication/result.json')
    active_review = read_json(root / 'docs/validation' / a.active_review_evidence / 'result.json')
    if active_review and active_review.get('candidate_run_id') != active_snapshot.get('run_id'):
        raise ValueError('Active review belongs to another active native run')
    connection_record = read_json(a.active_work / 'board-connection.json')
    if connection_record and connection_record.get('candidate_run_id') != active_snapshot.get('run_id'):
        raise ValueError('Board connection record belongs to another native run')
    connection = connection_record or active_review.get('board_connection', {})
    active_board_work = read_json(a.active_board_work / 'owner.json')
    active_board_repeat = read_json(a.active_board_work / 'repeat/owner.json')
    if active_board_work and active_board_work.get('run_id') != active_snapshot.get('run_id'):
        raise ValueError('Active board campaign belongs to another native run')
    connection_status = ('FTDI=' + str(connection.get('ftdi_count', '?')) +
                         '；枚举状态=' + str(connection.get('ftdi_status', '?')) +
                         '；' + connection.get('created_utc', '无当前检查'))
    active_cycles = read_json(root / 'build/cpu80-20261020-csrhead/coremark-cycles.json')
    for label, obj in [('active-final', active_final), ('active-board', active_board)]:
        if obj.get('run_id') and obj['run_id'] != active_snapshot.get('run_id'):
            raise ValueError(label + ' belongs to another active native run')
    active_phase = '尚无当前阶段标记'
    active_log = a.active_work / 'native-build.log'
    if active_log.is_file():
        active_markers = re.findall(r'(?m)^(?:PDS argv:[^\r\n]+|[A-Z][A-Z_]+_PASS[^\r\n]*)',
                                   active_log.read_text(errors='replace'))
        if active_markers:
            active_phase = active_markers[-1]
    if active_native_source and active_freeze.get('rtl_sha256'):
        if active_native_source.get('sha256') != active_freeze['rtl_sha256']:
            raise ValueError('Active native source does not match selected CPU freeze')
    if active_snapshot.get('inputs'):
        if active_snapshot['inputs'] != active_resource_snapshot.get('inputs'):
            raise ValueError('Active native inputs differ from gated resource candidate')
        for name, digest in active_snapshot['inputs'].items():
            path = a.active_native_root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Active native frozen input changed: ' + name)
    control_work = root / 'build/cpu80-20261020-csrhead'
    control_full = read_json(control_work / 'full.json')
    control_resource = read_json(control_work / 'resource.json')
    work = root / 'build/cpu80-20261019'
    evidence = root / 'docs/validation/cpu80-20261019'
    doc = root / 'docs/CPU_Frequency_Handoff.md'
    snap = read_json(a.native_root / 'pds/build_snapshot.json')
    source = read_json(a.native_root / 'rtl/cpu/source.json')
    clocks = read_json(a.native_root / 'config/clocks.json')
    owner = read_json(work / a.owner)
    resource_task = (read_json(work / 'pe-hold-resource-final-owner.json') or
                     read_json(work / 'pe-hold-resource-retry-owner.json') or
                     read_json(work / 'pe-hold-resource-owner.json'))
    resource_full = (read_json(work / 'full-entry-pe-hold-pre-pnr-portable.json') or
                     read_json(work / 'full-entry-pe-hold-pre-pnr-retry.json') or
                     read_json(work / 'full-entry-pe-hold-pre-pnr.json'))
    new_cpu_focus = read_json(work / 'ibwrite80-targeted-v2.json')
    new_cpu_pair = (read_json(work / 'cpu80-ibwrite-source-freeze.json') or
                    read_json(work / 'cpu80-ibwrite-generation-reviewed.json') or
                    read_json(work / 'cpu80-ibwrite-generation.json'))
    new_cpu_unit = read_json(work / 'cpu80-ibwrite-complete-unit.json')
    new_cpu_synth = (read_json(work / 'ibwrite80-synthesis-bound-owner.json') or
                     read_json(work / 'ibwrite80-synthesis-qualified-owner.json') or
                     read_json(work / 'ibwrite80-synthesis-final-owner.json') or
                     read_json(work / 'ibwrite80-synthesis-retry-owner.json') or
                     read_json(work / 'ibwrite80-synthesis-owner.json'))
    new_cpu_native_diag = read_json(work / 'ibwrite80-all-native-diagnostic.json')
    new_cpu_windows = (read_json(work / 'full-entry-ibwrite-pre-pnr-bound.json') or
                       read_json(work / 'full-entry-ibwrite-pre-pnr.json'))
    carry_pair = read_json(work / 'cpu80-carryin-source-freeze.json')
    carry_unit = read_json(work / 'cpu80-carryin-complete-unit.json')
    carry_resource = read_json(work / 'carryin80-resource-owner.json')
    prefix_pair = read_json(work / 'cpu80-prefix-source-freeze.json')
    prefix_unit = read_json(work / 'cpu80-prefix-complete-unit.json')
    prefix_resource = read_json(work / 'prefix80-resource-owner.json')
    prefix_windows = read_json(work / 'full-entry-prefix-pre-pnr.json')
    rs_pair = read_json(work / 'cpu80-rsunion-source-freeze.json')
    rs_resource = read_json(work / 'rsunion80-resource-owner.json')
    rs_unit = read_json(work / 'cpu80-rsunion-complete-unit.json')
    rs_windows = read_json(work / 'full-entry-rsunion-pre-pnr.json')
    eq_pair = read_json(work / 'cpu80-eqfast-source-freeze.json')
    eq_focus = read_json(work / 'eqfast80-targeted.json')
    eq_unit = read_json(work / 'cpu80-eqfast-complete-unit.json')
    eq_resource = read_json(work / 'eqfast80-resource-owner.json')
    eq_windows = read_json(work / 'full-entry-eqfast-pre-pnr.json')
    br_pair = read_json(work / 'cpu80-breq-source-freeze.json')
    br_base = read_json(work / 'breq80-baseline.json')
    br_focus = read_json(work / 'breq80-targeted.json')
    br_unit = read_json(work / 'cpu80-breq-complete-unit.json')
    br_resource = read_json(work / 'breq80-resource-owner.json')
    br_windows = read_json(work / 'full-entry-breq-pre-pnr.json')
    br_flow = read_json(work / 'breq80-offline-flow-owner.json')
    post = read_json(work / a.post_owner)
    cpu = read_json(work / a.cpu_test)
    native = read_json(evidence / a.native_evidence / 'result.json')
    full = read_json(work / ('full-entry-' + a.full_entry + '.json'))
    ledger = read_json(evidence / 'pnr-history.json') or read_json(evidence / 'search-budget.json')
    library = read_json(root / 'skills/manifest.json')
    receipt = read_json(root / 'SKILLS_DELIVERY.json')
    board = read_json(root / 'docs/validation/cpu80-board-20261019/result.json')
    cpu75_restore = (read_json(root / 'docs/validation/cpu75-restore-20261020/result.json') or
                     read_json(root / 'build/restore75-20261020/retry-owner.json'))
    run = snap.get('run_id', '未生成')
    phase = '尚无当前run原生阶段日志'
    phase_log = a.native_root / 'pds/input-snapshots' / run / 'pds.stdout.log'
    if phase_log.is_file():
        markers = re.findall(r'(?m)^(?:Phase\s[^\r\n]+|Start [^\r\n]+|Process "[^"\r\n]+"[^\r\n]*)',
                             phase_log.read_text(errors='replace'))
        phase = markers[-1] if markers else '原生日志存在，尚无阶段标记'
    for label, obj in [('native', native), ('full-entry', full), ('board', board)]:
        if obj and obj.get('run_id') and obj['run_id'] != run:
            raise ValueError(label + ' belongs to another run; choose matching paths')
    if cpu.get('rtl_sha256') and cpu['rtl_sha256'] != source.get('sha256'):
        raise ValueError('CPU unit test does not bind selected RTL')
    resource = read_json(a.resource_root / 'pds/build_snapshot.json')
    # A staged PnR directory can already match all synthesis inputs while its
    # own native run/snapshot does not exist yet. Report that phase explicitly.
    inputs = snap.get('inputs') or resource.get('inputs', {})
    for name, digest in inputs.items():
        path = a.native_root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('selected candidate input differs from frozen source: ' + name)
    same = bool(inputs) and inputs == resource.get('inputs')
    input_phase = '' if snap.get('inputs') else '（综合冻结输入逐项复核；native快照尚未生成）'
    last_accepted = ('80 MHz；本轮原生/板测及HDMI已确认'
                     if active_final.get('all_native_final_gates_pass') is True and
                     active_board.get('performance_nonregression_gate') == 'PASS_SAME_SESSION_COREMARK_NNUE_DENSE' and
                     active_board.get('hdmi_visual') == 'USER_CONFIRMED' and
                     active_board.get('programming') == 'PASS_VOLATILE_CRAM_DONE1'
                     else '75 MHz；新80 MHz验收以本轮板测证据为准')
    cpu_log = work / Path(a.cpu_test).with_suffix('.log')
    suites = '?'
    if cpu_log.is_file() and hashlib.sha256(cpu_log.read_bytes()).hexdigest() == cpu.get('log_sha256'):
        count = re.search(r'Suites: completed (\d+), aborted 0', cpu_log.read_text(errors='replace'))
        if count:
            suites = count[1]
    if native.get('all_native_final_gates_pass') is True:
        sta = ('已约束全角通过；CPU setup ' + str(native['cpu_setup_wns_ns']) +
               ' ns；CPU hold慢/快 ' + str(native['cpu_slow_hold_wns_ns']) + '/' +
               str(native['cpu_fast_hold_wns_ns']) + ' ns；仍须板测及披露既有I/O缺口')
    elif native:
        sta = '最终未通过：' + str(native.get('status'))
    else:
        sta = '尚未产生本轮最终全角报告，不能认定80 MHz通过'
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    rows = [
        ('快照更新时间', now + '（Asia/Shanghai）'),
        ('当前用户目标', str(a.target_hz) + ' Hz；已验收频率仍见下方80MHz凭据'),
        ('当前目标工作树', str(a.target_cpu) + '；SoC=' + str(a.target_soc)),
        ('当前目标当前配置声明', str(target_clock.get('cpu_hz', '未知')) + ' Hz；配置不是验收'),
        ('当前目标时钟厂商模型', target_pll.get('status', '未完成') + '；不代表原生STA或实板锁定'),
        ('当前目标本地冻结实现', target_freeze.get('cpu_commit', '未冻结') + '；RTL=' + target_freeze.get('rtl_sha256', '未生成') + '；不是验收'),
        ('当前目标 SoC本地冻结实现', target_records.get('soc-freeze', {}).get('soc_implementation_commit', '未冻结') + '；不是验收'),
        ('当前目标原生根/run', str(a.target_native_root) + '；' + str(target_snapshot.get('run_id', '尚未冻结')) + '；须核对真实进程与最终报告'),
        *[('当前目标阶段 ' + name, str(obj.get('status', '未完成')) +
           ('；PID=' + str(obj['pid']) + '（须核对真实命令）' if 'pid' in obj else ''))
          for name, obj in target_records.items()],
        ('当前优化源码', str(a.active_cpu) + '；' + a.active_description),
        ('当前优化冻结实现', active_freeze.get('cpu_commit', '未冻结') + '；RTL=' + active_freeze.get('rtl_sha256', '未生成')),
        ('当前优化旧实现对照', active_baseline.get('status', '未启动')),
        ('当前优化改版定向', active_focus.get('status', '未启动')),
        ('当前优化配对生成', active_pair.get('status', '未启动')),
        ('当前优化完整CPU回归', active_full.get('status', '未启动') + '；tests=' + str(active_full.get('tests', '?'))),
        ('当前优化综合资源', active_resource.get('status', '未启动') + '；phase=' + active_resource.get('phase', '未生成')),
        ('当前优化完整Windows', active_windows.get('status', '未启动')),
        ('当前同固件RTL CoreMark周期', active_cycles.get('status', '未运行') + '；短夹具非实板分数'),
        ('当前优化原生owner', active_native.get('status', '未启动') + '；PID=' + str(active_native.get('pid', '?'))),
        ('当前优化原生根/run', str(a.active_native_root) + '；' + active_snapshot.get('run_id', '尚未创建原生快照')),
        ('当前优化原生日志阶段', active_phase + '；不是最终STA结论'),
        ('当前优化原生输入绑定', str(len(active_snapshot.get('inputs', {}))) + '项；有快照时已核对与综合输入及当前文件完全一致'),
        ('当前优化离线流程', active_flow.get('status', '未启动') + '；PID=' + str(active_flow.get('pid', '?'))),
        ('当前优化正式全角STA', active_final.get('status', '尚无最终报告') + '；CPU setup=' + str(active_final.get('cpu_setup_wns_ns', '?')) + 'ns'),
        ('当前板测准备', active_preparation.get('status', '尚无准备记录')),
        ('当前独立审查', active_review.get('status', '无本轮独立审查归档')),
        ('最近板卡只读连接检查', connection_status + '；不是板测验收'),
        ('当前实板作业', active_board_work.get('status', '未启动') + '；phase=' + active_board_work.get('phase', '无') + '；PID=' + str(active_board_work.get('pid', '?')) + '；需另查真实进程'),
        ('当前CoreMark固定复测及恢复', active_board_repeat.get('status', '未启动') + '；phase=' + active_board_repeat.get('phase', '无') + '；PID=' + str(active_board_repeat.get('pid', '?')) + '；不代表性能门禁通过'),
        ('当前板测验收', active_board.get('status', '无本轮板测证据')),
        ('同日起点对照47bd9d85完整CPU', control_full.get('status', '未启动') + '；tests=' + str(control_full.get('tests', '?'))),
        ('同日起点对照47bd9d85综合', control_resource.get('status', '未启动') + '；未进入PnR'),
        ('最后完整实板验收', last_accepted),
        ('本次75MHz恢复启动', cpu75_restore.get('status', '尚无本次恢复记录') + '；独立于CPU80验收'),
        ('当前候选时钟声明', f"CPU {active_clocks.get('cpu_hz', '?')} Hz / SYS {active_clocks.get('sys_hz', '?')} Hz；此项仅为配置"),
        ('历史c80p13 native run', run),
        ('历史c80p13 CPU实现', source.get('source_reference_commit', '未读取')),
        ('历史c80p13冻结输入', str(len(inputs)) + input_phase + '；与综合候选完全一致=' + str(same)),
        ('历史c80p13完整CPU回归', str(cpu.get('status', '未生成')) + '；tests=' + str(cpu.get('tests', '?')) + '；suites=' + suites),
        ('历史c80p13构建owner', str(owner.get('status', '未生成')) + '；PID=' + str(owner.get('pid', '?')) + '；child=' + str(owner.get('child_pid', '?'))),
        ('历史c80p13日志最近阶段', phase + '；原文标记，不代表最终STA通过'),
        ('历史c80p13自动后处理', str(post.get('status', '未生成')) + '；PID=' + str(post.get('pid', '?'))),
        ('MAC资源优化基线', str(resource_task.get('status', '未启动')) + '；' + str(resource_task.get('phase', '')) + '；该资源owner不启动PnR'),
        ('MAC复用基线完整Windows入口', str(resource_full.get('status', '未启动')) + '；旧r10b输入绑定，新CPU入口另列'),
        ('历史IB候选定向检查', str(new_cpu_focus.get('status', '未启动'))),
        ('历史IB候选配对生成', str(new_cpu_pair.get('status', '未启动'))),
        ('历史IB候选完整回归', str(new_cpu_unit.get('status', '未启动'))),
        ('历史IB候选综合门禁', str(new_cpu_synth.get('status', '未启动')) + '；仅综合资源'),
        ('历史IB候选Windows入口', str(new_cpu_windows.get('status', '未启动')) + '；绑定r11d；旧c/full15失败保留'),
        ('历史IB候选只读诊断', str(new_cpu_native_diag.get('status', '未启动')) + '；不能追认旧失败快照'),
        ('ALU carry-in表示试验', str(carry_pair.get('cpu_commit', '未生成')) + '；映射无预期链深改善，不进入PnR'),
        ('carry-in完整135项回归', str(carry_unit.get('status', '未启动'))),
        ('carry-in资源/原生门禁', str(carry_resource.get('status', '未启动')) + '；不启动PnR'),
        ('ALU分组前缀新候选', str(prefix_pair.get('cpu_commit', '未生成')) + '；' + str(prefix_pair.get('status', '未启动'))),
        ('前缀候选完整135项回归', str(prefix_unit.get('status', '待实际映射核对'))),
        ('前缀候选资源/原生门禁', str(prefix_resource.get('status', '未启动')) + '；不启动PnR'),
        ('前缀候选完整Windows入口', str(prefix_windows.get('status', '未启动'))),
        ('独立仲裁辅助候选', str(rs_pair.get('cpu_commit', '未冻结')) + '；' + str(rs_pair.get('status', '未启动'))),
        ('辅助候选资源预检查', str(rs_resource.get('status', '未启动')) + '；不启动PnR'),
        ('辅助候选完整138项回归', str(rs_unit.get('status', '待实际映射核对'))),
        ('辅助候选完整Windows入口', str(rs_windows.get('status', '未启动'))),
        ('并行等值比较候选', str(eq_pair.get('cpu_commit', '未冻结')) + '；' + str(eq_pair.get('status', '未启动'))),
        ('等值比较定向检查', str(eq_focus.get('status', '未启动')) + '；6项/3套件、168448组全ALU输出对照'),
        ('等值比较完整138项回归', str(eq_unit.get('status', '未启动'))),
        ('等值比较综合门禁', str(eq_resource.get('status', '未启动')) + '；无PnR'),
        ('等值比较完整Windows入口', str(eq_windows.get('status', '未启动'))),
        ('执行单元分支等值新候选', str(br_pair.get('cpu_commit', '未冻结')) + '；' + str(br_pair.get('status', '未启动'))),
        ('分支消费者旧实现基线', str(br_base.get('status', '未启动')) + '；16384周期/4次复位/256分支掩码'),
        ('分支消费者定向检查', str(br_focus.get('status', '未启动'))),
        ('分支消费者完整139项回归', str(br_unit.get('status', '未启动'))),
        ('分支消费者综合门禁', str(br_resource.get('status', '未启动')) + '；无PnR'),
        ('分支消费者完整Windows入口', str(br_windows.get('status', '未启动'))),
        ('分支消费者后续离线流程', str(br_flow.get('status', '未启动')) + '；PID=' + str(br_flow.get('pid', '?')) + '；全部正确性通过后才PnR，禁止编程/推送'),
        ('历史c80p13最终STA', sta),
        ('历史c80p13配对Windows入口', full.get('status', '无历史native配对入口')),
        ('历史20261019归档板测', board.get('status', '无历史板测；不代表本轮80 MHz通过')),
        ('PnR启动统计', str(len(ledger.get('attempts', []))) + '；仅历史统计，无次数或累计期限限制'),
        ('当前ZIP绑定交付', active_delivery.get('status', '尚无完成回执') + '；SHA256=' + active_delivery.get('archive_sha256', '未绑定')),
        ('当前主分支发布', active_publication.get('status', '尚无远程核验回执')),
        ('技能/交付清单revision', str(library.get('revision', '?')) + '/' + str(receipt.get('revision', '?'))),
        ('远程推送门禁', '硬件验收后推送；完整验证并交付后可合入CPU/SoC main，同步README及证据；交接/流程及维护工具可独立推送'),
    ]
    retained_labels = {'当前同固件RTL CoreMark周期','当前板测准备','当前独立审查',
                       '当前实板作业','当前CoreMark固定复测及恢复','当前板测验收',
                       '当前候选时钟声明','当前ZIP绑定交付','当前主分支发布'}
    rows = [(k.replace('当前优化', '已验收80MHz', 1) if k.startswith('当前优化') else
             k.replace('当前', '已验收80MHz', 1) if k in retained_labels else k, v)
            for k, v in rows]
    sd80_path = root / 'artifacts/cpu80_sd_20261021_v2/manifest.json'
    sd80 = read_json(sd80_path)
    if sd80:
        rows.append(('CPU80整合SD启动包', str(sd80.get('status', '未完成')) +
                     '；artifacts/cpu80_sd_20261021_v2/sd-root；18项离线检查，实卡/实板待验，原RAM验收不变'))
    table = '## 当前状态快照\n\n| 项目 | 状态 |\n|---|---|\n'
    table += ''.join('| ' + str(k).replace('|', '\\|') + ' | ' + str(v).replace('|', '\\|') + ' |\n' for k, v in rows)
    table += ('\n来源：当前候选 `pds/build_snapshot.json`、`rtl/cpu/source.json`、上述owner、'
              '完整CPU回归收据、原生归档及技能manifest。进程是否仍存活必须另查命令行与启动时间。\n')
    text = doc.read_text(encoding='utf-8')
    begin, end = '<!-- CPU_HANDOFF_STATUS_BEGIN -->', '<!-- CPU_HANDOFF_STATUS_END -->'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('handoff status markers missing or duplicated')
    text = re.sub(re.escape(begin) + r'[\s\S]*?' + re.escape(end),
                  lambda _: begin + '\n' + table + '\n' + end, text, count=1)
    doc.write_text(text, encoding='utf-8')
    print(json.dumps({'status': 'CPU_HANDOFF_STATUS_REFRESHED',
                      'active_run_id': active_snapshot.get('run_id'), 'historical_run_id': run,
                      'path': str(doc), 'sha256': hashlib.sha256(doc.read_bytes()).hexdigest(),
                      'build_started': False, 'board_accessed': False, 'remote_pushed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
