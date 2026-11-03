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


def refresh_cpu78(a):
    """Refresh the source-bound CPU78 synthesis/PnR result without promoting it."""
    if a.target_hz != 78000000 or a.target_soc.name != 'source':
        return False
    work = a.target_work
    native = a.target_native_root
    status = read_json(work/'status.json')
    snapshot = read_json(native/'pds/build_snapshot.json')
    run_id = snapshot.get('run_id')
    run_dir = native/'pds/input-snapshots'/str(run_id)
    timing = native/'pds/place_route/soc_top_timing_summary_after_hold_fix.txt'
    if not status or not snapshot or not timing.is_file():
        raise ValueError('CPU78 status, native snapshot, or final timing summary is missing')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source_commit=__import__('subprocess').check_output(['git','-C',str(a.target_soc),'rev-parse','HEAD'],text=True).strip()
    if status.get('native_run') != run_id or status.get('source_commit') != source_commit:
        raise ValueError('CPU78 status and native source/run identity differ')
    if status.get('pnr_snapshot_sha256') != sha(native/'pds/build_snapshot.json'):
        raise ValueError('CPU78 PnR snapshot hash differs from status receipt')
    text=timing.read_text(errors='replace')
    rows=[
        ('Updated UTC',datetime.now(timezone.utc).isoformat()),
        ('Request','78 MHz CPU synthesis and place/route; isolated candidate only'),
        ('Candidate',str(work)+'; source commit='+source_commit),
        ('Clock','78 MHz CPU / 49.5 MHz SYS; dedicated1053frac; 1053 MHz VCO; CPU FDC 12.820 ns'),
        ('Native run',str(run_id)+'; snapshot SHA256='+sha(native/'pds/build_snapshot.json')),
        ('Synthesis','PASS; LUT 45170/66600, FF 30407/133200, LUTRAM 2962/19900, DRM 136.5/155'),
        ('Place/route','PDS reports placed and routed successfully; detailed route reached 0 unrouted nets'),
        ('Final STA','FAIL: '+text.splitlines()[0]+'; CPU slow-corner setup WNS -0.444 ns, TNS -2.114 ns, 6 endpoints; fast-corner CPU setup WNS +4.561 ns; CPU hold slow +0.004 ns, fast +0.000 ns'),
        ('Final report',str(timing)+'; SHA256='+sha(timing)),
        ('Native audit','FAILED_NATIVE_PRESERVED: DDR RCF references invalid net u_cpu/u_cpu_wrapper/u_cpu/core/_N116458; strict unique-priority execution audit rejected the run'),
        ('Board and release','No board programming, remote push, delivery package, or hardware acceptance'),
        ('Recovery','Preserve this run and all synthesis screens. New candidate inputs must correct the frequency-specific DDR RCF mapping and address the -0.444 ns CPU setup miss before another PnR claim.'),
    ]
    doc=Path(__file__).resolve().parents[1]/'docs/CPU_Frequency_Handoff.md'
    raw=doc.read_bytes();source=raw.decode('utf-8-sig')
    begin,end='<!-- CPU_HANDOFF_STATUS_BEGIN -->','<!-- CPU_HANDOFF_STATUS_END -->'
    if source.count(begin)!=1 or source.count(end)!=1:raise ValueError('handoff status markers missing or duplicated')
    table='## Current source-bound status\n\n| Item | Evidence |\n|---|---|\n'+''.join('| '+str(k).replace('|','\\|')+' | '+str(v).replace('|','\\|')+' |\n' for k,v in rows)
    block=begin+'\n'+table+'\n'+end
    if b'\r\n' in raw:block=block.replace('\n','\r\n')
    source=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,source,count=1)
    doc.write_bytes(source.encode('utf-8'))
    print(json.dumps(dict(status='CPU78_HANDOFF_SOURCE_BOUND_REFRESHED_STA_FAILED',run_id=run_id,timing_sha256=sha(timing),path=str(doc),build_started=False,board_accessed=False,remote_pushed=False),ensure_ascii=False))
    return True


