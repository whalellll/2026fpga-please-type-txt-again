from pathlib import Path
import hashlib,json,re

def refresh(work):
 work=Path(work).resolve();R=Path(__file__).resolve().parents[1]
 def read(p):return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 f=read(work/'frozen-inputs.json');q=read(work/'status.json');review=read(work/'final-review-02/result.json');physical=read(work/'physical-verification-01/result.json');resources=read(work/'resource-review-01/result.json');pre=read(work/'pnr-preflight-05/result.json');plan=read(work/'resource-first-plan.json')
 followup=read(work/'resource-first-review.json')
 resource_work=work
 while followup and not resources:
  parent=read(resource_work/'frozen-inputs.json').get('parent_candidate')
  if not parent:break
  resource_work=Path(parent);resources=read(resource_work/'resource-review-01/result.json')
 placement=read(work/'placement-change.json')
 inherited=read(work/'placement-policy-inherited.json')
 fallback=read(work/'fallback-policy.json')
 followup_note=('本轮复用已减少的硬件和71个逐文件核对的native编译/综合/映射输入，不再次改写ETH/CPU或重跑功能测试。03最终CPU−0.244ns/4端点、DDR−0.054ns/3端点；04增加10条实际长弧提示后CPU−0.236ns/5端点、DDR−0.003ns/1端点，仍失败，原报告保留。本轮只释放tagMem2/Memory1继承的DRM_256_30/DRM0固定位置，由原生合法布局选择位置；保留30个CSR位置、165引脚、39路由优先网、seed和全部时钟/例外。resource-first-review.json绑定既有全局−89LUT/−256LUTRAM及123个保护FF/Q边界；最差路径低扇出14、路由占61%，据此选择单个布局因素。' if placement else '本轮复用父03已减少的硬件和71个逐文件核对的native编译/综合/映射输入，不再次改写ETH/CPU或重跑功能测试。03最终CPU−0.244ns/4端点集中TAGE反馈地址，DDR−0.054ns/3端点转到group2，原报告保留。resource-first-review.json核对全局−89LUT/−256LUTRAM、保护边界与低扇出长路由后增加10条实际TAGE/DDR长弧提示；总39条，seed和时钟不变。资源数据来自父03实测。')
 if inherited:
  added=read(work/'priority-change.json').get('added',[])
  followup_note=f"本轮复用已减少的ETH硬件和71个逐文件核对的native编译/综合/映射输入，不再次改写ETH/CPU或重跑功能测试。05释放TAGE硬位置后实际RAM移至DRM_40_30/DRM1，DDR/TAGE违规清零；CPU转为D-cache标签命中反馈−0.263ns/39端点、布线占68%、wayHit扇出73，失败原报告保留。本轮保持该位置策略、30个CSR位置、165引脚和39条父优先网，只新增{len(added)}条实际D-cache负路径长弧；seed、hold、时钟/例外不变。resource-first-review.json绑定全局−89LUT/−256LUTRAM资源收益及123个FF/Q保护边界后选择有证据的路由改动。"
 valid=bool(f) and all(sha(work/'source'/n)==h for g in ['native_inputs_sha256','verification_inputs_sha256'] for n,h in f.get(g,{}).items())
 flows=[p for pattern in ['flow*.json','resource-native-flow.json'] for p in work.glob(pattern)];flow=read(max(flows,key=lambda p:p.stat().st_mtime)) if flows else {}
 begin='<!-- PDS25_CPU130_WNS_REPAIR_BEGIN -->';end='<!-- PDS25_CPU130_WNS_REPAIR_END -->'
 block='\n\n'.join([begin,'## 当前130MHz：资源优先修复，直到最终WNS为正（2026-11-01）',
 ('用户最新纠正：本轮06的130MHz若最终WNS仍未正，停止追加130MHz布线，转入真实125MHz候选`G:/fpga/build/pds25-cpu125-20261101-01`；详见当前`fallback-policy.json`。125计划为已有mode8扩展到encoded16：125MHz参考/5×40/8，1GHz VCO，严格7.992ns、SYS20.202ns、CDC7.192ns，91CPU=36SYS周期。仅为待启用计划，需新时钟/固件/综合映射验收及完整全角STA。' if fallback else '当前仍按活动候选继续修复，最终全角WNS须正。'),
 '用户最新要求“尝试修复直到wns为正”。01从最新发布120MHz da0ff3f2/Zbc+FC1建立，CPU慢setup−0.071ns/2端点、DDR−0.060ns/8端点。02增加15条实际优先网后DDR改善到−0.028ns/1端点，CPU却退化到−0.224ns/51端点，触发更严格−0.1ns资源优先流程。两版原始报告/数据库/失败及内存重跑回执保留，不把DDR改善冒称整机通过。',
 f"活动目录`{work.as_posix()}`；冻结SoC`{f.get('source_commit','PENDING')}`；CPU`{f.get('cpu_source_commit','PENDING')}`；run`{q.get('native_run','PENDING')}`；状态`{q.get('status','PENDING')}`。当前命令`{q.get('current_command','PENDING')}`，flow`{flow.get('status','PENDING')}`/`{flow.get('current_command','PENDING')}`；owner/PDS PID线索{q.get('owner_pid')}/{q.get('pds_session_pid')}，恢复前实时核对命令/创建时间/run。",
 (followup_note if followup else '本轮为03新资源候选，需新综合/映射及原生资源证明；不得复用旧版时序。'),
 '03资源版本只把以太网TX缓冲读-掩码-整字写改成四个条件字节写使能，保持512x32容量、SYS写/MAC读时钟、读地址/握手与公开输出周期。CPU/官方Pikafish/图像/语音/模型及全部时序打拍保持；旧H128已关闭，不能再次声称裁剪它。真实CPU130MHz、严格7.686ns、CDC6.886ns、SYS/CLINT49.5MHz及48CDC指令/五FIFO映射保持，不能靠放松约束收敛。',
 f"冻结输入逐项匹配={valid}。旧/新RTL四种子完整公开输出及RX/TX存储逐拍对照通过，每种子16掩码×512字和6000随机周期/独立复位/背压，并保留原整帧FCS/RX检查；只覆盖定义的0/1数字写掩码，不声称X输入等价。实际综合后以太网厂商原语/字节掩码及整帧仿真仍按当前receipt验收。资源门禁`{resources.get('status','PENDING')}`；全局资源变化={resources.get('global_delta','PENDING')}，ETH变化={resources.get('eth_delta','PENDING')}。实际资源未下降或CPU保护边界/组合深度退化时不进PnR。",
 f"当前物理优先网={len(pre.get('priority_constraints_kept',[])) if pre else 'PENDING'}；03恢复父01实际提示并拒绝02过宽CPU优先集合，后续新增提示均匹配当前映射实际网；seed3/decongestion4/hold200ps保持。最终全角STA={review.get('final_sta_pass','PENDING')}；CPU={review.get('cpu_timing','PENDING')}；违规={review.get('violating_summary_rows','PENDING')}；物理={physical.get('status','PENDING')}。",
 '离线修复范围：无UART/JTAG/SD/Flash、远程推送、main合并或正式包；最终STA不替代实板CoreMark/MHz/官方模型/并发。全部新副本/测试/native/tmp在G:/fpga，父版和未完成候选保留，不清理活动数据。',
 f"恢复入口：当前`resource-first-review.json`/`placement-change.json`（若存在）、`frozen-inputs.json`、status及最新flow；实际资源/ETH证明位于`{resource_work.as_posix()}`，包括RTL差分/整帧及实际双口RAM/WE边界检查。原集成ETH整模块原生仿真因映射端口提升不能编译，保留失败；RAM/WE通过不代表完整native MMIO译码仿真。刷新`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu_handoff.py --pds25-cpu130-repair-work {work.as_posix()}`。",end])
 for p in [Path('G:/fpga/HANDOFF.md'),R/'docs/CPU_Frequency_Handoff.md']:
  raw=p.read_bytes();t=raw.decode('utf-8-sig');t=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,t,count=1) if begin in t else block+'\n\n'+t
  data=t.replace('\r\n','\n').encode('utf-8');p.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in raw else data)
 p=R/'scripts/project_directory_catalog.json';j=read(p);marker='; '+work.name+':'
 label='CPU130 reduced-source D-cache long-route repair retaining TAGE release' if inherited else ('CPU130 TAGE hard-placement release with reduced ETH source' if placement else ('CPU130 reduced-source TAGE/DDR priority repair' if followup else 'CPU130 resource-first ETH byte-enable candidate'))
 value=j['project_directories']['build'][0];entry=marker+' '+label+', '+q.get('status','PENDING')+', exact CPU/accelerator/clocks retained, resource decrease and native boundaries required before route, offline only, preserve failures'
 if marker in value:
  start=value.index(marker);tail=value[start+len(marker):];following=re.search(r'; [A-Za-z0-9][A-Za-z0-9_.-]*:',tail);stop=start+len(marker)+following.start() if following else len(value);value=value[:start]+entry+value[stop:]
 else:value+=entry
 j['project_directories']['build'][0]=value;p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 p=Path('G:/fpga/PROJECT_INDEX.md');t=p.read_text(encoding='utf-8-sig');marker='<!-- PDS25_CPU130_REPAIR_INDEX -->';line=marker+'\n当前130MHz资源优先修复：[状态](build/'+work.name+'/status.json)、[资源](build/'+resource_work.name+'/resource-review-01/result.json)、[交接](HANDOFF.md)。'+q.get('status','PENDING')+'。';t=re.sub(re.escape(marker)+r'\n[^\n]*',lambda _:line,t,count=1) if marker in t else line+'\n\n'+t;p.write_text(t,encoding='utf-8')
 print(json.dumps(dict(status='CPU130_RESOURCE_SOURCE_BOUND_HANDOFF_REFRESHED',frozen_inputs_match=valid,hardware_acceptance=False)))
