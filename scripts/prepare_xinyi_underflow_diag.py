"""One bounded event-position diagnostic on the frozen e544/4ms source."""
from pathlib import Path
import argparse, json, hashlib, shutil, subprocess, shlex, gzip
from picture_workspace import ROOT, workspace_path, wsl_path

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 base=workspace_path(a.base);bound=json.loads((base.parent/'result.json').read_bytes())
 assert bound['helper']['sha256']=='e544ee464746ffe5e1b037f48b4d78ff1d5cefba228abdb235d66485a55ec9e4'
 for n,h in bound['source_sha256'].items():assert hashlib.sha256((base/n).read_bytes()).hexdigest()==h
 out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False);src=out/'source';shutil.copytree(base,src)
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();d=src/'linux/xinyi_board'
 for n in ['speech_underflow_diag_r18.c','speech_underflow_diag_test_r18.c']:(d/n).write_bytes((ROOT/'linux/xinyi_board'/n).read_bytes())
 (d/'speech_uf_base_linux.inc').write_bytes(b'#include "../voice_speech/xq_speech_linux.c"\n')
 original=(src/'linux/voice_speech/xq_speech.c').read_text();fn=original[original.index('int xqs_stream('):]
 changes=[('last=io->now_us(io->context); before=io->underflows(io->context);','last=io->now_us(io->context); before=io->underflows(io->context); uf_begin(before,n);'),
  ('  io->write(io->context,(uint16_t)samples[i]);','  io->write(io->context,(uint16_t)samples[i]);\n  if(i%64==63)uf_poll(io,i+1);'),
  ('    *delta=io->underflows(io->context)-before; return 0;','    *delta=io->underflows(io->context)-before; uf_observe(io,i,before+*delta); return 0;'),
  ('   *delta=io->underflows(io->context)-before; return 0;','   *delta=io->underflows(io->context)-before; uf_observe(io,i+1,before+*delta); return 0;'),
  (' *delta=io->underflows(io->context)-before;\n return 1;',' *delta=io->underflows(io->context)-before; uf_observe(io,n,before+*delta);\n return 1;')]
 for old,new in changes:
  assert fn.count(old)==1,(old,fn.count(old));fn=fn.replace(old,new)
 (d/'speech_uf_stream.inc').write_bytes(fn.encode())
 (out/'stream-transform.json').write_bytes(json.dumps(dict(base='e544_prime64',original_sha256=hashlib.sha256(original.encode()).hexdigest(),generated_sha256=hashlib.sha256(fn.encode()).hexdigest(),exact_replacements=changes),indent=2).encode())
 result=dict(status='FAILED_PRESERVED',hardware_used=False,production_selected=False,base_helper_sha256='e544ee464746ffe5e1b037f48b4d78ff1d5cefba228abdb235d66485a55ec9e4')
 def run(name,args):
  with (out/(name+'.log')).open('xb') as log:p=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','--','sh','-c','ulimit -c 0\nexec timeout --kill-after=3 60 '+shlex.join(args)],stdout=log,stderr=subprocess.STDOUT,timeout=75)
  assert p.returncode==0,(name,(out/(name+'.log')).read_text(errors='replace')[-2000:])
 try:
  common=['-std=gnu11','-O2','-Wall','-Wextra','-Werror','-DXINYI_COACH_MOVE_AUDIO=1','-DXINYI_BATTLE_R17=1','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-I'+wsl_path(d),'-I'+wsl_path(src/'linux/voice_speech'),'-I'+wsl_path(src/'sw/xiangqi')]
  bank=wsl_path(src/'linux/voice_speech/xq_whole_bank.c')
  for name,cc,flags,runner in [('host','cc',[],[]),('sanitizer','cc',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-no-pie'],[]),('rv32','/opt/toolchain/bin/riscv32-linux-musl-gcc',['-static','-march=rv32ima','-mabi=ilp32','-mstrict-align'],['qemu-riscv32'])]:
   exe=out/name;run(name+'-build',[cc,*common,*flags,wsl_path(d/'speech_underflow_diag_test_r18.c'),bank,'-o',wsl_path(exe)]);run(name,[*runner,wsl_path(exe)])
  exe=out/'speech-underflow-diag.rv32.elf';run('diagnostic-build',['/opt/toolchain/bin/riscv32-linux-musl-gcc',*common,'-static','-march=rv32ima','-mabi=ilp32','-mstrict-align','-s',wsl_path(d/'speech_underflow_diag_r18.c'),bank,'-o',wsl_path(exe)])
  data=exe.read_bytes();packed=gzip.compress(data,mtime=0);(out/'speech-underflow-diag.rv32.elf.gz').write_bytes(packed);assert len(packed)<=61440
  result.update(status='DIAGNOSTIC_ONLY_REAL_STREAM_HOST_SAN_RV32_OUTPUT_DELTA_RC_CANCEL_BOUNDS_PASS_NOT_BOARD',elf_path=str(exe),elf_bytes=len(data),elf_sha256=sha(exe),gzip_bytes=len(packed),gzip_sha256=hashlib.sha256(packed).hexdigest(),source_sha256={p.relative_to(src).as_posix():sha(p) for p in src.rglob('*') if p.is_file()},event_bytes=640,event_capacity=32,poll_samples=64,FIFO_syscalls_added=False,IRQ_reads='one before preparation and one after cleanup',command='/run/speech-underflow-diag PCM_DIR > /run/uf.log 2>&1',runtime_bound_seconds=12)
 finally:(out/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
 print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},indent=2))

if __name__=='__main__':main()