def refresh_pds25(work):
    """Refresh the isolated PDS25 trial without promoting its native results."""
    source = work / 'source'
    status = read_json(work / 'status.json')
    frozen = read_json(work / 'frozen-inputs.json')
    for name, expected in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest() != expected:
            raise ValueError('PDS25 frozen input changed: '+name)
    probe = read_json(work.parent/'pds25-cpu80-20261031-01/mcp-flow-05/result.json')
    legacy = read_json(work.parent/'pds25-cpu80-20261031-03/status.json')
    begin, end = '<!-- PDS25_CPU80_20261031_BEGIN -->', '<!-- PDS25_CPU80_20261031_END -->'
    block = '\n'.join([begin, '## PDS 2025.2 / CPU80 独立布线候选（2026-10-31）', '',
        f"候选 `{work.as_posix()}`；状态 `{status.get('status')}`。CPU80/SYS49.5，CPU约束12.495ns；来源 `{frozen['source_commit']}`，08候选的522项输入逐项SHA一致，CPU/RTL/模型/时钟/例外保持。",
        f"原生run `{status.get('native_run', 'PENDING')}`；当前命令 `{status.get('current_command', 'PENDING')}`；控制器PID线索 {status.get('owner_pid', '?')}。恢复时须fresh核对进程命令行/启动时间，不能据此重复启动或停止其他作业。",
        f"现有便携MCP实测 `{probe.get('status', 'PENDING')}`，非mock的小电路compile/ADS/map/PnR/report_timing完成。此结果不代表整机CPU80通过。",
        'PDS25工具：`G:/fpga/PDS_2025.2-ads-win64/pango/PDS_2025.2-ads/bin/pds_shell.exe`，2025.2 build211867。旧-parsetcl/model3在最小架构工程复现signal11；旧模式performance无效，新版仅normal/fast。新版使用显式XML RTL/ADS工程及200ps两种时钟路径hold阈值；不声称与旧迭代参数一一等价。',
        '01目录保留全部接口探针及旧入口失败。02通过MCP执行实际整机新流程；原生输出在source/pds/prj_tasks/。综合、资源/CPU边界/DDR/加速器审计、布线、最终慢快setup/hold及板测分别验收。尚未通过的检查不得写成通过。',
        '最终结论：02新综合LUT42650/FF31353/LUTRAM2234/DRM122/APM76；保护123个CPU FF和32位resident key保留，路径6/6/6/3对旧7/5/7/3，未通过旧生产语义审计。dev_map退出1：DRC-0034拒绝RGMII TX IODELAY的DELAY_SEL=1；PORT、TDELAY_EN=TRUE和PARAMETER三种小电路均复现，改0虽映射通过却改变延时，不采用。',
        f"03旧映射库重布线：`{legacy.get('status', 'PENDING')}`。native-03成功注册原FDC/RCF/PCF，PnR读原生旧map ADF报DB-0064格式不兼容，未进入布局布线；不能用旧库绕过新版DRC。",
        '汇总 `G:/fpga/build/pds25-cpu80-20261031-02/RESULTS.md` 和result.json绑定13份核心证据SHA。当前完整CPU80布线、最终STA、板测都未通过。后续先确定保持TX动态延时语义的PDS25合法IOLDELAY迁移，再新冻结/审计/布线；保留全部失败，不能跳DRC或放宽约束。',
        '恢复入口：run_synthesis_mcp.py、synthesis-01/result.json、synthesis-client.log；新控制器/命令与工具哈希单独绑定，不改写旧冻结输入。未访问UART/JTAG/SD/Flash，未推送或制作正式包。',
        end])
    for doc in (Path('G:/fpga/HANDOFF.md'), Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'), source/'docs/CPU_Frequency_Handoff.md'):
        text = doc.read_text(encoding='utf-8-sig')
        if begin in text:
            if text.count(begin) != 1 or text.count(end) != 1:
                raise ValueError('PDS25 handoff marker ambiguity')
            text = re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end), lambda _: block, text, count=1)
        else:
            text = block+'\n\n'+text
        crlf = b'\r\n' in doc.read_bytes()
        payload = text.replace('\r\n','\n').encode('utf-8')
        doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_SOURCE_BOUND_HANDOFF_REFRESHED', hardware_acceptance=False)))


