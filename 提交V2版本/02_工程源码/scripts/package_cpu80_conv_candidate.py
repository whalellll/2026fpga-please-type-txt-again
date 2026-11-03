"""Package only a fully gated offline candidate; never access boards or remotes."""
import argparse,gzip,hashlib,json,re,shutil,subprocess,sys,zipfile
from pathlib import Path
from datetime import datetime,timezone

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--native',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--sd-kit',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--repackage',action='store_true');a=ap.parse_args()
root=Path(__file__).resolve().parents[1];native=a.native.resolve();work=a.work.resolve();sd_source=a.sd_kit.resolve();output=a.output.resolve()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
write=lambda p,x:Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not output.exists(),'Never overwrite a candidate archive'
flow=read(work/'native-flow.json');assert flow['status']=='NATIVE_ALL_GATES_PASS_OFFLINE_DELIVERY_PENDING',flow['status']
snapshot=read(native/'artifacts/build_snapshot.json');evidence=read(native/'artifacts/build_evidence.json');run=snapshot['run_id']
assert evidence['run_id']==flow['run_id']==run and evidence['timing']=='All Constraints Met'
assert evidence['max_skew_verified'] and evidence['timing_scope_verified']
assert read(work/'full.json')['status']=='FULL_SOC_PASS_NOT_STA_OR_BOARD'
assert read(work/'native-map-audit/result.json')['status']=='NATIVE_FOLDED_STORE_MAC512_CHECKSUM32_READ_BOUNDARIES_CPU_DRM_PASS_NOT_STA'
assert read(work/'native-map-audit/fold-ads-proof.json')['netlist_sha256']==sha(native/'pds/synthesize/soc_top_syn.vm')
for n,h in snapshot['inputs'].items():assert sha(root/n)==sha(native/n)==h,n
for n,h in evidence['outputs'].items():assert sha(native/n)==h,n
assert flow['bitstream_sha256']==sha(native/'artifacts/soc_top.sbit')
assert read(sd_source/'manifest.json')['status']=='CPU80_CONV_SD_OFFLINE_VERIFIED_BOARD_PENDING'

dest_art=root/'artifacts/cpu80_conv_20261022'
if dest_art.exists():assert a.repackage and read(root/'CPU80_CONV_CANDIDATE.json')['run_id']==run
else:dest_art.mkdir(parents=True)
ev=root/'docs/validation'/work.name;ev.mkdir(parents=True,exist_ok=True)
def copy(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);assert sha(src)==sha(dst)
selected=set(n for n in snapshot['inputs'] if n.startswith('artifacts/'))
for n in [*evidence['outputs'],'artifacts/build_evidence.json']:
 if n.startswith('artifacts/'):
  copy(native/n,root/n);selected.add(n)
copy(root/'artifacts/bootrom.hex',root/'pds/bootrom.hex')
for name in ['soc_top.rtr','rtr.db']:
 destination=dest_art/'native'/('CPU80_CONV_'+run[:8]+('_final.rtr' if name.endswith('.rtr') else '_final.xml'))
 copy(native/'pds/report_timing'/name,destination)
copy(native/'pds/synthesize/soc_top.snr',dest_art/'native/soc_top.snr')
# Preserve actual native reports/VM as compressed read-only evidence, not DBs.
for source,name in [(native/'pds/synthesize/soc_top_syn.vm','soc_top_syn.vm.gz'),(native/'pds/input-snapshots'/run/'pds.stdout.log','native-console.log.gz')]:
 if source.is_file():
  with gzip.open(dest_art/'native'/name,'wb') as f:f.write(source.read_bytes())
copy(native/'pds/build_snapshot.json',dest_art/'native/input-snapshot.json')
for file in (native/'pds/input-snapshots'/run).glob('*.json'):copy(file,ev/'native-gates'/file.name)
for name in ['baseline.json','focus.json','focus-conv.json','full.json','resource.json','soc-freeze.json','native-flow.json','final-native.json','tool-review.json','native-resource-profile.json','microarch-tool-tests.log','fold-basis.json','fold-ads-proof.json','mapped-boundaries.json','c80cvr2-resources.json','c80cvr4-resources.json']:
 if (work/name).is_file():copy(work/name,ev/name)
