"""Independent unpack regression: CPU134, architecture9, SoC and FC1 primitives.

All newly generated files/cache/temp remain under the extracted workspace or
the explicitly supplied output. No UART, JTAG, SD, Flash or Git push access.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,concurrent.futures,hashlib,json,os,shutil,subprocess,sys,threading,shlex
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cpu-cache',type=Path,required=True);p.add_argument('--tools',type=Path,default=Path('G:/fpga/workspace/tools'));p.add_argument('--java',default='G:/JavaSoft/OracleJdk/jdk25/jdk-25.0.2/bin/java.exe');p.add_argument('--pds',type=Path,required=True);p.add_argument('--wsl-distro',default='pikafish-verify');a=p.parse_args()
 root=a.root.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tmp=out/'tmp';tmp.mkdir();tools=out/'tools';tools.mkdir();cpu=root/'CPU_SOURCE/cpu';assert cpu.is_dir()
 for name in ['scripts/cpu120_zbc_regression/run_cpu_runtime_llvm.ps1','scripts/cpu120_regression/simulation_tools_llvm.ps1','scripts/bounded_process.cs']:
  assert (root/name).is_file() and not (root/name).is_symlink(),('Missing packaged runtime dependency',name)
 sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
 env=dict(os.environ,TEMP=str(tmp),TMP=str(tmp),TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1')
 host=Path(shutil.which('clang++.exe')).parent;env['CPU_HOST_LLVM_BIN']=str(host)
 env['PATH']=str(host)+';'+str(a.tools/'msys64/ucrt64/bin')+';'+str(a.tools/'msys64/mingw64/bin')+';'+env['PATH']
 env['WSLENV']='TMPDIR/p:TMP/p:TEMP/p'+(':'+env['WSLENV'] if env.get('WSLENV') else '')
 state=dict(status='RUNNING',owner_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),root=str(root),commands=[],checks_scope='Fresh source/RTL correctness after independent ZIP unpack; existing native proofs and board measurements remain separately hash-bound.')
 lock=threading.Lock()
 def save():
  with lock:(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')
 def run(name,args,cwd,marker=None,timeout=3600):
  item=dict(name=name,arguments=list(map(str,args)),cwd=str(cwd),started_utc=datetime.now(timezone.utc).isoformat());state['commands'].append(item);save();print('PACKAGE_REGRESSION_START',name,flush=True)
  log=out/(name+'.log')
  with log.open('xb') as stream:
   process=subprocess.Popen(item['arguments'],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);item['pid']=process.pid;save()
   try:code=process.wait(timeout=timeout)
   except subprocess.TimeoutExpired:
    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True);raise RuntimeError('Owned regression timeout '+name)
  item.update(exit_code=code,log_sha256=sha(log),completed_utc=datetime.now(timezone.utc).isoformat());save()
  assert code==0 and (not marker or marker.encode() in log.read_bytes()),name+' failed: '+str(log)
  print('PACKAGE_REGRESSION_PASS',name,flush=True)
 # Seed existing immutable dependency/tool inputs into this new test tree.
 for name in ['sbt-boot','sbt-global','ivy','coursier','firtool','host-atomic','sbt-launch-1.10.1.jar','repositories']:
  src=a.cpu_cache/name;assert src.exists() and not src.is_symlink(),src
  for item in ([src] if src.is_file() else [src,*src.rglob('*')]):
   assert not item.is_symlink() and not (getattr(item.lstat(),'st_file_attributes',0)&0x400),('Linked dependency input',item)
   assert item.resolve().is_relative_to(src.resolve() if src.is_dir() else src.parent.resolve()),item
  dst=tools/name
  if src.is_dir():shutil.copytree(src,dst,ignore=shutil.ignore_patterns('*.lock','*.lck'))
  else:shutil.copyfile(src,dst)
 env.update(COURSIER_CACHE=str(tools/'coursier'),CHISEL_FIRTOOL_PATH=str(tools/'firtool'),CPU120_CPU_SOURCE=str(root/'CPU_SOURCE'),CPU120_REGRESSION_ROOT=str(out),CPU120_HOST_ATOMIC=str(tools/'host-atomic'))
 wrapper=tools/'verilator-llvm'
 wrapper.write_text('''#!/usr/bin/env bash
set -euo pipefail
host=$(cygpath -m "$CPU_HOST_LLVM_BIN")
atomic=$(cygpath -m "$CPU120_HOST_ATOMIC")
exec /mingw64/bin/verilator --compiler clang -CFLAGS "-std=c++20" -MAKEFLAGS "CXX=$host/clang++.exe LINK=$host/clang++.exe" -LDFLAGS "-fuse-ld=lld -L$atomic" "$@"
''',newline='\n');env['CPU120_VERILATOR_WRAPPER']=str(wrapper)
 def msys(q):
  q=Path(q).resolve().as_posix();assert q[1:3]==':/';return '/'+q[0].lower()+q[2:]
 def linux(q):
  q=Path(q).resolve().as_posix();assert q[1:3]==':/';return '/mnt/'+q[0].lower()+q[2:]
 original=root/'scripts/cpu120_zbc_regression'
 isolated=(original/'run_cpu_test_isolated.sh').read_text().replace('/g/fpga/build/pds25-cpu120-20261101-03/cpu-source/cpu',msys(cpu))
 assert '/g/fpga/build/pds25-cpu120-20261101-03/' not in isolated,'Unresolved historical isolated-runner path'
 (out/'run_cpu_test_isolated.sh').write_text(isolated,newline='\n')
 generator=(original/'generate_qualified_architecture.py').read_text();needle="B=Path(__file__).resolve().parent;C=B/'cpu-source/cpu';out=C/'work/cpu-test'";assert needle in generator
 generator=generator.replace(needle,"B=Path(__file__).resolve().parent;C=Path(os.environ['CPU120_CPU_SOURCE'])/'cpu';out=C/'work/cpu-test'")
 (out/'generate_qualified_architecture.py').write_text(generator,newline='\n')
 flow=(original/'architecture-flow.sh').read_text().replace('/g/fpga/build/pds25-cpu120-zbc-20261101-01/cpu-source/cpu',msys(cpu)).replace('/g/fpga/build/pds25-cpu120-zbc-20261101-01',msys(out)).replace('/g/fpga/workspace/tools',msys(a.tools))
 assert '/g/fpga/build/pds25-cpu120-zbc-20261101-01/' not in flow,'Unresolved historical architecture-runner path'
 (out/'architecture-flow.sh').write_text(flow,newline='\n')
 def cpu_suite():
  args=[a.java,'-Xmx3g','-Xss16m','-XX:ActiveProcessorCount=4','-Djava.io.tmpdir='+str(tmp),'-Dsbt.color=false','-Dsbt.supershell=false','-Dsbt.boot.directory='+str(tools/'sbt-boot'),'-Dsbt.global.base='+str(tools/'sbt-global'),'-Dsbt.ivy.home='+str(tools/'ivy'),'-Dcoursier.cache='+str(tools/'coursier'),'-Dsbt.override.build.repos=true','-Dsbt.repository.config='+str(tools/'repositories'),'-De91c.socProbes=false','-De91c.zbc=true','-De91c.aluEntries=4','-De91c.memEntries=2','-De91c.fallbackSets=64','-De91c.fallbackHash=true','-De91c.rasDepth=2','-De91c.supervisor=true','-jar',tools/'sbt-launch-1.10.1.jar','set Test / parallelExecution := false','set Test / javaOptions += "-XX:ActiveProcessorCount=4"','test']
  run('cpu-unit134',args,cpu,'All tests passed.',14400)
  text=(out/'cpu-unit134.log').read_text(errors='replace');assert 'Total number of tests run: 134' in text and 'Suites: completed 49' in text
 def runtime_suite():
  run('architecture9',[a.tools/'msys64/usr/bin/bash.exe','--noprofile','--norc',msys(out/'architecture-flow.sh')],cpu,'Architectural self-checks passed.',3600)
  ps=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File']
  run('cdc',ps+[root/'scripts/run_cdc_tests.ps1','-IcarusBin',a.tools/'msys64/ucrt64/bin'],root,'SOC_CDC_TESTS_PASS',1800)
  run('peripherals',ps+[root/'scripts/run_soc_tests.ps1','-IcarusBin',a.tools/'msys64/ucrt64/bin'],root,None,1800)
  run('cpu-console',ps+[root/'scripts/cpu120_zbc_regression/run_cpu_runtime_llvm.ps1','-IcarusBin',a.tools/'msys64/ucrt64/bin','-MsysRoot',a.tools/'msys64','-ToolchainBin',a.tools/'riscv32-gcc16/bin','-CandidateCpuPath',root/'rtl/cpu/CoreTop.sv'],root,'CPU_CANDIDATE_TESTS_PASS',3600)
  vendor=a.pds/'arch/vendor/pango/verilog/simulation';receipt=json.loads((root/'docs/validation/cpu120-zbc-fc1-20261101/fc1-vendor-03/result.json').read_text())
  for name,digest in receipt['vendor_models_sha256'].items():assert sha(vendor/name)==digest,name
  for label,count in [('official-half0',16),('official-half1',16),('initial-real',6)]:
   case=out/label;case.mkdir()
   for name in ['model.hex','features.hex','golden.hex']:shutil.copyfile(root/'docs/validation/cpu120-zbc-fc1-20261101/fc1-vendor-03'/label/name,case/name)
   command='set -eu\ncd '+shlex.quote(linux(case))+'\nexport TMPDIR='+shlex.quote(linux(tmp))+'\niverilog -g2012 -DSYNTHESIS -y '+shlex.quote(linux(vendor))+' -s tb_pikafish_mlp_dedicated -Ptb_pikafish_mlp_dedicated.CASES='+str(count)+' -o test.vvp '+shlex.quote(linux(root/'sim/tb_pikafish_mlp_dedicated.sv'))+' '+shlex.quote(linux(root/'rtl/mac_accel/pikafish_mlp_dedicated.v'))+'\nvvp test.vvp\n'
   script=case/'run.sh';script.write_text(command,newline='\n');run('fc1-'+label,['wsl.exe','-d',a.wsl_distro,'--','sh',linux(script)],case,'PIKAFISH_DEDICATED_PASS',600)
 try:
  save()
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(cpu_suite),pool.submit(runtime_suite)]
   errors=[]
   for future in futures:
    try:future.result()
    except Exception as e:errors.append(repr(e))
   assert not errors,errors
  state.update(status='CPU120_INDEPENDENT_UNPACK_FULL_CPU134_ARCH9_SOC_FC1_38_REGRESSION_PASS',completed_utc=datetime.now(timezone.utc).isoformat(),unit_tests=134,unit_suites=49,architecture_groups=9,fc1_cases=38);save();print(state['status'],flush=True)
 except Exception as e:state.update(status='FAILED_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