def refresh_pds25_fix(work):
    source=work/'source'
    frozen=read_json(work/'frozen-inputs.json');state=read_json(work/'status.json')
    for name,h in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=h:
            raise ValueError('PDS25 fix source changed: '+name)
    marker='PDS25_CPU80_FIX_20261031'
    begin,end='<!-- '+marker+'_BEGIN -->','<!-- '+marker+'_END -->'
    block='\n'.join([begin,'## 当前PDS25 CPU80：RGMII兼容修复（2026-10-31）','',
        f"用户已授权自行修改后布线。候选 `{work.as_posix()}`，来源 `{frozen['source_commit']}`；状态 `{state.get('status')}`；命令 `{state.get('current_command','PENDING')}`，run `{state.get('native_run','PENDING')}`；控制器PID线索 {state.get('owner_pid','?')}。恢复须核对真实命令和创建时间。",
        'CPU80/SYS49.5、12.495ns/11.695ns和原FDC时序约束保持。CPU/加速器/模型/固件未改。修改TX为DELAY_SEL=0合法单链，二进制步数翻倍后Gray编码；默认100保持厂商模型1ns延时；TX请求范围现为0..123，超范围限幅并读回有效值，RX保持。这个范围缩小是明确的能力变化，旧失败输入不改写。',
        'eth-tests-portable-02：256设置/512厂商模型边沿、MMIO默认/限幅/字节写使能/读回、完整帧/FCS和100M字节对齐通过；原实现负例被拒绝。新测试已接入run_all_tests。未重跑无关CPU/模型完整回归，按精确输入复用；新版原生映射、语义检查和最终布线STA仍须分别记录，不把待验审计写通过。',
        '旧01/02/03的接口崩溃、DRC-0034和DB-0064证据原样保留。04使用新RTL重新综合映射；不绕过DRC，不强读旧DB，不以降频/新false path收敛。新工具物理对象与历史PCF/RCF逐项核对。',
        '04当前综合LUT42683/FF31352/LUTRAM2234/DRM122/APM76；新映射DRC通过。保留20条实际网络优先级，8条旧打包网不存在而移除；保留30条CSR+1条TAGE位置约束，移除的是不存在的CSR N1131/gateop。原生GPLL/参考/标签及123个保护FF、resident key32位检查通过；完整旧CPU控制锥/CDC原生审计仍待迁移，不能把实验布线写成全部正确性/板测验收。',
        'pnr-01曾因新增PCF替换原生PCF而缺失IO约束，已确认owner后停止，全部原日志/控制器/中断回执保留。pnr-preflight-03将完整原生PCF作为字节前缀，165端口和168条原生约束逐条保留后追加31位置约束。pnr-02已完成布局、布线和route optimize，原生日志无E错误和unspecified I/O提示。seed3/decongestion4/normal、两种hold阈值200ps；单作业4小时，无累计预算。',
        '最终STA失败：18时钟周期与原输入一致，保留全部128条汇总（旧116条没有丢失，新工具增加12条跨域hold/DDR skew）。CPU慢角setup WNS -2.793ns、TNS -4631.252ns、4962/58141违规端点；慢hold +0.019ns、快setup +2.874ns、快hold +0.011ns。另有DDR/RGMII/CPU-SYS setup及跨域hold违规，共11条失败汇总；不得仅凭max-skew通过或布通宣布CPU80可用。详见final-review-02/result.json和原生report_timing/soc_top.rtr。',
        'physical-verification-04回读165管脚、31位置（30 CSR gopLUT6Q同CLM配对FY/FF槽位、1 TAGE DRM）、20实际优先网络及20条已报告max-skew顶层组均通过。完整48条CDC指令实际对象与新增hold分析仍须迁移核验；这不是完整CDC/CPU/PMA语义通过。failure-analysis-01资源优先分析：相对旧工具LUT -2510、LUTRAM -728、DRM -14.5、APM -25、FF +950；CPU最差ROB/LSU/issue/ALU0路径12级、布线12.103ns占82.02%、skew -0.236ns，假设零skew仍约-2.557ns。后续先核验CDC端点和语义，再按实际扇出/消费端布局处理，保留123保护FF与key32，不盲换seed/PLL相位。',
        '入口：RESULTS.md、result.json、evidence-manifest.json、run_pnr_mcp_02.py、pnr-client-02.log、pnr-02/result.json、pnr-preflight-03/result.json、frozen-inputs.json及source/docs/PDS25_CPU80_Migration.md。最终失败候选完整保留，当前未上板、生成位流、写卡/Flash、推送或交付；新源码/模型副本、构建、tmp和证据全部G:/fpga。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        crlf = b'\r\n' in doc.read_bytes()
        text=doc.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload = text.replace('\r\n','\n').encode('utf-8')
        doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_FIX_SOURCE_BOUND_HANDOFF_REFRESHED',hardware_acceptance=False)))


def refresh_pds25_opt(work):
    frozen=read_json(work/'frozen-inputs.json'); state=read_json(work/'status.json')
    source=work/'source'
    for name,h in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=h:
            raise ValueError('PDS25 optimization source changed: '+name)
    marker='PDS25_CPU80_OPTIMIZATION'
    begin,end='<!-- '+marker+'_BEGIN -->','<!-- '+marker+'_END -->'
    block='\n'.join([begin,'## 当前CPU80正WNS优化（2026-10-31）','',
        '用户要求优化直到WNS为正，并保持CoreMark与加速器性能。保持CPU80/SYS49.5、CPU12.495ns/CDC11.695ns及I/O约束；正式验收须全角全部约束通过，CoreMark/MHz同轮全部样本均值下降不超过0.05、官方加速器性能不退步。',
        f"当前候选 `{work.as_posix()}`，冻结 `{frozen['source_commit']}`，状态 `{state['status']}`，run `{state.get('native_run','PENDING')}`。命令 `{state.get('current_command','PENDING')}`，owner PID线索 {state.get('owner_pid','PENDING')}，恢复须核对真实命令/创建时间。",
        '父04最终CPU慢角setup -2.793ns，另有DDR/RGMII/跨域违规，资源优先分析与原始证据保留。发现新版FIFO storage_N_x2x4拆分后的部分物理切片未继承原CDC约束，原综合SDC标签仍在WCLK，因此不能仅凭综合标签宣称最终覆盖。',
        frozen.get('native_controller_delta',frozen.get('scope','PENDING')),
        state.get('conclusion','当前为综合筛选：先检查资源、组合深度、保护边界及实际CDC覆盖；未通过检查不启动完整PnR。'),
        '用户2026-10-31最新安排：先反馈最终时序报告，等待用户另行通知才上板；即使设备重新枚举也不得自动启动板端操作。' if state.get('board_deferred_by_user') else '板端安排以当前用户授权和实际连接状态为准。',
        '05全局关闭RAM流水筛选已淘汰：LUT64749/66600、LUTRAM19002/19900，未启动PnR。其synthesis-01曾因旧GUI准备器拒绝新Tcl配方而停止；所有失败与完整筛选证据保留。06仅追加5条精确CDC storage映射属性，原48条CDC指令不变。新副本/临时目录/构建全部在G:/fpga。未完成原生资格审计、最终全角STA和板端性能前，不声明性能不变或发布通过。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        crlf=b'\r\n' in doc.read_bytes();text=doc.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload=text.replace('\r\n','\n').encode('utf-8');doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_OPTIMIZATION_SOURCE_BOUND_HANDOFF_REFRESHED',hardware_acceptance=False)))


def refresh_pds25_cpu85(work):
    source=work/'source';frozen=read_json(work/'frozen-inputs.json');state=read_json(work/'status.json')
    for name,h in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=h:raise ValueError('CPU85 frozen input changed: '+name)
    begin,end='<!-- PDS25_CPU85_TRIAL_BEGIN -->','<!-- PDS25_CPU85_TRIAL_END -->'
    block='\n'.join([begin,'## 当前PDS25 CPU85试验（2026-10-31）','',
        '用户在CPU80全角通过后要求“再试试85mhz”。CPU80候选06的原生报告、源码和位流完整保留，不替换为85版本。',
        f"候选 `{work.as_posix()}`，冻结 `{frozen['source_commit']}`，状态 `{state['status']}`，run `{state.get('native_run','PENDING')}`；命令 `{state.get('current_command','PENDING')}`，owner PID线索 {state.get('owner_pid','PENDING')}。恢复须核对真实进程命令与创建时间。",
        '精确85MHz既有dedicated1147p5frac配置：27MHz参考、VCO1147.5MHz、CLKOUT0 /13.5、50%占空比；CPU严格11.760ns、CDC10.960ns。SYS49.5MHz/时基、显示和加速器配置保持；CPU Chisel/生成RTL及模型未改，五个FIFO寄存器映射属性保持。',
        '时钟配置/85MHz策略负例/厂商周期与占空比/行为模型对照通过；五套固件重建后Assert-FpgaFirmware通过。当前bootloader与四套辅助固件BIN/ELF字节仍与CPU80一致（频率由硬件运行时报告），新的来源元数据和85MHz DTS/DTB单独绑定。',
        state.get('conclusion','本轮原生综合/映射/完整PnR/最终全角STA各阶段分别验收，最新结果见status.json；不把综合完成或中间WNS当成时序通过。'),
        '性能合同保留CoreMark/MHz同轮全样本均值绝对下降≤0.05、官方Pikafish/图像加速器不退步；本轮未上板，不能给85MHz继承80MHz的性能或时序通过。',
        '用户仍要求等待另行通知才上板；不得扫描JTAG、开串口、编程或写SD/Flash。本轮只做隔离离线验证，未推送/交付。新源码/构建/tmp全部G:/fpga；无累计PnR预算，单作业4小时，保留失败与恢复证据。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        crlf=b'\r\n' in doc.read_bytes();text=doc.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload=text.replace('\r\n','\n').encode('utf-8');doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_CPU85_SOURCE_BOUND_HANDOFF_REFRESHED',hardware_acceptance=False)))