assert read(work/'focus-conv.json')['status']=='FOCUSED_CONV_RTL_UAPI_ARITHMETIC_PERFORMANCE_PASS_NOT_STA_OR_BOARD'
assert b'crc=eb240272 job_cycles=8897293' in (work/'focus-conv-test_mac_conv_full_layer.log').read_bytes()
copy(work/'focus-conv.json',ev/'full-layer/receipt.json')
copy(work/'focus-conv-test_mac_conv_full_layer.log',ev/'full-layer/raw.log')
for folder in ['dense-gather-v2','sd-rebuild-v2','native-map-audit','fold-ads-faults']:
 for p in (work/folder).rglob('*'):
  if p.is_file():copy(p,ev/folder/p.relative_to(work/folder))
for name in ['baseline.log','focus.log','focus-conv-test_trained_conv_tile.log','full-soc.log','native-build.log']:
 if (work/name).is_file():
  with gzip.open(ev/(name+'.gz'),'wb') as f:f.write((work/name).read_bytes())
kit=dest_art/'sd-kit'
for p in sd_source.rglob('*'):
 if p.is_file() and p.suffix not in ('.img','.pyc') and '__pycache__' not in p.parts:
  name=p.relative_to(sd_source)
  if name.as_posix()=='manifest.json':name=Path('software-build.json')
  copy(p,kit/name)
software=read(kit/'software-build.json')
manifest=dict(software,status='CPU80_CONV_SD_OFFLINE_VERIFIED_BOARD_PENDING',software_source_manifest_sha256=sha(kit/'software-build.json'),candidate_run_id=run,candidate_bitstream_sha256=flow['bitstream_sha256'],candidate_soc_implementation_commit=flow['soc_implementation_commit'],binding_scope='accepted_run_id/bitstream_sha256 describe the software baseline only; candidate_* identifies the new convolution image. No board acceptance inherited.')
write(kit/'manifest.json',manifest)
copy(root/'scripts/deploy_cpu80_conv_sd.ps1',kit/'Copy_To_SD.ps1')
extra=read(work.parent/'cpu80-conv-20261022/full-preparation-recovery.json')['copied_sha256']
for n,h in extra.items():assert sha(root/n)==h;selected.add(n)
for p in dest_art.rglob('*'):
 if p.is_file():selected.add(p.relative_to(root).as_posix())

