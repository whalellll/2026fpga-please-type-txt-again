"""Maintain the active130MHz repair without modifying source/build evidence."""
from pathlib import Path
import hashlib,json,re,sys

def refresh(work):
 work=Path(work).resolve();R=Path(__file__).resolve().parents[1]
 if (work/'resource-first-plan.json').is_file() or (work/'resource-first-review.json').is_file():
  from update_cpu130_resource_handoff import refresh as refresh_resource
  return refresh_resource(work)
 def read(p):return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 f=read(work/'frozen-inputs.json');q=read(work/'status.json');pre=read(work/'pnr-preflight-05/result.json');review=read(work/'final-review-02/result.json');physical=read(work/'physical-verification-01/result.json')
 flows=[p for p in work.glob('flow*.json') if p.name=='flow.json' or p.name.startswith('flow-retry')];flow=read(max(flows,key=lambda p:p.stat().st_mtime)) if flows else {}
 valid=bool(f) and all(sha(work/'source'/n)==h for group in ['native_inputs_sha256','verification_inputs_sha256'] for n,h in f.get(group,{}).items())
 change=read(work/'priority-change.json');parent=f.get('parent_candidate','PENDING')
 memory=read(work/'memory-wait02.json') or read(work/'memory-wait.json')
 begin='<!-- PDS25_CPU130_WNS_REPAIR_BEGIN -->';end='<!-- PDS25_CPU130_WNS_REPAIR_END -->'
 block='\n\n'.join([begin,'## 当前130MHz：按用户要求修复直到最终WNS为正（2026-11-01）',
 '用户最新要求“尝试修复直到wns为正”。保持真实CPU130MHz、严格7.686ns、CDC6.886ns及SYS/CLINT49.5MHz，按原有正确性/最终全角STA/约束覆盖检查逐轮修复；不通过降频、放松时序例外或连续盲换seed达成目标。范围为离线修复；无新增板卡/SD/Flash或推送授权。',
 f"活动目录`{work.as_posix()}`；来源`{f.get('source_commit','PENDING')}`/CPU`{f.get('cpu_source_commit','PENDING')}`；run`{q.get('native_run','PENDING')}`；父候选`{parent}`。最初01完整布线失败CPU慢setup−0.071ns/2端点、DDR−0.060ns/8端点，慢/快hold及快setup通过；完整报告/数据库/失败回执保持。",
 f"本轮状态`{q.get('status','PENDING')}`；原生命令`{q.get('current_command','PENDING')}`；flow`{flow.get('status','PENDING')}`/`{flow.get('current_command','PENDING')}`；owner/PDS PID线索{q.get('owner_pid')}/{q.get('pds_session_pid')}。恢复须实时核对命令、创建时间、工作目录和run，不按旧PID重复启动或停止其它作业。",
 f"输入回读一致={valid}。当前优先网={len(pre.get('priority_constraints_kept',[]))}，新增={len(change.get('added',[]))}，仅取失败路径实际长弧或高扇出网且核对映射对象。全部523原生源码/固件输入保持，71个compile/synth/map文件逐项大小/哈希回读复用；31位置、165引脚、48CDC指令及五FIFO映射保持，seed3/decongestion4/hold200ps不变。未改CPU/加速器逻辑，既有来源绑定功能及native资格凭据明确复用，不冒称重新跑过。",
 '02首个控制器企图移除复制项目中已不存在的历史RCF，被原生拒绝且未启动PnR；pnr-01/flow.json保留。pnr-02使用项目已登记的精确PCF/RCF并显式force_to_run执行全流程，不绕过DRC。父01的ROB深度拒绝和旧one-hot检查器不匹配/现有PDS25 binary-owner适配证据仍保留原身份，不改成时序通过。',
 f"02第二个控制器布局因原生Memory alloc failed中断，未得到新STA；原生失败文件及manifest在pnr-02/native-failure/保留。资源等待状态`{memory.get('status','N/A')}`，monitor PID线索{memory.get('owner_pid')}，最新采样{memory.get('samples',[])[-1:] or 'N/A'}。待可用提交内存≥6.5GiB、物理内存≥7GiB连续两次采样后，以相同输入重跑pnr-03；只替换本任务空闲监视器，不停止其它任务或更改系统pagefile。",
 f"最终全角STA={review.get('final_sta_pass','PENDING')}；CPU={review.get('cpu_timing','PENDING')}；违规={review.get('violating_summary_rows','PENDING')}；物理回读={physical.get('status','PENDING')}。完整工具/实板性能与离线时序结论分别验收。",
 f"恢复入口：`frozen-inputs.json`、`native-reuse.json`、`priority-change.json`、`status.json`、最新flow、`final-review-02/`、`RESULTS.md`。只读刷新`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu_handoff.py --pds25-cpu130-repair-work {work.as_posix()}`。先读真实失败路径、资源和扇出，再冻结下一候选；所有新副本/tmp/证据在G:/fpga，未完成候选不清理。",end])
 for p in [Path('G:/fpga/HANDOFF.md'),R/'docs/CPU_Frequency_Handoff.md']:
  raw=p.read_bytes();t=raw.decode('utf-8-sig');t=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,t,count=1) if begin in t else block+'\n\n'+t
  data=t.replace('\r\n','\n').encode('utf-8');p.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in raw else data)
 p=R/'scripts/project_directory_catalog.json';j=read(p);marker='; '+work.name+':'
 value=j['project_directories']['build'][0];entry=marker+' CPU130 WNS repair, exact source/native-map reuse, actual priority count '+str(len(pre.get('priority_constraints_kept',[])))+', '+q.get('status','PENDING')+', full STA/physical independent, offline only, preserve all failures'
 if marker in value:
  start=value.index(marker);tail=value[start+len(marker):];following=re.search(r'; [A-Za-z0-9][A-Za-z0-9_.-]*:',tail);stop=start+len(marker)+following.start() if following else len(value);value=value[:start]+entry+value[stop:]
 else:value+=entry
 j['project_directories']['build'][0]=value;p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 p=Path('G:/fpga/PROJECT_INDEX.md');t=p.read_text(encoding='utf-8-sig');marker='<!-- PDS25_CPU130_REPAIR_INDEX -->';line=marker+'\n当前130MHz WNS修复：[状态](build/'+work.name+'/status.json)、[结果](build/'+work.name+'/RESULTS.md)、[交接](HANDOFF.md)。'+q.get('status','PENDING')+'。'
 t=re.sub(re.escape(marker)+r'\n[^\n]*',lambda _:line,t,count=1) if marker in t else line+'\n\n'+t;p.write_text(t,encoding='utf-8')
 print(json.dumps(dict(status='CPU130_REPAIR_SOURCE_BOUND_HANDOFF_REFRESHED',frozen_inputs_match=valid,hardware_acceptance=False)))

if __name__=='__main__':refresh(Path(sys.argv[1]))