def refresh_pds25_cpu90(work):
    source=work/'source';frozen=read_json(work/'frozen-inputs.json');state=read_json(work/'status.json')
    for name,h in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=h:raise ValueError('CPU90 frozen input changed: '+name)
    begin,end='<!-- PDS25_CPU90_TRIAL_BEGIN -->','<!-- PDS25_CPU90_TRIAL_END -->'
    block='\n'.join([begin,'## 当前PDS25 CPU90试验（2026-10-31）','',
        '用户要求“继续90mhz，一并测试”。CPU85候选01全角STA通过，CPU慢setup/hold +0.643/+0.123ns，快setup/hold +4.665/+0.088ns；物理回读通过，候选位流已生成。CPU80候选06慢setup +0.783ns，源码/报告/位流继续完整保留。两版新PDS候选均未上板，不继承历史性能验收。',
        f"当前候选 `{work.as_posix()}`，冻结 `{frozen['source_commit']}`，状态 `{state['status']}`，run `{state.get('native_run','PENDING')}`；命令 `{state.get('current_command','PENDING')}`，owner PID线索 {state.get('owner_pid','PENDING')}。恢复须核对真实进程命令与创建时间。",
        '精确90MHz采用既有mode4：27MHz参考、VCO1080MHz、CLKOUT0 /12、50%占空比，编码CPU_DIVISOR24。仅扩展受限软件策略/独立时钟检查器；CPU核、PLL实现和加速器/模型RTL保持。CPU严格11.100ns（物理100/9ns）、CDC10.300ns；与SYS20.202ns按91:50周期精确展开。SYS/CLINT49.5MHz、显示/DDR、48条原始CDC指令及五个FIFO寄存器映射保持。',
        '90MHz策略与六个负例、1024边沿厂商周期/占空比、七组行为/厂商模型及实际SoC复位/丢锁/三拍释放检查通过；五套固件重建及清单校验通过。当前BIN/ELF仍与CPU85一致，DTS/DTB及来源元数据独立绑定。',
        state.get('conclusion','原生综合/映射/完整PnR/最终快慢角STA和物理回读分别记录；中间WNS不能作为最终通过。完整新版CPU控制/PMA/CDC原生oracle迁移仍为单独待验门禁。'),
        'CoreMark/MHz同轮全样本均值下降上限0.05；官方Pikafish Stage A/B/权重缓存、图像及并发性能须实板验收。本轮只做离线试验，收到用户另行通知后才上板；不得扫描JTAG、开串口、编程或写SD/Flash。未推送/正式交付。全部新增源码/构建/tmp在G:/fpga；无累计PnR预算，单作业4小时。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        crlf=b'\r\n' in doc.read_bytes();text=doc.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload=text.replace('\r\n','\n').encode('utf-8');doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_CPU90_SOURCE_BOUND_HANDOFF_REFRESHED',hardware_acceptance=False)))


