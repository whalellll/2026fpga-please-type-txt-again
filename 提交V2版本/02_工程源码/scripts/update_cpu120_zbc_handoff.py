"""Refresh only the source-bound120MHz Zbc merge state; never build or access a board."""
from pathlib import Path
import hashlib,json,re,sys

def read(p):return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
def refresh(work):
    root=Path('G:/fpga');repo=root/'performance_soc_voice_hw';source=work/'source'
    q=read(work/'status.json');f=read(work/'frozen-inputs.json');cpu=read(work/'cpu-bindings.json')
    unit=read(work/'java-all/status.json');arch=read(work/'architecture-01/status.json');cm=read(work/'coremark-pair-01/result.json');sta=read(work/'final-review-02/result.json');flow=read(work/'route-flow.json')
    matched=all(hashlib.sha256((source/n).read_bytes()).hexdigest()==h for g in ['native_inputs_sha256','verification_inputs_sha256'] for n,h in f.get(g,{}).items()) if f else None
    begin='<!-- CPU120_ZBC_MERGE_BEGIN -->';end='<!-- CPU120_ZBC_MERGE_END -->'
    scores='；'.join(r['implementation']+'/'+r['mode']+'='+format(r['coremark_per_mhz'],'.9f') for r in cm.get('runs',[])) or '运行中'
    timing='；'.join(x['corner']+'/'+x['check']+'='+str(x['wns_ns'])+'ns' for x in sta.get('cpu_timing',[])) or '待新原生报告'
    block='\n'.join([begin,'## 当前120MHz Zbc/CoreMark优化合并候选（2026-11-01）','',
        '用户要求将目录中的特定指令CoreMark优化候选合入120MHz候选。基于已通过全角STA的pds25-cpu120-20261101-06，合入cpu100-coremark58-20261101-01的通用Zbc三条指令及GCC16.2/O2/no-if-conversion配套配置；原候选与证据保留。',
        f"目录`{work.as_posix()}`；状态`{q.get('status','PREPARING')}`；SoC`{f.get('source_commit','PENDING')}`；CPU`{cpu.get('cpu_commit','PENDING')}`；run`{q.get('native_run','PENDING')}`。",
        '关闭Zbc重新生成的综合RTL与父120MHz逐字节一致。开启时SupervisorCsr/CoreMemory/RsMem/Rob/RsMdu保持，Rename只扩宽22→25位操作码载荷；既有寄存边界、120MHz/严格8.325ns、CDC7.525ns、SYS/CLINT49.5MHz及DDR23条实际优先网保持。',
        f"CPU全回归={unit.get('status','PENDING')}；真实指令架构={arch.get('status','PENDING')}，{arch.get('pass_groups',0)}/9组；配对生成/禁用等价={cpu.get('status','PENDING')}；冻结输入回读匹配={matched}。",
        '本轮100迭代诊断：'+scores+'。每行仅一次短跑、均不足官方10秒，不能作为正式成绩。官方算法源文件不变，128KiB ROM/16KiB栈保留。',
        f"新最终全角STA={sta.get('final_sta_pass',False)}；{timing}。原120MHz通过结论不转移到新RTL。",
        f"当前命令`{q.get('current_command','见各测试status.json')}`；owner PID线索{q.get('owner_pid')}。恢复必须核对实时命令、启动时间、工作目录和run，不据旧PID重复启动或终止作业。",
        f"整体控制器`{flow.get('status','PENDING')}`，PID线索{flow.get('owner_pid')}，子进程{flow.get('child_pid')}，当前步骤`{flow.get('current_command','等待完整CPU回归')}`；CPU回归owner线索{unit.get('owner_pid')}。完整CPU未通过时该控制器不启动PnR；route-flow.json记录进程归属和各步骤退出码。",
        '本轮无串口/JTAG/SD/Flash操作，不打断原120MHz候选的独立板上NNUE诊断。不合入main、不推送、不制作正式包；官方长跑CoreMark及NNUE/模型/并发板测继续待验，不声称原NNUE差异已修复。所有新增产物在G:/fpga；不清理未完成候选。',
        f"刷新：`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu_handoff.py --pds25-cpu120-zbc-work {work.as_posix()}`。",end])
    for p in [root/'HANDOFF.md',repo/'docs/CPU_Frequency_Handoff.md',source/'docs/CPU_Frequency_Handoff.md']:
        raw=p.read_bytes();text=raw.decode('utf-8-sig');text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
        payload=text.replace('\r\n','\n').encode();p.write_bytes(payload.replace(b'\n',b'\r\n') if b'\r\n' in raw else payload)
    for p in [repo/'scripts/project_directory_catalog.json',source/'scripts/project_directory_catalog.json']:
        j=read(p);marker='; CPU120_ZBC_CURRENT:';j['project_directories']['build'][0]=j['project_directories']['build'][0].split(marker,1)[0]+marker+' '+work.as_posix()+'; '+q.get('status','PREPARING')+'; source/paired RTL/new tests and native timing; no board/push/delivery'
        p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    p=root/'PROJECT_INDEX.md';tag='<!-- CPU120_ZBC_INDEX -->';line=tag+'\n[120MHz Zbc合并候选](build/'+work.name+'/RESULTS.md)、[机器状态](build/'+work.name+'/status.json)、[交接](HANDOFF.md)。'
    text=p.read_text(encoding='utf-8-sig');text=re.sub(re.escape(tag)+r'\n[^\n]*',lambda _:line,text,count=1) if tag in text else line+'\n\n'+text;p.write_text(text,encoding='utf-8')
    print(json.dumps(dict(status='CPU120_ZBC_SOURCE_BOUND_HANDOFF_REFRESHED',frozen_inputs_match=matched,hardware_acceptance=False)))
if __name__=='__main__':refresh(Path(sys.argv[1]))
