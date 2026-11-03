from pathlib import Path
import hashlib,json,re,sys
def refresh(work):
 work=Path(work).resolve();R=Path(__file__).resolve().parents[1]
 read=lambda p:json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 f=read(work/'frozen-inputs.json');q=read(work/'status.json');review=read(work/'final-review-02/result.json');physical=read(work/'physical-verification-01/result.json');result=read(work/'result.json')
 flows=[p for pattern in ['*flow*.json','memory-wait*.json'] for p in work.glob(pattern)];flow=read(max(flows,key=lambda p:p.stat().st_mtime)) if flows else {}
 valid=bool(f) and all(sha(work/'source'/n)==h for g in ['native_inputs_sha256','verification_inputs_sha256'] for n,h in f.get(g,{}).items())
 begin='<!-- PDS25_CPU125_CURRENT_BEGIN -->';end='<!-- PDS25_CPU125_CURRENT_END -->'
 block='\n\n'.join([begin,'## 当前目标125MHz：130本轮失败后按用户要求切换（2026-11-02）',
 '用户最新要求“这一次布线如果还没过就布线125mhz”。130第06轮最终CPU慢setup−0.753ns/TNS−11.067ns/71端点，其余时序组通过，完整失败报告及物理回读保留。停止追加130MHz布线，当前目标125MHz，最终全角WNS须正。最新提交120MHz基线为da0ff3f2/Zbc+官方FC1，配对CPU b1164e4；此前原始01/02/03/04/05/06失败证据均保留。',
 f"活动目录`{work.as_posix()}`；状态`{q.get('status','PENDING')}`；SoC冻结`{f.get('source_commit','NOT_FROZEN_YET')}`，CPU`{q.get('cpu_source_commit',f.get('cpu_source_commit','b1164e4'))}`；native run`{q.get('native_run','PENDING')}`。最新控制器`{flow.get('status','PENDING')}`/`{flow.get('current_command','PENDING')}`，PID线索`{flow.get('owner_pid')}`/`{flow.get('child_pid')}`；恢复前实时核对owner、命令、创建时间和run。",
 '真实125MHz由已有125MHz差分参考/5×40=1GHz VCO、CLKOUT0/8产生，mode8/encoded16；严格7.992ns，SYS20.202ns，91CPU=36SYS周期，CDC7.192ns，全部48CDC指令及五FIFO寄存器映射保留。实际PLL、时钟配置/CRC/启动参数和五组固件需新验证，重新综合/映射/原生边界及全角STA；130映射或STA不能冒充125MHz。',
 '保留03以太网TX条件字节写资源优化（原实测全局−89LUT/−256LUTRAM，ETH−299LUT/+1DRM36K），CPU/官方Pikafish StageA/B/缓存/FC1及视觉/语音RTL保持。125新资源数以实际综合为准。保留05释放TAGE旧硬位置的策略和30CSR位置，拒绝06新增7条D-cache优先网；采用05的实际路由提示时需重新匹配125真实映射。CPU保护FF/Q及流水、隔离扇出复制不能撤掉。',
 f"当前冻结输入匹配={valid}；时钟检查={read(work/'clock-checks-01/result.json').get('status','PENDING')}；复位={read(work/'clock-reset-01/result.json').get('status','PENDING')}；固件流程={read(work/'clock-flow.json').get('status','PENDING')}。原CPU134测试/49套件/9架构及官方算法证据仅按精确源码/receipt复用，新时钟与native门禁另验；ETH原RTL差分及整帧与原生RAM/WE边界证明须区分，旧整集成native ETH端口提升导致的编译失败保留。",
 f"最终全角STA={review.get('final_sta_pass','PENDING')}；严格正WNS={result.get('strict_positive_wns_pass','PENDING')}；CPU={review.get('cpu_timing','PENDING')}；违规={review.get('violating_summary_rows','PENDING')}；物理={physical.get('status','PENDING')}。综合/布线结束和位流生成均不单独代表通过。",
 '本次离线布线范围，板测/CoreMark每MHz/官方模型/并发验收仍为独立门禁。无远程推送、main合入或正式交付包；无UART/JTAG/SD/Flash操作。新source/build/tests/tmp均限G:/fpga；未完成候选和原生报告保留，不归档清理活动数据。',
 f"恢复：先读`baseline.json`、`status.json`及最新flow，核对实际进程再继续。刷新命令`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu125_handoff.py {work.as_posix()}`；目录索引刷新后执行`update_project_index.py --check`。",end])
 for p in [Path('G:/fpga/HANDOFF.md'),R/'docs/CPU_Frequency_Handoff.md']:
  raw=p.read_bytes();t=raw.decode('utf-8-sig');t=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,t,count=1) if begin in t else block+'\n\n'+t
  data=t.replace('\r\n','\n').encode('utf-8');p.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in raw else data)
 p=R/'scripts/project_directory_catalog.json';j=read(p);v=j['project_directories']['build'][0];marker='; '+work.name+':'
 entry=marker+' true CPU125 fallback after final failed130 run06, '+q.get('status','PENDING')+', strict7.992ns/CDC7.192ns, retained reduced ETH and exact paired CPU, fresh native map/STA required, offline only'
 if marker in v:
  start=v.index(marker);m=re.search(r'; [A-Za-z0-9][A-Za-z0-9_.-]*:',v[start+len(marker):]);stop=start+len(marker)+m.start() if m else len(v);v=v[:start]+entry+v[stop:]
 else:v+=entry
 j['project_directories']['build'][0]=v;p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 p=Path('G:/fpga/PROJECT_INDEX.md');t=p.read_text(encoding='utf-8-sig');marker='<!-- PDS25_CPU125_CURRENT_INDEX -->';line=marker+'\n当前125MHz离线布线：[状态](build/'+work.name+'/status.json)、[流程](build/'+work.name+'/baseline.json)、[交接](HANDOFF.md)。'+q.get('status','PENDING')+'。';t=re.sub(re.escape(marker)+r'\n[^\n]*',lambda _:line,t,count=1) if marker in t else line+'\n\n'+t;p.write_text(t,encoding='utf-8')
 print(json.dumps(dict(status='CPU125_SOURCE_BOUND_HANDOFF_REFRESHED',frozen_inputs_match=valid,hardware_acceptance=False)))
if __name__=='__main__':refresh(sys.argv[1])