def refresh_pds25_cpu95(work):
    source=work/'source';frozen=read_json(work/'frozen-inputs.json');state=read_json(work/'status.json')
    for name,h in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=h:raise ValueError('CPU95 frozen input changed: '+name)
    prior=[]
    for freq,name in [(80,'pds25-cpu80-20261031-06'),(85,'pds25-cpu85-20261031-01'),(90,'pds25-cpu90-20261031-01')]:
        sta=read_json(work.parent/name/'final-review-02/result.json')
        if sta:
            cpu={x['corner']+' '+x['check']:x['wns_ns'] for x in sta['cpu_timing']}
            prior.append(f"CPU{freq}: final STA={sta['final_sta_pass']}; slow setup/hold {cpu['Slow Setup']:+.3f}/{cpu['Slow Hold']:+.3f}ns; fast setup/hold {cpu['Fast Setup']:+.3f}/{cpu['Fast Hold']:+.3f}ns")
    begin,end='<!-- PDS25_CPU95_TRIAL_BEGIN -->','<!-- PDS25_CPU95_TRIAL_END -->'
    block='\n'.join([begin,'## 当前PDS25 CPU95试验（2026-10-31）','',
        '用户要求“继续布线95mhz一并测试”。此前80/85/90三版原生全角STA与物理回读均通过，候选位流及输入/报告独立保留，均未进行本轮实板性能验收。',*prior,
        f"当前候选 `{work.as_posix()}`，冻结 `{frozen['source_commit']}`，状态 `{state['status']}`，run `{state.get('native_run','PENDING')}`；命令 `{state.get('current_command','PENDING')}`，owner PID线索 {state.get('owner_pid','PENDING')}。恢复须核对真实进程命令与创建时间。",
        '精确95MHz新增受限mode7：板上既有125MHz差分参考，经GTP_INBUFDS、输入/5、反馈38，VCO950MHz，CLKOUT0 /10、50%占空比，编码CPU_DIVISOR20。仅CPU PLL参数/参考选择及配套策略/原生检查器扩展；CPU核和加速器/模型逻辑保持。CPU严格10.521ns（物理200/19ns），SYS20.202ns以962:501周期展开，CDC9.721ns。SYS/CLINT49.5MHz、DDR/显示/加速器配置、原48条CDC指令及五个FIFO寄存器映射不变。',
        '95MHz配置和六个策略负例、1024边沿厂商周期/占空比、八组行为/厂商模型、实际SoC复位/丢锁/恢复/三拍释放检查通过；五套固件重建及来源清单校验通过。BIN/ELF与CPU90一致，DTS/DTB及元数据独立绑定。',
        state.get('conclusion','原生综合、映射、完整PnR、最终快慢角STA和物理回读分阶段验证，最新状态见status.json；不把中间WNS或综合通过当最终通过。完整PDS25 CPU控制/PMA/CDC原生oracle迁移仍是单独待验资格门禁。'),
        'CoreMark/MHz同轮全样本均值下降上限0.05，官方Pikafish Stage A/B/权重缓存、图像/并发性能仍须实板确认，不能从源码一致或STA通过推断。用户要求另行通知后才上板：本轮不扫描JTAG、不打开串口、不编程或写SD/Flash。未推送、未制作正式交付包。所有新增源码/构建/tmp在G:/fpga，无累计PnR预算，单作业4小时。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        crlf=b'\r\n' in doc.read_bytes();text=doc.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload=text.replace('\r\n','\n').encode('utf-8');doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_CPU95_SOURCE_BOUND_HANDOFF_REFRESHED',hardware_acceptance=False)))