final=read(work/'final-native.json')
cpu_rows=[x for x in final['rows'] if x['clocks']==['cpu_clk','cpu_clk']]
model=dict(status='CPU80_CONV_OFFLINE_CANDIDATE_BOARD_PENDING',created_utc=datetime.now(timezone.utc).isoformat(),run_id=run,soc_implementation_commit=flow['soc_implementation_commit'],cpu_implementation_commit='fefd93052c4974c5a45fcebb7a34cc3d44f9a8d9',cpu_hz=80000000,sys_hz=49500000,sbi_ratio=[99,160],bitstream_sha256=flow['bitstream_sha256'],frozen_inputs_sha256=snapshot['inputs'],sd_kit='artifacts/cpu80_conv_20261022/sd-kit',dense_weight_bank_lines=64,conv_compute_abi=3,board_tested=False,physical_media_written=False,remote_pushed=False,incomplete_acceptance=['Real-card SD readback and boot','New-bitstream board CoreMark, official Pikafish and convolution/multifd concurrency','Current HDMI/GUI/audio acceptance'],gate_receipts_sha256={p.relative_to(root).as_posix():sha(p) for p in ev.rglob('*') if p.is_file()},source_scope='Frozen458-input implementation identified by local commit; later documentation, portable tools and skills are bound separately by the candidate package inventory.')
write(root/'CPU80_CONV_CANDIDATE.json',model)
guide=fr'''# CPU80卷积离线候选（2026-10-22）

这是离线候选，尚未做新位流的实板验收。请先核对本包SHA256和候选清单。
CPU固定fefd9305/80MHz，SYS/MAC49.5MHz，OpenSBI99/160；SoC输入冻结{flow['soc_implementation_commit']}。
原生run为{run}，位流SHA256为{flow['bitstream_sha256']}。
完整SoC、卷积行为/CRC、全部原生综合前置、最终116行时序和20组max-skew均通过。
用户当前无法连接板卡；CoreMark、官方模型、卷积多fd隔离、HDMI/语音及实卡SD启动仍待验。
原f79443a2成绩只属于旧conv关闭位流，不用于本候选。

## 离线核验

解包后在SOC_CANDIDATE目录运行：

```powershell
python -B scripts/verify_cpu80_conv_candidate.py --root .
python skills/manage.py verify-delivery --package .
```

独立解包的完整回归/加载器字节重建凭据以ZIP哈希绑定的旁置回执提供。该凭据是离线验证，不是硬件交付完成凭据。
配对CPU源码归档为artifacts/cpu80_candidate_20261020/cpu-source-fefd9305.tar.gz。
全部458个FPGA输入在CPU80_CONV_CANDIDATE.json及artifacts/build_snapshot.json逐项绑定。
原生未过滤RTR/XML位于artifacts/cpu80_conv_20261022/native；外部I/O延迟历史覆盖缺口61/128保留。

## SD部署与启动

完整八文件目录为artifacts/cpu80_conv_20261022/sd-kit/sd-root。
先将SD卡连接PC并核对实际盘符、磁盘序列号/容量、FAT文件系统；不要按历史盘符操作。
下例E:仅为占位。部署工具默认只读计划，Apply会备份同名旧文件并回读校验，不格式化或分区。

```powershell
& artifacts/cpu80_conv_20261022/sd-kit/Copy_To_SD.ps1 -Destination E:\
# 核对正确介质和计划后再执行：
& artifacts/cpu80_conv_20261022/sd-kit/Copy_To_SD.ps1 -Destination E:\ -Apply
```

安全移除并返卡、上电板卡。在确认唯一PG2L100H/0x00602899且本包证据/哈希通过后，只向易失CRAM编程：

```powershell
& scripts/program_cram.ps1 -Program -SbitPath artifacts/soc_top.sbit -PdsRoot '<本机PDS目录>'
```

本包不写配置/SPI Flash。串口为115200/8N1，DTR/RTS关闭；实际COM口需重新枚举。
等待DDR ready和soc>提示，输入sdboot。ROM从Image.mmode/mmode.dtb进入包内正式二级SD引导器，
它从卡装载fw_jump.bin、Image、rootfs.cpio、soc.dtb、pikafish.pff、pikafish.atk并校验大小/CRC，
然后启动S-mode/Sv32 Linux。无需串口临时loader或RAM overlay；不配置上电自动SD引导。
进入/ #后核对CPU80MHz/SYS49.5MHz、驱动设备和GET_INFO能力，再进行卷积验收。

## 运行范围

保留Pikafish官方Stage A/B与64行dense权重bank，H128关闭。
卷积权重bank保持32行/128B DDR读取；内部保存低512MAC位和高半行32bit折叠校验，保持原读出级与周期。
该模式只在集成卷积frontend启用；DMA默认原始1024bit模式保持。窗口折叠/MMIO及MAC低半行经RTL和网表精确验证。
卷积MMIO+0x40..+0x7c、ABI3 compute已启用；程序通过驱动私有scratch和完整事务锁访问。
rootfs加入pango-mac-conv-window-test和pango-mac-conv-compute-test；原GUI、语音和Pikafish文件保留。
在系统空闲并按既有服务流程停止GUI作业后运行上述两程序；它们校验硬件结果/计数，失败应保留日志。
完整板测还须恢复GUI/语音、跑官方模型及多fd交替/驻留恢复，不能只以自测打印代替验收。

ABI3限Cin≤4/Cout≤16、kernel1/3/6、stride1/2、≤32卷积权重行，NHWC4/S8最终输出；
dense64约束ceil(Cin/4)×ceil(Cout/32)≤64保持。接口详见CPU80_Conv_Interface_20261022.md。
其他层走原dense/软件路径；本包不宣称完整YOLO加速、整图准确率或30fps/5秒目标达成。

SD加载器可由scripts/rebuild_cpu80_conv_loader.py在新目录独立重建并逐字节比较；
工具链需具备包内记录的WSL/RV32 GCC/QEMU。构建入口scripts/build_fpga.ps1仍执行全部原生门禁，
不得把综合或中间时序估计当最终通过。新构建产生新run，不能沿用本次硬件验收身份。
'''
(root/'docs/CPU80_Conv_Offline_Candidate_20261022.md').write_text(guide,encoding='utf-8')
readme=root/'README.md';text=readme.read_text(encoding='utf-8-sig');text=text[text.index('# SoC V2.1'):];prefix='''> 2026-10-22 CPU80卷积离线候选：完整SoC/原生前置/最终全角STA通过，实板与实卡SD待验。
> 完整八文件SD启动及接口范围见[候选说明](docs/CPU80_Conv_Offline_Candidate_20261022.md)。
> 下文原f79443a2成绩属于旧conv关闭版本；本候选的新身份见CPU80_CONV_CANDIDATE.json。

''';readme.write_text(prefix+text,encoding='utf-8')

