"""Refresh hardware publication and software handoff links without board IO."""
from pathlib import Path
import argparse,json,re,subprocess
R=Path(__file__).resolve().parents[1];O=R/'artifacts/validated_accelerators_20261025'
p=argparse.ArgumentParser();p.add_argument('--shared-only',action='store_true');a=p.parse_args()
m=json.loads((O/'manifest.json').read_text());receipt=R/'docs/validation/hardware-publication-20261025/remote-readback.json'
final_receipt=R/'build/publication-final-readback.json'
if final_receipt.exists():receipt=final_receipt
d=json.loads(receipt.read_text()) if receipt.exists() else {}
begin='<!-- HW_PUBLICATION_20261025_BEGIN -->';end='<!-- HW_PUBLICATION_20261025_END -->'
block=f'''{begin}
## 已验证硬件推送与软件交接（2026-10-25）

用户明确要求推送已验证硬件，软件优化方向形成交接；本次新授权覆盖旧“候选暂不推送”的限制，仅针对本独立硬件分支。
工程`{R.as_posix()}`，分支hardware/validated-accelerators-20261025，基于main e7288be；相对main权威硬件只有vision32_layer.v改变，Linux/启动与软件性能优化代码未导入。
硬件原生来源85ed001，run c8282c99，e42f5f1b位流；408项硬件源与17项ROM/构建输入匹配，全角116行/20max-skew/18clocks通过，保留187个IO约束缺口。
图像/语音/官方Pikafish/搜索/并发功能板测通过，CoreMark/MHz新硬件A/B仍待；本次不是main更新或正式交付，无交付ZIP/Flash动作。
推送回读状态`{d.get('status','LOCAL_VERIFIED_REMOTE_PUSH_PENDING')}`；远程提交`{d.get('remote_commit','PENDING')}`。位流入口`artifacts/validated_accelerators_20261025/soc_top.sbit`，不要误用候选根目录旧artifacts位流。
硬件说明`docs/Validated_Hardware_Publication_20261025.md`；软件交接`docs/Software_Optimization_Handoff_20261025.md`，包含最新57.180712s结果、模型/输入SHA、方向、命令和软件本地提交。
最新软件仍在performance_soc_integer_ops_20261025，da0f914/aa134da；RAM实测与SD18离线通过，实体SD仍为旧整数版。软件代码未随本次硬件分支推送，不能把RAM实测当新SD部署。
当前无本次PnR/推理作业；新测试输出仅在G:/fpga内。交付前CoreMark/实体SD及正式流程仍需各自完成，不改写历史回执。
{end}
'''
paths=[Path('G:/fpga/performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md'),Path('G:/fpga/HANDOFF.md')]
if not a.shared_only:paths.insert(0,R/'docs/CPU_Frequency_Handoff.md')
for p in paths:
 text=p.read_bytes().decode('utf-8');eol='\r\n' if text.split('\n',1)[0].endswith('\r') else '\n';body=block.replace('\n',eol)
 if begin in text:text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:body.strip(),text,count=1)
 else:
  first,tail=text.split('\n',1);text=first+'\n'+eol+body+eol+tail
 p.write_bytes(text.encode('utf-8'))
print('HARDWARE_PUBLICATION_HANDOFF_REFRESHED_NO_BOARD_IO')