def refresh_pds25_cpu110_repair(work):
    """Bind the offline110MHz physical repair to exact inputs and native reports."""
    source=work/'source';frozen=read_json(work/'frozen-inputs.json');state=read_json(work/'status.json')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,h in frozen['native_inputs_sha256'].items():
        if sha(source/name)!=h:raise ValueError('CPU110 repair frozen input changed: '+name)
    pre=read_json(work/'pnr-preflight-05/result.json')
    for name,h in pre['route_constraint_sha256'].items():
        if sha(Path(name))!=h:raise ValueError('CPU110 repair route constraint changed: '+name)
    review=read_json(work/'final-review-02/result.json')
    physical=read_json(work/'physical-verification-01/result.json')
    result=state.get('conclusion','最终全角STA/物理回读待完成；不把中间WNS当通过。')
    if review:
        cpu={x['corner']+' '+x['check']:x['wns_ns'] for x in review['cpu_timing']}
        result=f"最终全角STA={review['final_sta_pass']}；CPU慢角setup/hold {cpu['Slow Setup']:+.3f}/{cpu['Slow Hold']:+.3f}ns，快角setup/hold {cpu['Fast Setup']:+.3f}/{cpu['Fast Hold']:+.3f}ns；违规summary行数={len(review['violating_summary_rows'])}；原报告SHA256={state.get('final_report_sha256')}。"
    begin,end='<!-- PDS25_CPU110_WNS_REPAIR_BEGIN -->','<!-- PDS25_CPU110_WNS_REPAIR_END -->'
    change=read_json(work/'priority-change.json')
    block='\n'.join([begin,'## 当前：110MHz WNS修复（2026-11-01）','',
        '用户要求尝试修复已布线110MHz失败候选的WNS；本轮离线修复，100MHz候选继续保留。',
        f"当前目录 `{work.as_posix()}`；源码冻结 `{frozen['source_commit']}`；新run `{state.get('native_run')}`；状态 `{state['status']}`；owner PID线索 {state.get('owner_pid')}、PDS PID线索 {state.get('pds_session_pid')}；恢复须核对实时命令行与启动时间。",
        f"当前命令 `{state.get('current_command')}`。",
        '父版pds25-cpu110-20261101-01最终失败：CPU慢角setup−1.167ns、TNS−334.070ns/1576端点，CPU→SYS−0.336ns，DDR−0.030ns；快角和hold通过。原始报告/数据库/失败证据不改写。',
        f"资源优先评估：综合43599LUT/33705FF/2158LUTRAM/76APM/122DRM36K等效；物理LUT约78%、DRM80%。旧H128已关闭，Stage A/B/权重缓存保留。父版CPU最差路径15级、布线6.803ns，占69.4%。本次在保留原20条优先网基础上新增{len(change.get('added',[]))}条实际失败长弧优先网；精确映射网名核对，seed3/decongestion4/hold200ps不变。",
        '522个原生输入及配对CPU/加速器/模型/固件保持字节一致，复用原生compile/synth/map并核对逐文件SHA256；仅独立RCF布线优先级变化。CPU110MHz、SYS49.5MHz、严格9.087ns/CDC8.287ns、48条CDC指令、五FIFO寄存器映射、165引脚及31固定单元保持。PnR首个控制器因复制项目的历史完成标志被工具跳过，未做布线；pnr-01保留回执，pnr-02用官方-force_to_run重新执行全部物理步骤，正常DRC和约束检查保留。',
        result,
        f"物理回读：{physical.get('status','PENDING')}；详细诊断diagnosis.json、priority-change.json、native-reuse.json、pnr-02/input-binding.json、final-review-02/result.json。",
        '本轮无110MHz板卡访问、远程推送或正式交付；完整PDS25 CPU控制/PMA/CDC工具资格与实板性能仍独立待验。CoreMark/MHz同轮均值绝对下降≤0.05，官方Pikafish/图像/并发性能门禁保留。所有新源码/测试/tmp在G:/fpga；无累计PnR预算，单作业4小时。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        raw=doc.read_bytes();text=raw.decode('utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        text=text.replace('## 当前：保留100MHz、实测100MHz与110MHz布线（2026-11-01）','## 此前：100MHz板测与110MHz首轮布线（2026-11-01）')
        text=text.replace('阶段 `RUNNING_PDS25_FIXED_CPU110_FULL_PLACE_ROUTE`','阶段 `CPU110_FINAL_STA_FAILED_PRESERVED_BOARD_DEFERRED`')
        payload=text.replace('\r\n','\n').encode('utf-8');doc.write_bytes(payload.replace(b'\n',b'\r\n') if b'\r\n' in raw else payload)
    print(json.dumps(dict(status='PDS25_CPU110_REPAIR_SOURCE_BOUND_HANDOFF_REFRESHED',native_run=state.get('native_run'),hardware_acceptance=False)))


def refresh_pds25_cpu100(work):
    source=work/'source';frozen=read_json(work/'frozen-inputs.json');state=read_json(work/'status.json')
    for name,h in frozen['native_inputs_sha256'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=h:raise ValueError('CPU100 frozen input changed: '+name)
    if (work/'board-current.json').is_file() and (work/'board_handoff100.py').is_file():
        # Board evidence follows the sealed offline trial. Preserve its source
        # metadata and refresh only the maintained/root handoff documents.
        import runpy
        runpy.run_path(str(work/'board_handoff100.py'), run_name='__main__')
        return
    prior=[]
    for freq,name in [(80,'pds25-cpu80-20261031-06'),(85,'pds25-cpu85-20261031-01'),(90,'pds25-cpu90-20261031-01'),(95,'pds25-cpu95-20261031-01')]:
        sta=read_json(work.parent/name/'final-review-02/result.json')
        if sta:
            cpu={x['corner']+' '+x['check']:x['wns_ns'] for x in sta['cpu_timing']}
            prior.append(f"CPU{freq}: final STA={sta['final_sta_pass']}; slow setup/hold {cpu['Slow Setup']:+.3f}/{cpu['Slow Hold']:+.3f}ns; fast setup/hold {cpu['Fast Setup']:+.3f}/{cpu['Fast Hold']:+.3f}ns")
    begin,end='<!-- PDS25_CPU100_TRIAL_BEGIN -->','<!-- PDS25_CPU100_TRIAL_END -->'
    block='\n'.join([begin,'## 当前PDS25 CPU100试验（2026-10-31）','',
        '用户要求“布线100mhz，成功再测试；确认仍等通知，先做离线验证”。此前80/85/90/95四版原生全角STA与物理回读均通过，候选位流及输入/报告独立保留，均未进行本轮实板性能验收。',*prior,
        f"当前候选 `{work.as_posix()}`，冻结 `{frozen['source_commit']}`，状态 `{state['status']}`，run `{state.get('native_run','PENDING')}`；命令 `{state.get('current_command','PENDING')}`，owner PID线索 {state.get('owner_pid','PENDING')}。恢复须核对真实进程命令与创建时间。",
        '精确100MHz新增受限mode8：板上既有125MHz差分参考，经GTP_INBUFDS、输入/5、反馈40，VCO1000MHz，CLKOUT0 /10、50%占空比，编码CPU_DIVISOR20。仅CPU PLL参数/参考选择及配套策略/原生检查器扩展；CPU核和加速器/模型逻辑保持。CPU严格9.990ns（物理10ns），SYS20.202ns以91:45周期展开，CDC9.190ns。SYS/CLINT49.5MHz、DDR/显示/加速器配置、原48条CDC指令及五个FIFO寄存器映射不变。',
        '100MHz配置和六个策略负例、1024边沿厂商周期/占空比、九组行为/厂商模型、实际SoC复位/丢锁/恢复/三拍释放检查通过；五套固件重建及来源清单校验通过。BIN/ELF与CPU90一致，DTS/DTB及元数据独立绑定。',
        state.get('conclusion','原生综合、映射、完整PnR、最终快慢角STA和物理回读分阶段验证，最新状态见status.json；不把中间WNS或综合通过当最终通过。完整PDS25 CPU控制/PMA/CDC原生oracle迁移仍是单独待验资格门禁。'),
        'CoreMark/MHz同轮全样本均值下降上限0.05，官方Pikafish Stage A/B/权重缓存、图像/并发性能仍须实板确认，不能从源码一致或STA通过推断。用户要求另行通知后才上板：本轮不扫描JTAG、不打开串口、不编程或写SD/Flash。未推送、未制作正式交付包。所有新增源码/构建/tmp在G:/fpga，无累计PnR预算，单作业4小时。',end])
    for doc in (Path('G:/fpga/HANDOFF.md'),Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),source/'docs/CPU_Frequency_Handoff.md'):
        crlf=b'\r\n' in doc.read_bytes();text=doc.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload=text.replace('\r\n','\n').encode('utf-8');doc.write_bytes(payload.replace(b'\n',b'\r\n') if crlf else payload)
    print(json.dumps(dict(status='PDS25_CPU100_SOURCE_BOUND_HANDOFF_REFRESHED',hardware_acceptance=False)))

def main():
    if '--pds25-cpu125-work' in sys.argv:
        from update_cpu125_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--pds25-cpu125-work')+1]))
        return
    if '--pds25-cpu130-repair-work' in sys.argv:
        from update_cpu130_repair_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--pds25-cpu130-repair-work')+1]))
        return
    if '--pds25-cpu130-work' in sys.argv:
        from update_cpu130_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--pds25-cpu130-work')+1]))
        return
    if '--pds25-cpu120-zbc-fc1-work' in sys.argv:
        import runpy
        queue = Path('G:/fpga/build/pds25-cpu120-zbc-20261101-01/board-delivery-20261101-01')
        runpy.run_path(str(queue/'refresh_wait_state.py'), run_name='__main__')
        runpy.run_path(str(queue/'update_queue_handoff.py'), run_name='__main__')
        return
    cm65_default = Path('G:/fpga/build/cpu120-coremark65-20261101-01')
    if '--cpu120-coremark65-work' in sys.argv or (not sys.argv[1:] and (cm65_default/'status.json').is_file()):
        from update_cpu120_coremark65_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--cpu120-coremark65-work')+1]) if '--cpu120-coremark65-work' in sys.argv else cm65_default)
        return
    zbc120_default = Path('G:/fpga/build/pds25-cpu120-zbc-20261101-01')
    if '--pds25-cpu120-zbc-work' in sys.argv or (not sys.argv[1:] and (zbc120_default/'status.json').is_file()):
        from update_cpu120_zbc_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--pds25-cpu120-zbc-work')+1]) if '--pds25-cpu120-zbc-work' in sys.argv else zbc120_default)
        return
    cm58_default = Path('G:/fpga/build/cpu100-coremark58-20261101-01')
    if '--cpu100-coremark58-work' in sys.argv or (not sys.argv[1:] and (cm58_default/'status.json').is_file()):
        import runpy
        work = Path(sys.argv[sys.argv.index('--cpu100-coremark58-work')+1]) if '--cpu100-coremark58-work' in sys.argv else cm58_default
        runpy.run_path(str(work/'update_handoff.py'), run_name='__main__')
        return
    if '--pds25-cpu120-work' in sys.argv:
        from update_cpu120_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--pds25-cpu120-work')+1]))
        return
    if '--cpu100-offline-work' in sys.argv:
        import runpy
        work = Path(sys.argv[sys.argv.index('--cpu100-offline-work')+1])
        runpy.run_path(str(work/'update_handoff.py'), run_name='__main__')
        return
    candidate100_publication=Path('G:/fpga/build/pds25-cpu100-20261031-01/candidate-handover-20261101-01')
    if not sys.argv[1:] and read_json(candidate100_publication/'publication.json').get('remote_head_verified'):
        import runpy
        runpy.run_path(str(candidate100_publication/'update_publication_handoff.py'), run_name='__main__')
        return
    if '--pds25-cpu110-logic-work' in sys.argv:
        from update_cpu110_logic_handoff import refresh
        refresh(Path(sys.argv[sys.argv.index('--pds25-cpu110-logic-work')+1]))
        return
    gui_sd100=Path('G:/fpga/build/pds25-cpu100-20261031-01/gui100-sd-01')
    if not sys.argv[1:] and (gui_sd100/'session.json').is_file():
        import runpy
        runpy.run_path(str(gui_sd100/'update_handoff.py'), run_name='__main__')
        return
    gui100=Path('G:/fpga/build/pds25-cpu100-20261031-01/gui100-01')
    if not sys.argv[1:] and (gui100/'session.json').is_file():
        import runpy
        runpy.run_path(str(gui100/'update_gui_handoff.py'), run_name='__main__')
        return
    board100=Path('G:/fpga/build/pds25-cpu100-20261031-01')
    if not sys.argv[1:] and (board100/'board-current.json').is_file():
        # User priority: measure CPU100 first; defer further CPU110 work.
        refresh_pds25_cpu100(board100)
        return
    pds25_110_repair=Path('G:/fpga/build/pds25-cpu110-20261101-02')
    if '--pds25-cpu110-work' in sys.argv:
        refresh_pds25_cpu110_repair(Path(sys.argv[sys.argv.index('--pds25-cpu110-work')+1]))
        return
    if not sys.argv[1:] and (pds25_110_repair/'frozen-inputs.json').is_file():
        refresh_pds25_cpu110_repair(pds25_110_repair)
        return
    pds25_100=Path('G:/fpga/build/pds25-cpu100-20261031-01')
    if '--pds25-cpu100-work' in sys.argv:
        refresh_pds25_cpu100(Path(sys.argv[sys.argv.index('--pds25-cpu100-work')+1]))
        return
    if not sys.argv[1:] and (pds25_100/'frozen-inputs.json').is_file():
        refresh_pds25_cpu100(pds25_100)
        return

    pds25_95=Path('G:/fpga/build/pds25-cpu95-20261031-01')
    if '--pds25-cpu95-work' in sys.argv:
        refresh_pds25_cpu95(Path(sys.argv[sys.argv.index('--pds25-cpu95-work')+1]))
        return
    if not sys.argv[1:] and (pds25_95/'frozen-inputs.json').is_file():
        refresh_pds25_cpu95(pds25_95)
        return
    pds25_90=Path('G:/fpga/build/pds25-cpu90-20261031-01')
    if '--pds25-cpu90-work' in sys.argv:
        refresh_pds25_cpu90(Path(sys.argv[sys.argv.index('--pds25-cpu90-work')+1]))
        return
    if not sys.argv[1:] and (pds25_90/'frozen-inputs.json').is_file():
        refresh_pds25_cpu90(pds25_90)
        return
    pds25_85=Path('G:/fpga/build/pds25-cpu85-20261031-01')
    if '--pds25-cpu85-work' in sys.argv:
        refresh_pds25_cpu85(Path(sys.argv[sys.argv.index('--pds25-cpu85-work')+1]))
        return
    if not sys.argv[1:] and (pds25_85/'frozen-inputs.json').is_file():
        refresh_pds25_cpu85(pds25_85)
        return
    pds25_opt=Path('G:/fpga/build/pds25-cpu80-20261031-06')
    if '--pds25-opt-work' in sys.argv:
        refresh_pds25_opt(Path(sys.argv[sys.argv.index('--pds25-opt-work')+1]))
        return
    if not sys.argv[1:] and (pds25_opt/'frozen-inputs.json').is_file():
        refresh_pds25_opt(pds25_opt)
        return
    pds25_work = Path('G:/fpga/build/pds25-cpu80-20261031-04')
    if '--pds25-fix-work' in sys.argv:
        refresh_pds25_fix(Path(sys.argv[sys.argv.index('--pds25-fix-work')+1]))
        return
    if not sys.argv[1:] and (pds25_work/'frozen-inputs.json').is_file():
        refresh_pds25_fix(pds25_work)
        return
    pds25_work = Path('G:/fpga/build/pds25-cpu80-20261031-02')
    if '--pds25-work' in sys.argv:
        pos = sys.argv.index('--pds25-work')
        refresh_pds25(Path(sys.argv[pos+1]))
        return
    if not sys.argv[1:] and (pds25_work/'frozen-inputs.json').is_file():
        refresh_pds25(pds25_work)
        return
    pikafish_sw = Path('G:/fpga/performance_soc_pikafish_sw_20261026/scripts/update_pikafish_sw_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and pikafish_sw.exists():
        import runpy
        runpy.run_path(str(pikafish_sw), run_name='__main__')
        return
    lut_compact = Path('G:/fpga/performance_soc_lut_compact_20261025/scripts/update_lut_compact_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and lut_compact.exists():
        import runpy
        runpy.run_path(str(lut_compact), run_name='__main__')
        return
    voice_efficient = Path('G:/fpga/performance_soc_voice_efficient_20261025/scripts/update_voice_efficient_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and voice_efficient.exists():
        import runpy
        runpy.run_path(str(voice_efficient), run_name='__main__')
        return
    voice_prune = Path('G:/fpga/performance_soc_voice_prune_20261025/scripts/update_voice_prune_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and voice_prune.exists():
        import runpy
        runpy.run_path(str(voice_prune), run_name='__main__')
        return
    hardware_publication = Path('G:/fpga/performance_soc_hw_publish_20261025/scripts/update_hw_publication_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and hardware_publication.exists():
        import runpy
        runpy.run_path(str(hardware_publication), run_name='__main__')
        return
    integer_ops = Path('G:/fpga/performance_soc_integer_ops_20261025/scripts/update_integer_ops_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and integer_ops.exists():
        import runpy
        runpy.run_path(str(integer_ops), run_name='__main__')
        return
    integer_handoff = Path('G:/fpga/performance_soc_integer_hwc_20261025/scripts/update_integer_handoff.py')
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name == 'performance_soc_voice_hw' and integer_handoff.exists():
        import runpy
        runpy.run_path(str(integer_handoff), run_name='__main__')
        return
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name in {
            'performance_soc_transfer_reuse_20261025','performance_soc_voice_hw'}:
        from update_transfer_handoff import main as refresh_transfer
        refresh_transfer()
        detector = Path('G:/fpga/performance_soc_transfer_reuse_20261025/scripts/update_detector_stage_handoff.py')
        if detector.exists():
            import runpy
            runpy.run_path(str(detector), run_name='__main__')
        return
    if not sys.argv[1:] and Path(__file__).resolve().parents[1].name in {
            'performance_soc_image_hwc_20261025','performance_soc_stage_profile_20261025','performance_soc_voice_hw'}:
        from update_image_hwc_handoff import main as refresh_current_offline
        refresh_current_offline()
        return
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target-hz', type=int, default=78000000)
    ap.add_argument('--target-work', type=Path, default=Path('G:/fpga/build/main78-20261030-01'))
    ap.add_argument('--target-cpu', type=Path, default=Path('G:/fpga/build/main78-20261030-01/source'))
    ap.add_argument('--target-soc', type=Path, default=Path('G:/fpga/build/main78-20261030-01/source'))
    ap.add_argument('--target-native-root', type=Path, default=Path('G:/fpga/build/main78-20261030-01/source'))
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
    a = ap.parse_args()
    if refresh_cpu78(a):return
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
