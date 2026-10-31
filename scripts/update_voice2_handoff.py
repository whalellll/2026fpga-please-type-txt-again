"""Refresh only the voice2 candidate's evidence and handoff section."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
R=Path(__file__).resolve().parents[1];W=R.parent
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--phase',required=True);a=ap.parse_args();checks={}
 for name in ['voice-cnn-rtl-02','voice-cnn-mmio-01','voice2-model-bound-01','voice2-legacy-mmio-01','voice2-rv32-build-02','voice2-rv32-bound-01','voice2-wav-01','voice2-full-regression-01','voice2-full-regression-02']:
  p=R/'build'/name/'result.json'
  if p.exists():checks[name]={'status':json.loads(p.read_text())['status'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 p=R/'build/voice2-kernel-01/build.json'
 if p.exists():checks['kernel']={'status':json.loads(p.read_text())['status'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 native=Path('G:/v2vsyn1/resource-evidence/result.json');resource=json.loads(native.read_text(encoding='utf-8-sig')) if native.exists() else {}
 state={'updated_utc':datetime.now(timezone.utc).isoformat(),'source_root':str(R),'branch':'feature/voice2-small-accel-20261024','parent':'07c39182c5befb170a7a42db44561046b4cf1278','phase':a.phase,'checks':checks,'native_resource_status':resource.get('status','NOT_STARTED'),'native_root':'G:/v2vsyn1','cpu_hz':75000000,'sys_hz':49500000,'display':'1080p30','model_sha256':'3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973','board':False,'pnr':False,'push':False,'delivery':False}
 resource_comparison=R/'build/voice2-resources-01.json'
 if resource_comparison.exists():state['resources']=json.loads(resource_comparison.read_text())['candidate']['total']
 state['source_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip()
 (R/'build/voice2-status.json').write_text(json.dumps(state,indent=2)+'\n')
 begin='<!-- VOICE2_SMALL_ACCEL_20261024_BEGIN -->';end='<!-- VOICE2_SMALL_ACCEL_20261024_END -->'
 block=f'''{begin}
## voice_2 小型语音加速器适配（2026-10-24）

用户授权使用现有语音小型加速器适配远程整句模型，暂不做CPU核内接口。隔离源码 `{R.as_posix()}`，分支feature/voice2-small-accel-20261024，父07c3918；CPU75/SYS49.5/1080p30、官方Pikafish专用核心和卷积不变。没有修改另一会话的专用候选或其物理作业。

模型固定voice_2/a901132，balanced24 SHA256 {state['model_sha256']}；40维logMel、20ms帧移、五层CNN与CTC8，不是旧SD77单token分类器。首版CPU保留原FFT/logMel、时序窗口展开、bias/int64 requant及CTC；将CNN全部点积放进现有4路S8语音计算结构的可编程profile。编译选择旧分类器或新CNN核，不同时复制两套乘法阵列；CNN层权重在片上复用，接口独立于已删除的通用dense MAC。

当前阶段：{a.phase}。新子窗0x80/VCN1与能力位区分；内核独占owner和锁保留，新增模型代次/范围/超时清理；旧profile仿真保留，新profile拒绝旧SD77模型调用。完整原始模型/源码在linux/voice2及SOURCE.json绑定，无远程AGENTS继承。

离线：{json.dumps(checks,ensure_ascii=False)}
真实权重4种输入长度的五层raw/quant trace在CPU/设备替身间一致，81个真实模型tile通过RTL回放；另19组独立整数oracle通过裸核及实际voice MMIO wrapper。替身不是实板验收，合成特征不是语音准确率。原SD77默认profile的1600样本/8窗口/121分类输出回归通过。

资源综合目录G:/v2vsyn1，状态{state['native_resource_status']}；只parse+synthesize，无PnR/位流/板卡操作。Linux编译build/voice2-kernel-01（独立WSL临时树），RV32编译/测试见checks；只以成功回执为准，活动进程后续核对命令和启动时间。未改SD/Flash/生产启动文件、未推送或打正式包。FFT和多帧静音判停仍在，不能宣称说完<=10ms；尚无此版板端加速比。

入口：`performance_soc_voice2_accel_20261024/docs/Voice2_Small_Accelerator_20261024.md`；实时证据`build/voice2-status.json`。保留before/编译选项/主机脚本失败记录和全部未完成候选。此处状态更新UTC {state['updated_utc']}。
{end}'''
 for p in [W/'HANDOFF.md',W/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']:
  text=p.read_bytes().decode();eol='\r\n' if '\r\n' in text else '\n'
  if begin in text:
   left,rest=text.split(begin,1);_,right=rest.split(end,1);text=left+block.replace('\n',eol)+right
  else:
   i=text.find('\n');text=text[:i+1]+eol+block.replace('\n',eol)+eol+text[i+1:]
  p.write_bytes(text.encode())
 # Add only this candidate's directory entry; leave other sessions' entries intact.
 for p in [R/'scripts/project_directory_catalog.json',W/'performance_soc_voice_hw/scripts/project_directory_catalog.json']:
  original=p.read_bytes();catalog=json.loads(original.decode('utf-8-sig'));pattern=R.name
  if not any(pattern in g['patterns'] for g in catalog['workspace_groups']):
   catalog['workspace_groups'].insert(0,{'patterns':[pattern],'role':'voice_2 balanced24小型语音CNN加速器隔离候选，CPU75/SYS49.5/1080p30','policy':'模型/ABI/离线逐层与RTL回放验证；资源/内核构建、时序和板测分别记录，未完成不清理、不推送、不交付'})
   eol='\r\n' if b'\r\n' in original else '\n'
   p.write_bytes((json.dumps(catalog,ensure_ascii=False,indent=2)+'\n').replace('\n',eol).encode())
  if p.parent.parent==R:
   tracked=subprocess.check_output(['git','show','HEAD:scripts/project_directory_catalog.json'],cwd=R)
   if b'\r\n' in tracked and b'\r\n' not in p.read_bytes():
    p.write_bytes(p.read_bytes().replace(b'\n',b'\r\n'))
 p=W/'PROJECT_INDEX.md';text=p.read_text(encoding='utf-8');link='performance_soc_voice2_accel_20261024/docs/Voice2_Small_Accelerator_20261024.md'
 if link not in text:
  i=text.find('\n');text=text[:i+1]+'\n- [voice_2 小型语音加速器适配]('+link+')：原4路语音乘加支持balanced24五层CNN，FFT/CTC暂留CPU；离线验证与资源/内核构建状态见交接。\n'+text[i+1:];p.write_bytes(text.encode())
 print(json.dumps({'status':'VOICE2_HANDOFF_UPDATED','phase':a.phase,'checks':len(checks),'native':state['native_resource_status']}))
if __name__=='__main__':main()
