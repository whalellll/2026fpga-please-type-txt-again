"""Refresh source-bound offline120MHz candidate facts without board/build actions."""
from pathlib import Path
import hashlib,json,re,sys
R=Path(__file__).resolve().parents[1]
def refresh(work):
 if (work/'board-state-current.json').is_file() and (work/'tool-qualification-01/result.json').is_file():
  from update_cpu120_board_handoff import refresh as refresh_board
  return refresh_board(work)
 read=lambda p:json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 q=read(work/'status.json');f=read(work/'frozen-inputs.json');sta=read(work/'final-review-02/result.json');physical=read(work/'physical-verification-01/result.json')
 gate=read(work/'correctness-for-native.json');s=work/'source';clock=read(s/'config/clocks.json');cpu=read(s/'rtl/cpu/source.json')
 unit=read(work/'cpu-test/status.json');arches=sorted(work.glob('architecture-supervisor-*/status.json'));arch=read(arches[-1]) if arches else {};runtime=read(work/'soc-runtime-01/status.json');boundary=read(work/'new-boundaries-02/result.json')
 reuse=read(work/'regression-reuse.json')
 if reuse:
  origin=Path(reuse['source_candidate'])
  if not unit:unit=read(origin/'cpu-test/status.json')
  if not arch:arch=read(origin/'architecture-supervisor-01/status.json')
  if not runtime:runtime=read(origin/'soc-runtime-01/status.json')
  gate=dict(reuse,**gate)
 valid=bool(f) and all((s/n).is_file() and sha(s/n)==h for n,h in f.get('native_inputs_sha256',{}).items())
 begin,end='<!-- PDS25_CPU120_CURRENT_BEGIN -->','<!-- PDS25_CPU120_CURRENT_END -->'
 summary='最终全角STA待验；中间布局/路由值不代表通过。'
 if sta:summary=f"最终全角STA={sta['final_sta_pass']}，{sta['headline']}；CPU={sta['cpu_timing']}；违规={sta['violating_summary_rows']}；物理回读={physical.get('status','PENDING')}。"
 block='\n'.join([begin,('## 当前120MHz NNUE/CoreMark5.2合并验证（2026-11-01）' if (work/'merge-plan.json').is_file() else '## 当前120MHz独立布线与修复（2026-11-01）'),'',
  ('用户要求把100MHz候选的NNUE与CoreMark5.2修复合入已通过的120MHz候选。保留原120MHz通过版本，在新候选重新做正确性、综合/映射/布线/最终全角STA；不得继承旧时序结论或以降频、放宽约束、新增false path代替修复。' if (work/'merge-plan.json').is_file() else '用户要求“尝试120mhz布线，如果没过就修复直到通过”。本轮离线综合/映射/布线/最终STA，保留每次失败证据；不得以降频、放宽时序或新增false path代替修复。'),
  f"目录 `{work.as_posix()}`；状态 `{q.get('status','PREPARING')}`；SoC冻结 `{f.get('source_commit','尚未冻结')}`；CPU实现 `{cpu.get('source_reference_commit','PENDING')}`；native run `{q.get('native_run','PENDING')}`。",
  '父版110MHz为 pds25-cpu110-20261101-03 / SoC43f7dad42d7eda8c6a4cfaf6a7112c41de923260 / CPU47088441501bbe853299a6ed1f87069f6878cff1，最终CPU慢setup+0.236ns/hold+0.131ns，快setup+3.459ns/hold+0.090ns，CDC+0.177ns、DDR+0.120ns；原生124汇总/16例外与物理回读通过。其完整46套件128CPU测试、8组Sv32架构回归和配对RTL哈希保留。',
  f"120MHz新增模式10：125MHz参考/5×48=1200MHz VCO，CLKOUT0/10（编码20），50%占空比。严格CPU8.325ns小于物理25/3ns，182CPU=75SYS公共展开；CDC7.525ns；原48条CDC指令和五个FIFO register映射保持。SYS/CLINT49.5MHz、DDR/显示/加速器/模型保持。当前配置cpu_hz={clock.get('cpu_hz')}。",
  f"冻结原生输入逐项匹配={valid}；正确性门禁 `{gate.get('status','PENDING')}`；当前命令 `{q.get('current_command','PREPARING')}`；owner/PDS PID线索 {q.get('owner_pid')}/{q.get('pds_session_pid')}；恢复时须核对真实命令、启动时间、run与报告，不能据旧PID重复启动或停止别的作业。",
  '本轮范围：'+q.get('scope',f.get('scope','详见本候选 merge-plan.json；当前实现与测试仍待冻结/验证。')),
  ('合并来源：100MHz 5.2效率修复CPU1dd79af及NNUE影子CPU参考/默认关闭的强制上传诊断；保留120MHz父版02已通过STA的CSR向量寄存器、Dcache取消因式分解、五个CDC目的端寄存器。父版02 CPU慢setup+0.249ns，主报告build/pds25-cpu120-20261101-02/RESULTS.md；新候选不能继承该时序通过结论。NNUE板上2951/2392主差异仍待闭环；未引入独立5.8/Zbc或编译参数实验。' if (work/'merge-plan.json').is_file() else '父版及每次失败证据保留；本候选只按新生成的原生最终报告判断通过。'),
  (f"功能证据复用来源 `{reuse['source_candidate']}`：CPU/生成RTL/全部功能输入哈希一致，复用其131测试/48套件、8组架构、SoC/NNUE/CoreMark诊断；不是再次执行这些测试。原03 CPU慢setup+0.258ns，但DDR慢setup-0.039ns/3端点，整机STA失败，保留原报告。04被旧优先网白名单拒绝且未启动PDS；05新增绑定03报告哈希的单网配置及严格校验。当前候选必须有自己的全新原生STA和物理回读，不能复用03的时序结论。" if reuse else '功能与物理证据按本候选实际执行/复用范围分别记录。'),
  ('05单公共网优先级将DDR从-0.039ns/3端点改善到两个-0.006ns端点，CPU慢setup+0.286ns；整机仍失败。06保留05的21条实际优先网，增加实测adj_cke[5]/phy_wrdata_en[1]两条，v2配置绑定05原生报告与03基础报告，正向/十类反例通过；目标实际23条，所有RTL/时钟/FDC/位置/seed/hold参数保持。05初次辅助计数误用20，已按完整名单纠正为父03的20+1=21，原拒绝与修正证据分别保留。' if '06'==work.name.rsplit('-',1)[-1] else '实际优先网数量以本候选原生名单和最终执行/回读记录为准；历史固定文字标签不能替代实际字段。'),
  f"正确性：CPU单元={unit.get('status','PENDING')}（{gate.get('unit_tests','待汇总')}项/{gate.get('unit_suites','待汇总')}套件）；架构={arch.get('status','PENDING')}（{gate.get('architectural_cases','待汇总')}组）；SoC运行时={runtime.get('status','PENDING')}；原生新增寄存器={boundary.get('status','PENDING')}。历史75/80MHz专用回归工具尚不能代表120MHz完整工具资格，运行时仿真与原生检查分别列证据。",
  summary,
  '证据入口：status.json、frozen-inputs.json、clock-checks-01/result.json、clock-reset-01/result.json、correctness-for-native.json、final-review-02/result.json、physical-verification-01/result.json、RESULTS.md。下一步按当前真实阶段恢复；最终失败先分析真实路径、资源和扇出，再冻结下一候选并完成相应正确性及完整PnR。',
  '本轮无板卡操作、远程推送或正式交付；PDS25完整CPU-control/CDC工具资格、CoreMark/MHz与官方模型/并发实板门禁仍独立待验。原100MHz SD GUI及已上传候选不受本轮改动。所有新增源码/构建/测试/cache/tmp均在G:/fpga。',
  f"刷新：`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu_handoff.py --pds25-cpu120-work {work.as_posix()}`。",end])
 docs=[Path('G:/fpga/HANDOFF.md'),R/'docs/CPU_Frequency_Handoff.md']
 if (s/'docs/CPU_Frequency_Handoff.md').is_file():docs.append(s/'docs/CPU_Frequency_Handoff.md')
 for p in docs:
  raw=p.read_bytes();t=raw.decode('utf-8-sig');t=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,t,count=1) if begin in t else block+'\n\n'+t
  data=t.replace('\r\n','\n').encode('utf-8');p.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in raw else data)
 p=R/'scripts/project_directory_catalog.json';j=read(p);mark='; '+work.name+':'
 j['project_directories']['build'][0]=j['project_directories']['build'][0].split(mark,1)[0]+mark+' baseline110 cancel-factor CPU4708844; currentCPU='+cpu.get('source_reference_commit','PENDING')+'; mode10 exact120MHz/strict8.325ns/CDC7.525ns; '+q.get('status','PREPARING')+'; final STA/physical and board separate; preserve all failures/110/100; all new artifacts G'
 p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 p=Path('G:/fpga/PROJECT_INDEX.md');t=p.read_text(encoding='utf-8-sig');mark='<!-- PDS25_CPU120_INDEX -->';line=mark+'\n当前：[120MHz候选](build/'+work.name+'/status.json)、[原120MHz已通过STA](build/pds25-cpu120-20261101-02/RESULTS.md)、[110MHz已通过STA](build/pds25-cpu110-20261101-03/RESULTS.md)、[交接](HANDOFF.md)。'
 t=re.sub(re.escape(mark)+r'\n[^\n]*',lambda _:line,t,count=1) if mark in t else line+'\n\n'+t;p.write_text(t,encoding='utf-8')
 print(json.dumps(dict(status='CPU120_SOURCE_BOUND_HANDOFF_REFRESHED',frozen_inputs_match=valid,hardware_acceptance=False)))
if __name__=='__main__':refresh(Path(sys.argv[1]))