# Reconcile final native evidence locally before sealing the portable library.
# The actual board and independent-unpack gates remain explicitly pending.
lesson=root/'skills/fpga-timing-optimization/references/lessons.md'
heading='## CPU80 folded-store final native '+run
if heading not in lesson.read_text(encoding='utf-8'):
 cpu_setup=min(x['wns'] for x in cpu_rows if x['kind']=='setup')
 cpu_hold=min(x['wns'] for x in cpu_rows if x['kind']=='hold')
 with lesson.open('a',encoding='utf-8') as f:
  f.write(f'\n{heading}\n\nThe frozen458-input SoC{flow["soc_implementation_commit"]} passed final116 timing rows and20skew rows at CPU80MHz/SYS49.5MHz. CPU setup{cpu_setup}ns/hold{cpu_hold}ns. Formal synthesis repeated the544-bit read/cache allocation and exact affine proof; three synthetic wrong-wiring/nonlinear-LUT/wrong-clock faults rejected. This is an offline candidate; independent ZIP unpack/rebuild is recorded separately, and real-card/board acceptance and remote publication remain pending.\n')
note=f'CPU80 folded-store{run}: full correctness, native116rows/20skew and physical register/cache/fold gates PASS; include complete SD8files and tools. Offline candidate only; independent ZIP verification follows, board unavailable and no remote push.'
for command in [['review','--note',note],['verify']]:
 subprocess.run([sys.executable,'-X','utf8',str(root/'skills/manage.py'),*command],cwd=root,check=True)

# Source-bound skill receipt after final documentation edits. Never change the
# native458-input identity to follow a later documentation/maintenance snapshot.
stage=work/('candidate-skills-stage-r2' if a.repackage else 'candidate-skills-stage');stage.mkdir(exist_ok=False)
for n in ['README.md','AGENTS.md','scripts/create_delivery.ps1','scripts/verify_delivery.ps1','scripts/invoke_project_skills.ps1','scripts/test_project_skills.py']:copy(root/n,stage/n)
subprocess.run([sys.executable,'-X','utf8',str(root/'skills/manage.py'),'stage','--root',str(root/'skills'),'--project',str(root),'--stage',str(stage)],check=True,cwd=root)
copy(stage/'SKILLS_DELIVERY.json',root/'SKILLS_DELIVERY.json')
from verify_cpu80_conv_candidate import validate
write(work/'candidate-content-prepack.json',validate(root))
fixture=root/'prebuilt/cpu80-policy-fixture'
fixture_required=set(read(fixture/'artifacts/build_snapshot.json')['inputs'])|set(read(fixture/'artifacts/build_evidence.json')['outputs'])
fixture_extras=[]
for n in sorted(fixture_required):
 p=fixture/n;assert p.is_file(),('Missing complete historical policy dependency',n)
 fixture_extras.append(p.relative_to(root).as_posix())
options=dict(artifacts=sorted(selected),output=str(output),extras=['CPU80_CONV_CANDIDATE.json','pds/bootrom.hex']+fixture_extras+[p.relative_to(root).as_posix() for p in ev.rglob('*') if p.is_file()],incomplete=model['incomplete_acceptance'])
write(work/'package-options.json',options)
psfile=work/'package-command.ps1'
q=lambda p:str(p).replace("'","''")
psfile.write_text("$ErrorActionPreference='Stop'\n"+"$o=Get-Content -LiteralPath '"+q(work/'package-options.json')+"' -Raw -Encoding UTF8 | ConvertFrom-Json\n"+"& '"+q(root/'scripts/create_candidate_delivery.ps1')+"' -Incomplete ([string[]]$o.incomplete) -IncludeArtifact ([string[]]$o.artifacts) -IncludeSource ([string[]]$o.extras) -OutputZip $o.output -PythonPath '"+q(sys.executable)+"'\nif ($LASTEXITCODE -ne 0) { throw 'Candidate packaging failed' }\n",encoding='utf-8')
output.parent.mkdir(parents=True,exist_ok=True)
result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(psfile)],cwd=root,capture_output=True,timeout=1800)
(work/'candidate-package.log').write_bytes(result.stdout+result.stderr);assert result.returncode==0,(result.stdout+result.stderr)[-3000:]
record=dict(status='CPU80_CONV_OFFLINE_CANDIDATE_PACKAGED_UNPACK_VERIFICATION_PENDING',archive=str(output),archive_sha256=sha(output),bytes=output.stat().st_size,run_id=run,board_tested=False,remote_pushed=False)
write(work/'package.json',record);output.with_suffix('.zip.sha256').write_text(record['archive_sha256']+'  '+output.name+'\n',encoding='ascii');print(json.dumps(record))
