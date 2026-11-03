"""Check actual half-output dense DMA, unchanged DDR bytes, ABI, gather, resets and enabled-conv isolation."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--icarus-bin',type=Path,required=True);a=ap.parse_args()
root=Path(__file__).resolve().parents[1];a.output.mkdir(parents=True,exist_ok=False)
env=dict(os.environ);env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
iv=str(a.icarus_bin/'iverilog.exe');vvp=str(a.icarus_bin/'vvp.exe')
sources=[root/'rtl/soc/axi_2x1_arbiter.v',*sorted((root/'rtl/mac_accel').glob('*.v')),root/'sim/gtp_apm_e2_perf_sim.v',root/'sim/axi_shared_ram.sv',root/'sim/tb_soc_mac_accel.sv']
texts={};logs={};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for enabled in [0,1]:
 image=a.output/f'conv-{enabled}.vvp'
 for label,cmd in [('compile',[iv,'-g2012','-DPIKAFISH_BOOT_MIN_DRM','-s','tb_soc_mac_accel','-Ptb_soc_mac_accel.H128_ENABLED=0','-Ptb_soc_mac_accel.HALF_DENSE=1',f'-Ptb_soc_mac_accel.CONV_ENABLED={enabled}','-o',str(image),*map(str,sources)]),('run',[vvp,str(image)])]:
  result=subprocess.run(cmd,cwd=root,env=env,capture_output=True,timeout=300)
  log=a.output/f'{label}-{enabled}.log';log.write_bytes(result.stdout+result.stderr);logs[log.name]=sha(log)
  assert result.returncode==0 and not re.search(rb'(?m)^\s*(ERROR:|FATAL:)',result.stdout+result.stderr),(label,enabled,(result.stdout+result.stderr)[-2000:])
  if label=='run':
   text=result.stdout.decode(errors='replace').replace('\r','');assert 'SOC_STAGEA_GATHER_PASS' in text and 'S16_MAX_OUTPUT_PASS pixels=16 cout=256 words=4096' in text and 'H128_DISABLED_MMIO_IRQ_DDR_PASS' in text;texts[enabled]=text
metrics={}
for name in ['DDR_BIAS_MAC_PASS','PARTIAL_PACKED_MAC_PASS','MAX_CIN_MAC_PASS','MAX_COUT_MAC_PASS','LEGACY_MAX_COUT_MAC_PASS','MAX_PIXELS_MAC_PASS','S16_MAX_OUTPUT_CYCLES']:
 rows=[re.findall(r'^'+name+r' cycles=(\d+)$',texts[e],re.M) for e in [0,1]]
 assert rows[0] and rows[0]==rows[1],(name,rows);metrics[name]=int(rows[0][0])
(a.output/'result.json').write_text(json.dumps(dict(status='HALF_OUTPUT_DENSE_GATHER_DDR_CONV_ISOLATION_PASS_NOT_STA_OR_BOARD',metrics=metrics,logs_sha256=logs,source_sha256={p.relative_to(root).as_posix():sha(p) for p in sources}),indent=2)+'\n')
print('HALF_OUTPUT_DENSE_GATHER_DDR_CONV_ISOLATION_PASS_NOT_STA_OR_BOARD')
