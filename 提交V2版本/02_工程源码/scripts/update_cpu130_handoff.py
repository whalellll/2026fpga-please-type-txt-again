"""Read source-bound CPU130 status; never launch tools or touch the board."""
from pathlib import Path
import hashlib,json,re,sys

def refresh(work):
    work=Path(work).resolve();root=Path(__file__).resolve().parents[1]
    def read(p):
        if not p.is_file():return {}
        return json.loads(p.read_text(encoding='utf-8-sig'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    f=read(work/'frozen-inputs.json');q=read(work/'status.json');flow=read(work/'flow.json');review=read(work/'final-review-02/result.json');physical=read(work/'physical-verification-01/result.json');s=work/'source'
    flows=[p for p in work.glob('flow*.json') if p.name=='flow.json' or p.name.startswith('flow-retry')]
    if flows:flow=read(max(flows,key=lambda p:p.stat().st_mtime))
    matches=bool(f) and all((s/n).is_file() and sha(s/n)==h for group in ['native_inputs_sha256','verification_inputs_sha256'] for n,h in f.get(group,{}).items())
    begin='<!-- PDS25_CPU130_LATEST_MAIN_BEGIN -->';end='<!-- PDS25_CPU130_LATEST_MAIN_END -->'
    block='\n\n'.join([begin,'## 最新提交120MHz基础上的130MHz布线试验（2026-11-01）',
        '用户要求查找最新120MHz提交对应本地仓库并尝试130MHz布线。远端main回读`da0ff3f2b8ec509546170a18dc0082d47eb20c99`，对应本地`G:/fpga/build/pds25-cpu120-zbc-fc1-20261101-01/release-source`，Git共用库`G:/fpga/performance_soc_repo/.git`。包括Zbc及FC1修复；未引入另一会话CoreMark6.5试验RTL。',
        f"独立候选`{work.as_posix()}`；冻结SoC`{f.get('source_commit','PENDING')}`；配对CPU`{f.get('cpu_source_commit','PENDING')}`；原生run`{q.get('native_run','PENDING')}`；状态`{q.get('status','PENDING')}`。",
        '新增受限mode11：既有125MHz差分参考/5×39=975MHz VCO，CLKOUT0/7.5=130MHz，编码CPU_DIVISOR15，50%占空比。STA严格7.686ns，481CPU=183SYS公共展开，CDC6.886ns；SYS/CLINT49.5MHz、原48条CDC指令及五FIFO寄存器映射保持。CPU/加速器/IP共224个受保护输入逐字节核对，CPU134项49套件9组架构及原功能凭据按来源复用；本轮时钟策略/反例、12配置厂商/行为对照、1024边沿PLL波形及SoC复位/丢锁/三拍释放通过，五套固件已重建。',
        f"冻结输入逐项匹配={matches}；当前原生命令`{q.get('current_command','PENDING')}`；流程`{flow.get('status','PENDING')}`/`{flow.get('current_command','PENDING')}`；owner/PDS PID线索{q.get('owner_pid')}/{q.get('pds_session_pid')}。恢复前核对实时命令行、创建时间、工作目录和run；不能按旧PID重复启动或停止其它作业。",
        f"130MHz最终全角STA={review.get('final_sta_pass','PENDING')}；CPU时序={review.get('cpu_timing','PENDING')}；违规={review.get('violating_summary_rows','PENDING')}；物理回读={physical.get('status','PENDING')}。120MHz父版通过不代表130MHz通过。",
        '范围为离线布局布线及最终STA。未访问串口/JTAG/SD/Flash，未推送或合入main，不制作正式包。完整原生工具资格与CoreMark/MHz、官方模型/并发板测仍单独待验。所有新增源码、构建、测试和tmp均在G:/fpga；父版及失败证据保留。本轮未完成候选不做清理。',
        '映射诊断：原6/3级ROB消费者深度筛查被当前7/4级映射拒绝，原flow及失败日志保留。64消费者位中仅1位深度变化，123个保留寄存器/Q线逐字节一致。旧PDS22 one-hot owner检查首轮不匹配；按父版已验证PDS25二进制owner适配后1024组读取向量/64位消费者语义通过。boundary-review-01记录深度、扇出、原失败与适配；此次仅为带已知映射风险的离线诊断布线，不改写原深度拒绝为通过，不代表时序收敛。',
        '实际约束：31位置和165引脚保留；父版23条优先网中的旧CPU issueUsesFast在新映射中不存在，按原有真实对象过滤机制保留22条，未猜测替代名；所有原DDR网优先级保留，priority-inventory-review.json记录差异。seed3/decongestion4/hold200ps及原生DRC保持。',
        f"恢复：读`status.json`、`flow.json`及最新步骤日志；运行控制器`run_flow.py`不能重复启动，失败后先分析并使用新的步骤/回执。证据`baseline.json`、`frozen-inputs.json`、`regression-reuse.json`、`clock-checks-01/`、`clock-reset-01/`、`final-review-02/`、`RESULTS.md`。刷新`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu_handoff.py --pds25-cpu130-work {work.as_posix()}`。",end])
    for p in [Path('G:/fpga/HANDOFF.md'),root/'docs/CPU_Frequency_Handoff.md']:
        raw=p.read_bytes();t=raw.decode('utf-8-sig');t=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,t,count=1) if begin in t else block+'\n\n'+t
        data=t.replace('\r\n','\n').encode('utf-8');p.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in raw else data)
    p=root/'scripts/project_directory_catalog.json';j=read(p);marker='; '+work.name+':'
    value=j['project_directories']['build'][0];entry=marker+' latest published120MHz da0ff3f2 Zbc/FC1 -> bounded130MHz mode11 VCO975/output7.5, '+q.get('status','PENDING')+', strict7.686ns/CDC6.886ns, offline only, final STA/physical independent, preserve parent and failures'
    if marker in value:
        start=value.index(marker);tail=value[start+len(marker):];following=re.search(r'; [A-Za-z0-9][A-Za-z0-9_.-]*:',tail)
        end=start+len(marker)+following.start() if following else len(value)
        value=value[:start]+entry+value[end:]
    else:value+=entry
    j['project_directories']['build'][0]=value;p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    p=Path('G:/fpga/PROJECT_INDEX.md');t=p.read_text(encoding='utf-8-sig');marker='<!-- PDS25_CPU130_INDEX -->'
    phase='最终全角STA通过，未上板' if review.get('final_sta_pass') is True else '布线完成，最终STA未通过' if review else '离线待验'
    line=marker+'\n当前130MHz试验：[状态](build/'+work.name+'/status.json)、[流程](build/'+work.name+'/flow-retry03.json)、[结果](build/'+work.name+'/RESULTS.md)、[交接](HANDOFF.md)。最新120MHz起点da0ff3f2；'+phase+'。'
    t=re.sub(re.escape(marker)+r'\n[^\n]*',lambda _:line,t,count=1) if marker in t else line+'\n\n'+t;p.write_text(t,encoding='utf-8')
    print(json.dumps(dict(status='CPU130_SOURCE_BOUND_HANDOFF_REFRESHED',frozen_inputs_match=matches,hardware_acceptance=False)))

if __name__=='__main__':refresh(Path(sys.argv[1]))
