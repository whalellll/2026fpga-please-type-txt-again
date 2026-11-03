"""Refresh accepted CPU120 board facts; read-only with respect to builds/board."""
from pathlib import Path
import json,re,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
def refresh(work):
 work=Path(work).resolve();read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
 board=read(work/'board-state-current.json');native=read(work/'tool-qualification-01/result.json');f=read(work/'frozen-inputs.json')
 assert native['status']=='PDS25_CPU120_NATIVE_CONTROL_CDC_QUALIFICATION_PASS' and native['source_commit']==board['source_commit']==f['source_commit']
 for group in ['native_inputs_sha256','verification_inputs_sha256']:
  for name,digest in f[group].items():assert hashlib.sha256((work/'source'/name).read_bytes()).hexdigest()==digest,name
 begin,end='<!-- PDS25_CPU120_CURRENT_BEGIN -->','<!-- PDS25_CPU120_CURRENT_END -->'
 block=f'''{begin}
## 当前120MHz已完成实现验收，正式包流程继续

工作目录 `{work.as_posix()}`；SoC `{board['source_commit']}`，CPU `{board['cpu_commit']}`，原生 `{board['native_run']}`。实际CPU120MHz/SYS49.5MHz，约束8.325ns/CDC7.525ns；位流SHA256 `{board['bitstream_sha256']}`。

最终124行全角STA、31sites/165pins/23优先网/20skew、523原生输入/82验证输入和完整限定范围PDS25 native CPU/CDC资格通过。CoreMark3+1通过，四样本均值5.281757871/MHz；用户明确“无需对照coremark”，不做80MHz对照/比较门禁。SD六载荷CRC/Linux root、运行SHA、官方NNUE65例及冷/热200、图像/语音、四路并发80000采音样本零溢出通过。NNUE冷/热14.852/13.937ms，10ms目标仍未达到。用户确认界面/鼠标正常，当前GUI及worker保持运行。

当前状态 `{board['status']}`。正式交付完成={board['formal_delivery_complete']}；远程推送={board['remote_pushed']}；Flash写入=False。主分支发布→包独立解包回归→包SHA绑定SD回读/直接启动/应用验证继续按用户授权完成，未绑定完成凭据前不宣称交付完成。证据 `board-state-current.json`、`tool-qualification-01/result.json`、`BOARD_RESULTS_20261101.md`；旧06 NNUE/kit01失败和全部尝试保留。

恢复时先核对真实owner与当前板态。此刷新器不启动构建、不访问板卡、不推送。
{end}'''
 if board['formal_delivery_complete']:
  done=read(work/'delivery/DELIVERY_COMPLETE.json')
  assert done['formal_delivery_complete'] and done['status']=='CPU120_FORMAL_DELIVERY_COMPLETE_USER_FINAL_REMOTE_READBACK_ACCEPTANCE'
  block=f'''{begin}
## 当前120MHz FC1修复版已按用户最终范围交付

工作目录 `{work.as_posix()}`；实现SoC `{board['source_commit']}`、CPU `{board['cpu_commit']}`，原生 `{board['native_run']}`。
发布SoC `{done['soc_commit']}`、CPU `{done['cpu_commit']}` 已推送main并完整回读。CPU120MHz/SYS49.5MHz；位流SHA256 `{board['bitstream_sha256']}`。

最终124行全角STA通过，CPU慢角setup WNS +0.330ns；限定范围PDS25原生CPU/CDC资格、来源一致的CPU131/48套件/架构8组及新FC1原语38项通过。
既有实板CoreMark3+1 CRC/计时通过，三次性能均值5.282446664/MHz；官方NNUE65例及冷/热200、图像/语音、四路并发、80000采音样本零溢出及用户GUI/鼠标确认通过。NNUE冷/热14.852/13.937ms，10ms目标仍未达到。

用户最终明确“回读校验通过就可以了，不需要再次上板”“sd卡文件也不需要重读，保证推送回读就行”。本版以远端提交/617项SoC文件和252项配对CPU源码回读作为最终确认，未重复SD读写、上板或包解出后的完整CPU回归；保留首次SD八文件回读和直接启动证据。CoreMark对照亦由用户明确豁免。

正式包 `{done['archive']}`，SHA256 `{done['archive_sha256']}`；全部{done['inventory_files_verified']}项包内文件大小/哈希通过并与远端回读清单关联。
正式交付完成=True，远程推送=True，Flash写入=False。完成凭据 `delivery/DELIVERY_COMPLETE.json`，最终验收范围 `user-final-acceptance-remote-readback.json`，完整远端回读 `remote-full-input-readback.json`。
本会话已释放串口/JTAG占用，未再接触板卡；其他候选须按其独立授权和验收合同恢复。H盘不可用，G原件保留，归档待H恢复后逐文件校验。

恢复时核对当前真实owner与板态；旧06失败及所有原始输入/工具报告保持身份。此刷新器不启动构建、不访问板卡、不推送。
{end}'''
 workspace=Path(os.environ.get('FPGA_WORKSPACE',str(ROOT.parent)))
 paths=[ROOT/'docs/CPU_Frequency_Handoff.md',workspace/'HANDOFF.md']
 if (work/'release-source/docs/CPU_Frequency_Handoff.md').is_file():paths.append(work/'release-source/docs/CPU_Frequency_Handoff.md')
 for p in paths:
  text=p.read_text(encoding='utf-8-sig') if p.exists() else ''
  text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1) if begin in text else block+'\n\n'+text
  p.write_text(text,encoding='utf8')
 p=ROOT/'scripts/project_directory_catalog.json';catalog=read(p);tag='; cpu12007-board-current='
 role=catalog['project_directories']['build'][0]
 role=re.sub(re.escape(tag)+r'[^;]*', '',role)+tag+board['status']
 catalog['project_directories']['build'][0]=role;p.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 p=workspace/'PROJECT_INDEX.md'
 if p.exists():
  text=p.read_text(encoding='utf-8-sig');mark='<!-- PDS25_CPU120_INDEX -->';line=mark+'\n当前：[120MHz板测/资格凭据](build/'+work.name+'/board-state-current.json)、[完整原生资格](build/'+work.name+'/tool-qualification-01/result.json)、[交接](HANDOFF.md)。'
  text=re.sub(re.escape(mark)+r'\n[^\n]*',lambda _:line,text,count=1) if mark in text else line+'\n\n'+text;p.write_text(text,encoding='utf8')
 print(json.dumps(dict(status='CPU120_ACCEPTED_BOARD_HANDOFF_REFRESHED',frozen_inputs_match=True,board_accessed=False,build_started=False,remote_pushed=False),ensure_ascii=False))
