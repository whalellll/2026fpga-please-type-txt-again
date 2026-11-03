"""Refresh only the CPU125 small CoreMark optimization handoff; never touch hardware."""
from pathlib import Path
import argparse, json, re
from datetime import datetime, timezone

BEGIN = '<!-- CPU125_COREMARK60_SMALL_CURRENT_BEGIN -->'
END = '<!-- CPU125_COREMARK60_SMALL_CURRENT_END -->'

def replace(path, block):
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig').replace('\r\n','\n')
    if BEGIN in text:
        text = re.sub(re.escape(BEGIN)+r'[\s\S]*?'+re.escape(END), lambda _: block, text, count=1)
    else:
        text = block+'\n\n'+text
    data = text.encode('utf-8')
    path.write_bytes(data.replace(b'\n',b'\r\n') if b'\r\n' in raw else data)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('work',type=Path)
    a=p.parse_args()
    work=a.work.resolve()
    workspace=Path('G:/fpga').resolve()
    assert work.is_relative_to(workspace)
    root=Path(__file__).resolve().parents[1]
    q=json.loads((work/'status.json').read_text())
    rows=[]
    for path in sorted((work/'compiler02').glob('*/performance.json')):
        r=json.loads(path.read_text())
        rows.append(f"| {path.parent.name} | {r['iterations']} | {r['coremark_per_mhz']:.9f} | {r['duration_seconds']:.6f} |")
    final_path=work/'full-fixed100-01/result.json'
    if final_path.is_file():
        for r in json.loads(final_path.read_text())['runs']:
            rows.append(f"| 完整重建 {r['mode']} | {r['iterations']} | {r['coremark_per_mhz']:.9f} | {r['duration_seconds']:.6f} |")
    block='\n\n'.join([BEGIN,'## CPU125 小幅优化：目标超过 6.0 CoreMark/MHz（2026-11-02）',
        '用户要求合并125MHz与约6.0/MHz，并补充：尝试优化到超过6.0，避免大改，可适当增加几条指令。已选择纯编译优化cm60-unroll2-lto-branch1；CPU/ISA/队列/缓存/访存及官方加速器保持父版，无新增指令。',
        f"独立候选`{work.as_posix()}`，分支`candidate/cpu125-coremark60-20261102-01`；父SoC`{q['parent_soc']}`，父CPU`{q['parent_cpu']}`；状态`{q['status']}`。真实CPU125MHz/SYS49.5MHz，严格7.992ns/CDC7.192ns。原125MHz全角STA通过仅适用于原冻结输入；任何新RTL/固件须按变更范围重新绑定验收。",
        '当前使用精确97abbc79生成RTL的已绑定模型，运行时明确CPU125MHz；六个CoreMark编译单元统一O2/no-if/unroll2/LTO/branch1，官方算法/种子/2000字节工作区不改，无PGO。早期筛选复用配对boot对象，完整重建已重新编译16个boot及6个CoreMark对象，性能6.031419124/验证6.011920910/MHz；独立官方C oracle四项CRC通过。五套生产固件/输入绑定通过，生产仍ITERATIONS=0自动校准；128KiB BRAM及16KiB栈门槛保持，实际栈18008字节、余量1624。10编译配方和11容量反例门禁通过。短仿真约0.133秒，不代表每次≥10秒的实板验收。',
        '| 编译候选 | 迭代数 | 诊断CoreMark/MHz | 模拟目标秒数 |\n|---|---:|---:|---:|\n'+'\n'.join(rows),
        '不选ALU8/MEM4/SB4的6.6试验配置：原生综合较已发布FC1基线增加3416LUT/1298FF；保留该候选原始证据和其他会话作业。新bootROM不能借用父版位流/STA身份，须另行生成绑定原生产固件的新native产物并按变更范围验收。当前UART枚举为空，实板正式CoreMark/官方模型/并发尚未执行；本候选未推送/合入main，未制作正式交付包。新源码、测试、tmp均限G:/fpga；恢复先核对进程归属及status.json。',
        f"刷新：`G:/py/ana/python.exe -X utf8 -B scripts/update_cpu125_coremark60_handoff.py {work.as_posix()}`。更新时间UTC `{datetime.now(timezone.utc).isoformat()}`。", END])
    targets=[workspace/'HANDOFF.md', workspace/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md',root/'docs/CPU_Frequency_Handoff.md']
    for path in dict.fromkeys(targets):
        replace(path,block)
    entry=f"; {work.name}: CPU125 small CoreMark optimization >6.0/MHz, {q['status']}; uniform compiler first, no queue/cache enlargement; short diagnostics are not board acceptance"
    for project in [workspace/'performance_soc_voice_hw',root]:
        path=project/'scripts/project_directory_catalog.json'
        catalog=json.loads(path.read_text(encoding='utf-8-sig'))
        old=catalog['project_directories']['build'][0]
        marker='; '+work.name+':'
        if marker in old:
            start=old.index(marker)
            following=re.search(r'; [A-Za-z0-9][A-Za-z0-9_.-]*:',old[start+len(marker):])
            end=start+len(marker)+following.start() if following else len(old)
            old=old[:start]+entry+old[end:]
        else:
            old+=entry
        catalog['project_directories']['build'][0]=old
        path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    path=workspace/'PROJECT_INDEX.md'
    text=path.read_text(encoding='utf-8-sig')
    marker='<!-- CPU125_COREMARK60_SMALL_INDEX -->'
    line=marker+'\n[CPU125 小幅CoreMark优化](build/'+work.name+'/status.json)：'+q['status']+'；目标超过6.0/MHz，完整实板/时序验收按变更范围独立进行。'
    text=re.sub(re.escape(marker)+r'\n[^\n]*',lambda _:line,text,count=1) if marker in text else line+'\n\n'+text
    path.write_text(text,encoding='utf-8')
    print(json.dumps(dict(status='CPU125_SMALL_COREMARK_HANDOFF_REFRESHED',hardware_acceptance=False)))

if __name__=='__main__':
    main()
