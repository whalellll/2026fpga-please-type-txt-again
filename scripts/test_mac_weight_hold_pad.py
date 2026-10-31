from pathlib import Path
import argparse,hashlib,json,os,subprocess
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--icarus-bin',required=True);ap.add_argument('--vendor-models',required=True);a=ap.parse_args();p=Path(__file__).resolve().parents[1];d=a.output;assert not d.exists();d.mkdir()
vendor=Path(a.vendor_models);binary=a.icarus_bin;env=dict(os.environ);env['PATH']=binary+';G:/fpga/workspace/tools/msys64/mingw64/bin;'+env['PATH'];results={}
for mode in ['behavior','vendor']:
 image=d/(mode+'.vvp');cmd=[binary+'/iverilog.exe','-g2012','-s','tb_mac_weight_word_hold_pad','-y',str(vendor),'-o',str(image)]
 if mode=='vendor':cmd+=['-DSYNTHESIS']
 cmd+=[str(p/'rtl/mac_accel/MacAccelCore.v'),str(p/'sim/tb_mac_weight_word_hold_pad.sv')]
 for phase,args in [('compile',cmd),('run',[binary+'/vvp.exe',str(image)])]:
  r=subprocess.run(args,cwd=p,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120);(d/(mode+'-'+phase+'.txt')).write_bytes(r.stdout);assert r.returncode==0,(mode,phase,r.stdout[-2500:])
  if phase=='run':assert b'MAC_WEIGHT_WORD_HOLD_IDENTITY_CAPACITY_AND_CYCLE_PASS' in r.stdout
 results[mode]='PASS'
(d/'result.json').write_text(json.dumps({'status':'WEIGHT_BANK_BEHAVIOR_AND_VENDOR_IDENTITY_CAPACITY_CYCLE_PASS','results':results,'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ['rtl/mac_accel/MacAccelCore.v','sim/tb_mac_weight_word_hold_pad.sv']}},indent=2)+'\n');print('WEIGHT_BANK_FOCUS_PASS')
