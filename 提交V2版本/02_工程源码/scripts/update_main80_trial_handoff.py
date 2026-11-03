"""Refresh this isolated80MHz trial only; never inherit packaged75 acceptance."""
from pathlib import Path
import hashlib,json,re

def main():
    root=Path(__file__).resolve().parents[1];work=root.parent
    q=json.loads((work/'status.json').read_text(encoding='utf-8-sig'))
    assert Path(q['source_root']).resolve()==root and q['target_cpu_hz']==80000000
    assert q['base_commit']=='538215e20b0d628e713f296cfbe7e13c741e42a5'
    assert hashlib.sha256((root/'rtl/cpu/CoreTop.sv').read_bytes()).hexdigest()=='e8ae28118b91cd52ce4876a36f7d28efdc646979d960d48e87bc36ced35a88db'
    clock=json.loads((root/'config/clocks.json').read_text(encoding='utf-8-sig'))
    assert (clock['cpu_hz'],clock['sys_hz'],clock['cpu_clock_source'],clock['cpu_divisor'])==(80000000,49500000,'dedicated800',10)
    final=work/'native-result.json'
    if final.exists():
        result=json.loads(final.read_text());q.update(result)
        snap=json.loads((root/'pds/build_snapshot.json').read_text(encoding='utf-8-sig'))
        assert snap['run_id']==result['native_run']
        for name,h in snap['inputs'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h,name
    begin='<!-- MAIN80_SOURCE_TRIAL_20261028_BEGIN -->';end='<!-- MAIN80_SOURCE_TRIAL_20261028_END -->'
    block=begin+'\n## 当前80MHz候选（2026-10-28）\n\n'+f"来源main538215e2；CPU05c7ef96/e8ae2811保持不变。CPU80/SYS49.5，125MHz参考/5×32/10；STA12.495ns，CDC11.695ns。\n当前：`{q['status']}`。作业`{work.as_posix()}`，恢复入口`../HANDOFF.md`，原生状态`../status.json`、最终回读`../native-result.json`。\n"+'本轮范围仅正确性、综合、完整PnR、全角STA；75MHz SD/GUI继承文件不代表80MHz启动套件或板测通过。\nowner快照需要核对真实命令/启动时间；每个PDS作业14400s，无累计预算；不访问板卡/Flash或推送。\n'+end+'\n'
    p=root/'docs/CPU_Frequency_Handoff.md';text=p.read_text(encoding='utf-8-sig')
    text=re.sub(re.escape(begin)+r'.*?'+re.escape(end)+r'\n?','',text,flags=re.S)
    p.write_text(block+'\n'+text,encoding='utf-8')
    print(json.dumps(dict(status='MAIN80_TRIAL_SOURCE_BOUND_HANDOFF_REFRESHED',trial_status=q['status'],build_started=False,board_accessed=False,remote_pushed=False)))
if __name__=='__main__':main()
