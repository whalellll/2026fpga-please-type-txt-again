"""Exercise retained dense/gather paths and inert retired H128 MMIO."""
import argparse,json,os,re,subprocess,shutil
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--icarus-bin',type=Path);ap.add_argument('--expect-old-rejection',action='store_true');a=ap.parse_args()
assert not a.output.exists();a.output.mkdir(parents=True)
suffix='.exe' if os.name=='nt' else ''
iv=str(a.icarus_bin/('iverilog'+suffix)) if a.icarus_bin else shutil.which('iverilog')
vvp=str(a.icarus_bin/('vvp'+suffix)) if a.icarus_bin else shutil.which('vvp')
assert iv and vvp,'Icarus is required; pass --icarus-bin or set PATH'
env=dict(os.environ)
if a.icarus_bin:env['PATH']=str(a.icarus_bin)+os.pathsep+env['PATH']
sources=[a.root/'rtl/soc/axi_2x1_arbiter.v',*sorted((a.root/'rtl/mac_accel').glob('*.v')),a.root/'sim/gtp_apm_e2_perf_sim.v',a.root/'sim/axi_shared_ram.sv',a.root/'sim/tb_soc_mac_accel.sv']
outputs={}
for enabled in [1,0]:
 image=a.output/f'h128-{enabled}.vvp'
 cmd=[iv,'-g2012','-DPIKAFISH_BOOT_MIN_DRM','-s','tb_soc_mac_accel',f'-Ptb_soc_mac_accel.H128_ENABLED={enabled}','-o',str(image),*map(str,sources)]
 r=subprocess.run(cmd,cwd=a.root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,env=env);(a.output/f'compile-{enabled}.txt').write_bytes(r.stdout);assert r.returncode==0,(r.returncode,r.stdout[-2000:])
 r=subprocess.run([vvp,str(image)],cwd=a.root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,env=env);(a.output/f'run-{enabled}.txt').write_bytes(r.stdout);text=r.stdout.decode(errors='replace').replace('\r','');outputs[enabled]=text
 if a.expect_old_rejection and not enabled:
  assert r.returncode!=0 and 'disabled H128 MMIO must read zero' in text
  print('H128_TEST_REJECTS_OLD_ALWAYS_ENABLED_HARDWARE');raise SystemExit(0)
 assert r.returncode==0 and 'FATAL:' not in text and 'ERROR:' not in text,text[-2200:]
 assert 'SOC_STAGEA_GATHER_PASS' in text and 'S16_MAX_OUTPUT_PASS pixels=16 cout=256 words=4096' in text
 if not enabled:assert 'H128_DISABLED_MMIO_IRQ_DDR_PASS registers=32 idle_cycles=64' in text
patterns=['DDR_BIAS_MAC_PASS','PARTIAL_PACKED_MAC_PASS','MAX_CIN_MAC_PASS','MAX_COUT_MAC_PASS','LEGACY_MAX_COUT_MAC_PASS','MAX_PIXELS_MAC_PASS','S16_MAX_OUTPUT_CYCLES']
metrics={}
for name in patterns:
 x=[re.findall(r'^'+name+r' cycles=(\d+)$',outputs[k],re.M) for k in [1,0]]
 assert x[0] and x[0]==x[1],(name,x);metrics[name]=int(x[0][0])
record={'status':'H128_RETIREMENT_FUNCTIONAL_AND_CYCLE_PASS','dense_cycles_identical':metrics,'enabled_and_disabled_profiles_tested':True,'gather_and_dense_concurrency':'PASS','disabled_mmio_registers':32,'disabled_idle_cycles':64,'scope':'RTL only; no native resource, routed STA or board acceptance.'}
(a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('H128_RETIREMENT_FUNCTIONAL_AND_CYCLE_PASS')
