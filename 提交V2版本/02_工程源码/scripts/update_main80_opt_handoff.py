"""Refresh the source-bound CPU80 resident-key optimization status; never start a build."""
from pathlib import Path
import hashlib,json,re

def main():
    root=Path(__file__).resolve().parents[1];work=root.parent
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    q=read(work/'status.json');cpu=read(root/'rtl/cpu/source.json');clock=read(root/'config/clocks.json')
    assert Path(q['source_root']).resolve()==root and work.name.startswith('main80-opt-')
    assert sha(root/'rtl/cpu/CoreTop.sv')==q['cpu_rtl_sha256']
    assert cpu['source_reference_commit']==q['cpu_source_commit'] and not cpu['source_worktree_dirty']
    assert (clock['cpu_hz'],clock['sys_hz'],clock['cpu_clock_source'],clock['cpu_divisor'])==(80000000,49500000,'dedicated800',10)
    if q.get('resource_first_assessment'):
        begin='<!-- MAIN80_RF_PRIORITY_SOURCE_20261029_BEGIN -->';end='<!-- MAIN80_RF_PRIORITY_SOURCE_20261029_END -->'
        block=begin+'\n## 当前 CPU80：RF读控制网优先路由\n\n'+f"源码 `{root.as_posix()}`，状态 `{q['status']}`，冻结 `{q.get('source_commit','PENDING')}`。硬件RTL继承723a1d52，CPU `{q['cpu_source_commit']}` / RTL `{q['cpu_rtl_sha256']}` 不变。\n\n"+\
            '前05候选a10eb164最终CPU慢setup−0.745ns、26端点，hold +0.061/+0.036ns；其余115行通过。资源45193 LUT，原123个CPU边界FF保留，旧失败数据库/报告原样保存。本版经资源优先复查，仅追加5条实际RF读控制网的优先路由；clock/STA/seed/hold/所有原优先及位置合同保持。细则docs/CPU80_RF_Read_Priority_20261029.md及候选根resource-first-assessment.json。\n\n'+\
            '新综合/原生预检、CPU资源边界、最终全角STA和板测分别验收；不提前上板、推送或制作正式包。恢复见../HANDOFF.md、../status.json。\n'+end+'\n'
        p=root/'docs/CPU_Frequency_Handoff.md';text=p.read_text(encoding='utf-8-sig')
        text=re.sub(re.escape(begin)+r'.*?'+re.escape(end)+r'\n?','',text,flags=re.S)
        p.write_text(block+'\n'+text,encoding='utf-8')
        print(json.dumps(dict(status='MAIN80_RF_PRIORITY_SOURCE_HANDOFF_REFRESHED',trial_status=q['status'],build_started=False)))
        return
    if (root/'config/vision32_cache_contract.json').exists():
        begin='<!-- MAIN80_BRAM_PROOF_SOURCE_20261029_BEGIN -->';end='<!-- MAIN80_BRAM_PROOF_SOURCE_20261029_END -->'
        block=begin+'\n## 当前 CPU80：显式BRAM映射证明后继\n\n'+f"来源 `{root.as_posix()}`，状态 `{q['status']}`，源码冻结 `{q.get('source_commit','PENDING')}`。硬件723a1d52、CPU `{q['cpu_source_commit']}` / RTL `{q['cpu_rtl_sha256']}` 保持；CPU80/SYS49.5及全部严格时钟/CSR/hold合同不变。\n\n"+\
            '前候选04完整SoC回归及25组周期/整数/故障通过，整机综合45193 LUT/30402 FF/2962 LUTRAM/136.5 DRM/101 APM，123个CPU保护FF保留。其cea3eb0d缺BRAM证明失败及数据库原样保存，本后继只补显式profile、实际原语/完整布尔映射证明、哈希绑定和真实网表负例。旧36-bank LUTRAM证明不替代BRAM。\n\n'+\
            '细则docs/CPU80_BRAM_Native_Contract_20261029.md，实际状态/证据在候选根status.json和HANDOFF.md。新综合/全部预检、完整PnR/最终全角STA和板测分别验收；旧03候选d975运行状态需fresh核对，不能依据过期PID控制进程。匹配80启动包、同轮CoreMark/MHz、官方图像/Pikafish/固定WAV及并发仍待验。不上Flash、不提前推送、不制作正式包。\n'+end+'\n'
        p=root/'docs/CPU_Frequency_Handoff.md';t=p.read_text(encoding='utf-8-sig')
        t=re.sub(re.escape(begin)+r'.*?'+re.escape(end)+r'\n?','',t,flags=re.S)
        p.write_text(block+'\n'+t,encoding='utf-8')
        print(json.dumps(dict(status='MAIN80_BRAM_PROOF_SOURCE_HANDOFF_REFRESHED',trial_status=q['status'],build_started=False,board_accessed=False)))
        return
    if (root/'sim/reference/vision32_layer_lut_weight_reference.v').exists():
        begin='<!-- MAIN80_BRAM_SOURCE_20261029_BEGIN -->';end='<!-- MAIN80_BRAM_SOURCE_20261029_END -->'
        block=begin+'\n## 当前 CPU80：图像权重块RAM资源候选\n\n'+f"源码 `{root.as_posix()}`；状态 `{q['status']}`；实现冻结723a1d52，当前回归/工具冻结 `{q.get('source_commit','PENDING')}`。SoC父082b737d；CPU `{q['cpu_source_commit']}`、RTL `{q['cpu_rtl_sha256']}` 保持。\n\n"+\
            '恢复原RF和resident-key边界继续保留。图像缓存完整1152行/9216字节，四组同步读输出加寄存银行选择，保留原FEED读周期；权重格式、MMIO、整数计算和官方Pikafish Stage A/B/权重缓存不变。另已纳入严格60/70/75/80 GUI时钟支持。\n\n'+\
            '先行独立证据在main80-opt-20261029-03/cache-bram-study-04与cache-bram-map-01：25组整层独立整数、逐周期/字节对照及FEED取消/复位重启通过，3个实际数据故障拒绝；模块综合5911→4451 LUT、1357→205 LUTRAM、2023→2024 FF、0→3 DRM、44 APM不变。局部统计不代表整机收益或STA通过。旧脚本启动/准备失败及等价的未寄存选择诊断均保留原身份。\n\n'+\
            '当前完整SoC回归、整机综合/完整块RAM原生映射证明、最终全角STA及板测分别验收。旧LUTRAM36-bank证明不代表新BRAM通过。CPU80/SYS49.5、125MHz输入/CPU VCO800/CLKOUT3及STA12.495ns/CDC11.695ns、31个真实CSR位置和hold设置不变。原main80-opt-20261029-03/run d975b569仍为独立PnR，未覆盖其数据库；PID、命令及启动时间须fresh核对。\n\n'+\
            '实板CoreMark/MHz、官方图像/Pikafish、固定WAV/并发及匹配80MHz启动文件仍待验；不上Flash，不提前推送或打正式包。恢复入口 `../HANDOFF.md`、`../status.json`、`../correctness-02/result.json`；原CPU75验收不迁作80。\n'+end+'\n'
        p=root/'docs/CPU_Frequency_Handoff.md';t=p.read_text(encoding='utf-8-sig')
        for a,b in [(begin,end),('<!-- MAIN80_OPT_SOURCE_20261028_BEGIN -->','<!-- MAIN80_OPT_SOURCE_20261028_END -->')]:
            t=re.sub(re.escape(a)+r'.*?'+re.escape(b)+r'\n?','',t,flags=re.S)
        p.write_text(block+'\n'+t,encoding='utf-8')
        print(json.dumps(dict(status='MAIN80_BRAM_SOURCE_BOUND_HANDOFF_REFRESHED',trial_status=q['status'],build_started=False,board_accessed=False,remote_pushed=False)))
        return
    begin='<!-- MAIN80_OPT_SOURCE_20261028_BEGIN -->';end='<!-- MAIN80_OPT_SOURCE_20261028_END -->'
    block=begin+'\n## 当前 CPU80 资源／时序优化候选\n\n'+f"作业 `{work.as_posix()}`；状态 `{q['status']}`。SoC父ce01c237（旧失败候选，仅用作隔离开发来源，非验收），CPU `{q['cpu_source_commit']}`，RTL `{q['cpu_rtl_sha256']}`。\n"+'RF恢复原始05c7ef96实现。配对生成64模块中60模块逐字节不变，RsMem行为改变，Rob/Dispatch/CoreBackend仅剪除已证明无用的提示端口/连线：地址提示在已有操作数/刷新寄存边界之后计算，保留全部原有打拍。队头最早发射不增加等待；新入队非队头load提示允许晚一拍，不宣称全接口逐拍等价。固定旧参考在共同背压下核对有效输出并计数延迟。完整回归、实际综合资源与最终全角STA分别验收；新增冻结owner_valid_c1_promoted配置要求执行原生RF写使能/owner专项证明和实际Dispatch读消费者的WB关闭余因子检查，不依赖2.1/6.5版本号。图像缓存证明沿真实共享DDR响应/适配器状态核对全部36 bank写使能，保留kernel-response可支配旧映射。前版RF原生审计通过，图像响应边界适配失败已保留；本版仅变更证明工具，需新冻结与新原生预检。PLL简化仿真修复保持，真实80MHz配置不变。\nCPU80/SYS49.5，严格STA12.495ns/CDC11.695ns；31个CSR位置必须由本轮原生执行和导出验证。保留上一轮setup−1.166ns及hold失败证据，不继承旧75MHz或其他历史80MHz验收。\n恢复入口 `../HANDOFF.md`、`../status.json`；核对真实owner后恢复。当前不上板、不推送、不打正式交付包。\n'+end+'\n'
    p=root/'docs/CPU_Frequency_Handoff.md';t=p.read_text(encoding='utf-8-sig')
    for old in [('<!-- MAIN80_SOURCE_TRIAL_20261028_BEGIN -->','<!-- MAIN80_SOURCE_TRIAL_20261028_END -->'),(begin,end)]:
        t=re.sub(re.escape(old[0])+r'.*?'+re.escape(old[1])+r'\n?','',t,flags=re.S)
    p.write_text(block+'\n'+t,encoding='utf-8')
    print(json.dumps(dict(status='MAIN80_OPT_SOURCE_BOUND_HANDOFF_REFRESHED',trial_status=q['status'],build_started=False,board_accessed=False,remote_pushed=False)))

if __name__=='__main__':main()
