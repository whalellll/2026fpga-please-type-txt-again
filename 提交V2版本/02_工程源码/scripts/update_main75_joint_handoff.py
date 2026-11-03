"""Refresh this CPU75 joint candidate from bound local evidence; no board access."""
import json
from pathlib import Path
from audit_main75_candidate import validate, sha, read


def main():
    source = Path(__file__).resolve().parents[1]
    run = source.parent
    result = read(run/'native-result.json')
    validate(source, run/'native-result.json', source/'artifacts/soc_top.sbit')
    state = read(run/'status.json')
    assert Path(state['source_root']).resolve() == source
    sd = read(run/'sd75-candidate/manifest.json')
    preparation = read(run/'sd75-preparation.json')
    assert preparation['manifest_sha256'] == sha(run/'sd75-candidate/manifest.json')
    assert len(sd['tests']) == 18 and preparation['status'].endswith('PASS_NOT_BOARD')
    for name, item in sd['sd_root_files'].items():
        assert sha(run/'sd75-candidate/sd-root'/name) == item['sha256'], name
    program = read(run/'program-precheck-03/result.json')
    assert program['status'] == 'EXACT_MAIN75_IDENTITY_8_CORRUPTIONS_REJECTED_AND_CRAM_DRYRUN_PASS_NO_BOARD_ACCESS'
    assert program['audit_script_sha256'] == sha(source/'scripts/audit_main75_candidate.py')
    assert program['program_script_after_sha256'] == sha(source/'scripts/program_cram.ps1')
    text = f'''## 当前75MHz联合优化候选（2026-10-27）

用户要求的图像驱动优化与voice_3 r05已合入独立分支 `candidate/main75-joint-20261027-01`。
候选目录 `{run.as_posix()}`；原生实现冻结 `{result['source_commit']}`，run `{result['native_run']}`。
后续源码归档/编程工具/文档提交不改写该原生实现身份；软件新增头文件另随本地后续提交保存。

CPU75MHz=675MHz/9，SYS/CLINT49.5MHz，OpenSBI期限换算33/50；STA13.320ns、CDC12.520ns保持。
CPU源05c7ef96、生成RTLe8ae2811及逻辑/seed保持。旧H128已关闭，官方Pikafish Stage A/B和权重缓存保留。
原75MHz run0dba5123慢角setup−0.050ns、8个违例端点；本轮32个CSR相关单元采用同源CPU70原生位置，
最终严格执行、类型、槽位、快照和实际PNR导出逐项通过。未使用-no_check或放宽时序例外。

完整SoC回归SOC_ALL_TESTS_PASS、五套固件、517项原生输入、46份报告与49项输出哈希回读通过。
最终全角STA All Constraints Met：CPU慢/快setup +0.191/+5.066ns，慢/快hold +0.141/+0.105ns，
18个时钟、116行汇总和20行max-skew检查通过。保留既有187项外部I/O覆盖缺口，不能代替板级I/O验收。
位流SHA-256：`{result['bitstream_sha256']}`。

已复用来源/配置/UAPI一致的b6fd3e52内核，启动参数及GUI启动器选择vision_io_mode=2、vision_profile=0。
voice_3 r05源2cc38efb、模型0bd87ebd、静态RV32运行时0f372779均保持；研究模型尚未晋升准确率验收。
75MHz GUI及计时换算、host/RV32时钟负例、三种WAV完整五层trace离线通过。
配套 `sd75-candidate/sd-root` 八文件及18项真实加载器离线检查通过，移除旧CPU70 CRAM回执，
新位流身份检查、8种篡改拒绝和CRAM脚本DryRun通过；上述离线检查没有串口/JTAG/SD/Flash访问，后续板测状态另列于本块末尾。

当前原生作业已完成，不应按旧PID重复启动或停止进程。CPU70图像/语音/Pikafish实测仅作来源参考，
离线冻结阶段的75MHz实板验收为待验；最新CoreMark/启动/模型状态按后文来源回执分别记录，真实麦克风不在本轮请求范围。
CoreMark只比较同轮全样本CoreMark/MHz均值，绝对下降最多0.05，总分仅记录。
未推送main、未制作正式交付包；原失败源码/报告/数据库均保留，H不可用，G原件未清理。
新输入、临时目录和产物均在G:/fpga。下一步先核对真实板卡连接和候选哈希，再做易失CRAM及SD实板验收；禁止写Flash。

证据入口：`native-result.json`、`software-checks-01/result.json`、`sd75-preparation.json`、
`program-precheck-03/result.json` 与 `source/docs/Main75_Joint_Candidate_20261027.md`（均相对于候选目录）。
'''
    board = read(run/'board-20261027-01/status.json') if (run/'board-20261027-01/status.json').exists() else {}
    if board.get('status') in ['BOARD_CONNECTION_REQUIRED_NO_ASSIGNMENT_NO_MEASUREMENTS', 'WAITING_CARD_RETURN_POWER_AND_JTAG_NO_ASSIGNMENT_NO_MEASUREMENTS']:
        text += '''
2026-10-27最新上板请求：COM17 CP210x、FTDI A/B均枚举OK，但UART四秒读回0字节。
70MHz对照编程的前置扫描与关闭UART/新server端口65490只扫描均报告JtagServer-0306，
未检测到FPGA器件链；两次都停在cfg_scan_chain，没有assign/program，也没有CoreMark或模型实测。
原生STA通过状态保持，板测仍未验收。当前无继续下载重试的变量，等待用户确认主电源/JTAG板端连接，
以及把SD接电脑并告知盘符；不据USB适配器枚举推断板卡已供电。
工作目录board-20261027-01，失败coremark-abab-01、scan-uart-closed-01日志保留，不覆盖/复用。
恢复后使用新coremark-abab-02目录；必要时UART关闭编程，所有控制/候选有效样本都须同轮采集。
SD使用board-20261027-01/sd75-board-kit-02：八个载荷与原18项离线检查保持相同；
仅修正继承的CPU70编程回执元数据flag为false/null。原CPU75 rootfs已经移除旧回执，
本轮无实际CPU75编程回执，不能把旧manifest的true标记当作75MHz编程证明。旧manifest原样保留。
板卡恢复后先备份并逐文件校验部署SD，再返卡并CPU复位，使用本轮MAIN75精确启动合同。
本轮boot合同一份正确样本、七份错误频率/CRC/载荷/内核/提示符样本拒绝检查通过，仅主机辅助检查。
'''
        sd_write = run/'board-20261027-01/sd-write-01/result.json'
        if sd_write.exists() and read(sd_write).get('status') == 'CPU75_SD8_AND_SUMS_BACKUP_WRITE_FLUSH_READBACK_PASS_RETURN_CARD_PENDING':
            text += '''
上段SD待接入已更新：用户明确指定E，实际核对USB disk2/FAT32/31,914,983,424字节、卷5c9f349d。
已保存原启动文件和根目录清单/恢复命令，写入八文件与SHA256SUMS并刷新卷缓存、逐项SHA回读通过，
98个无关根文件及CAMERA/VOICE等四个用户目录保持。没有格式化或Flash写入。
当前等待用户安全移除E、SD返卡、开发板主电源打开并接好UART/JTAG；尚未确认返卡/上电。
返卡确认后新建coremark-abab-02，使用run_coremark75_pair.py --program-with-uart-closed；
成功后run_measurements75.py执行MAIN75 SD启动、身份/计时、数值、图像分段、固定WAV与自动并发及GUI恢复。
协调器已按75MHz身份重新构建、host solo/重叠夹具通过、RV32 SHA d3177d1f；旧70MHz协调器不可直接替代。
未获得新CoreMark、图像或语音性能结果。写卡证据：board-20261027-01/sd-write-01/result.json。
'''
    pair_path = run/'board-20261027-01/coremark-abab-02/result.json'
    if pair_path.exists():
        pair = read(pair_path)
        text += '\n最新实板作业：`'+pair.get('status','UNKNOWN')+'`。已收到用户“已返卡并上电接好”确认。\n'
        if pair.get('status') == 'MAIN75_COREMARK_ABAB_ALL_SAMPLES_CRC_TIME_PER_MHZ_PASS_LINUX_PENDING':
            for item in pair['batches']:
                assert item['status']=='PASS'
                assert sha(Path(item['program_receipt']))==item['program_sha256']
                assert sha(Path(item['coremark_result']))==item['coremark_sha256']
            control=pair['summaries']['control'];candidate=pair['summaries']['candidate']
            text += (f"两轮70/75交替CoreMark全部12性能+4校验运行通过。70/75均值CoreMark/MHz "
                     f"{control['mean_coremark_per_mhz']:.9f}/{candidate['mean_coremark_per_mhz']:.9f}；"
                     f"绝对下降{pair['coremark_per_mhz_absolute_decrease']:.9f}，门槛0.05，通过。"
                     f"总分仅记录{control['mean_coremark']:.6f}/{candidate['mean_coremark']:.6f}。\n")
            assignment=read(Path(pair['final_program_receipt']))
            assert assignment['status']=='PASS' and assignment['bitstream_sha256']==result['bitstream_sha256']
            assert assignment['audit_script_sha256']==sha(source/'scripts/audit_main75_candidate.py')
            text += '最终75MHz候选易失CRAM编程成功、唯一PG2L100H ID00602899/DONE=1；未写Flash。\n'
        sequence_path=run/'board-20261027-01/sequence-status-02.json'
        if not sequence_path.exists():sequence_path=run/'board-20261027-01/sequence-status.json'
        if sequence_path.exists():
            sequence=read(sequence_path)
            text += ('原始顺序控制器回执`'+sequence['status']+'`，owner PID快照'+str(sequence['owner_pid'])+
                     '；恢复前核对实际命令行与启动时间，不重复打开UART或启动第二个控制器。\n')
        boot_path=run/'board-20261027-01/boot.result.json'
        if boot_path.exists():
            text += '本轮SD启动状态：`'+read(boot_path)['status']+'`。\n'
        text += '''
本轮E盘写入/刷新/回读与用户返卡已经完成，98个无关根文件和四个用户目录保留。
sd75-board-kit-02八载荷不变，runtime-binding75.json与sd75-effective-manifest.json逐项从实际CPIO回读GUI75、启动器和构建元数据哈希，
纠正旧manifest继承的三个CPU70 runtime哈希及旧编程回执标记；全部runtime.sha256条目与归档实际内容一致。
源父manifest及写卡回执不改写，不把元数据修正当作新载荷或上板验收。
board-20261027-01/coremark-abab-01和scan-uart-closed-01仍是早期无器件链的失败；恢复后成功不改写失败。
实际图像/固定WAV/自动并发和GUI恢复以各自结束回执为准；未完成的组不预先判通过。NNUE10ms与图像帧率目标单独记录，研究语音模型未晋升。
本轮操作指南与证据位于board-20261027-01，全部新临时目录都在G:/fpga。
'''
    final_path=run/'board-20261027-01/board-acceptance.json'
    if final_path.exists():
        final=read(final_path);summary=read(run/'board-20261027-01/summary.json')
        assert final['summary_sha256']==sha(run/'board-20261027-01/summary.json')
        assert final['report_binding_sha256']==sha(run/'board-20261027-01/report-binding.json')
        text += f'''
最新完成结论（2026-10-28）：`{final['status']}`，覆盖上文进行中/待验快照。
75MHz直接SD启动、同轮CoreMark/MHz、三WAV完整张量、297份worker结果、官方Pikafish数值/固定节点及自动并发通过。
图像同版三轮模式0/1/2均值90.382175/53.359113/51.657730秒，模式2减少42.845%；硬件均值约17.005秒。
单次剖析驱动非硬件49.136169→14.234532秒；剖析和后续复测的模式0基线不同，不混拼分解或倍率。
语音1秒固定WAV请求至IDLE独跑755.557ms，NNUE ready后全重叠84份均值1624.857ms，搜索39份均值1648.559ms。
Pikafish热NNUE独跑19.463ms、语音并发44.352ms；三个搜索局面的节点/bestmove/score/WDL不变。
GUI原后台恢复因SIGTTOU作业控制停住，失败gui-restore回执保留；旧GUI前台恢复后正常退出，
同一二进制以stdin=/dev/null重新后台启动，gui-restore-02首帧、实际非T状态、r05环境、模式2/探针关闭通过。
这仅改变串口实验恢复方式，不改变SD载荷、模型/驱动/位流或任何性能样本。MMIO键鼠保留，串口交还shell。
首次GUI停止也曾碰到启动脚本尚未exec的竞态，initial失败保留；实际进程确认后initial-retry-02全部通过。
NNUE10ms与图像30fps目标仍未达到，语音准确率、真实麦克风/句尾、实体相机及HDMI目视未在本轮验收。
研究r05不因此晋升，未推送main/制作正式包/写Flash，当前板卡保留75MHz易失CRAM与新SD、GUI已恢复。
全部原始失败、原生数据库和SD备份保留；H不可用，G原件未清理。
报告source/docs/CPU75_Board_Performance_20261028.md；summary、analysis、completed-sequence、board-acceptance及report-binding位于board-20261027-01。
原native-result.json仍保持构建阶段NOT_BOARD身份，最新板测结论以独立board-acceptance.json及其绑定为准。
'''
    workspace = run.parents[1]
    for path in [source/'docs/CPU_Frequency_Handoff.md', workspace/'HANDOFF.md',
                 workspace/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
        raw = path.read_bytes()
        nl = b'\r\n' if b'\r\n' in raw[:200] else b'\n'
        begin, end = b'<!-- MAIN75_JOINT_20261027_BEGIN -->', b'<!-- MAIN75_JOINT_20261027_END -->'
        assert raw.count(begin) == raw.count(end) == 1
        left, right = raw.index(begin), raw.index(end) + len(end)
        block = begin + nl + text.encode().replace(b'\n', nl) + end + nl
        path.write_bytes(raw[:left] + block + raw[right:].lstrip(b'\r\n'))
    print(json.dumps(dict(status='MAIN75_JOINT_SOURCE_BOUND_HANDOFF_REFRESHED',
                         native_run=result['native_run'], board_accessed=False, build_started=False)))


if __name__ == '__main__':
    main()
