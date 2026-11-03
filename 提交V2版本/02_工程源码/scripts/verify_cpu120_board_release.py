"""Portable PDS25 CPU120 board/source/SD gate; no programming or Flash action."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,struct,statistics,tempfile,zlib
from coremark_crc_reference import CrcReference
from verify_board_release import parse_uart

BIT='c641cf7ea2897102f87cd6081a92ef3b2ed4802089756c33bc1302483931ef82'
RUN='b4dc02253edf402ea26104f106505857'
CPU='8c14579b40044a2ab6d6370f9a1866b998713a59'
IMPL='13ea2329d20867c17faae584bb887e13bf90ab60'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def safe(root,name):
 p=(root/name).resolve();assert p.is_relative_to(root) and not Path(root/name).is_symlink(),name
 assert p.is_file(),name
 return p
def cpio(path):
 raw=path.read_bytes();entries={};offset=0
 while offset+110<=len(raw):
  h=raw[offset:offset+110];assert h[:6]==b'070701'
  f=[int(h[6+8*i:14+8*i],16) for i in range(13)];size,namesize=f[6],f[11]
  assert namesize>0 and raw[offset+110+namesize-1]==0
  name=raw[offset+110:offset+110+namesize-1].decode();start=(offset+110+namesize+3)&~3
  assert start+size<=len(raw);data=raw[start:start+size];offset=(start+size+3)&~3
  if name=='TRAILER!!!':assert size==0 and not any(raw[offset:]);return entries
  assert name not in entries and not name.startswith('/') and '..' not in Path(name).parts
  entries[name]=(f,data)
 raise AssertionError('CPIO trailer absent')
def fdt(path):
 raw=path.read_bytes();head=struct.unpack_from('>10I',raw);assert head[0]==0xd00dfeed and head[1]==len(raw)
 offset,strings=head[2],head[3];stack=[];props={}
 while True:
  token=struct.unpack_from('>I',raw,offset)[0];offset+=4
  if token==1:
   end=raw.index(0,offset);stack.append(raw[offset:end].decode());offset=(end+4)&~3
  elif token==2:assert stack;stack.pop()
  elif token==3:
   length,index=struct.unpack_from('>II',raw,offset);offset+=8
   end=raw.index(0,strings+index);name=raw[strings+index:end].decode();key=('/'+'/'.join(x for x in stack if x),name)
   assert key not in props;props[key]=raw[offset:offset+length];offset=(offset+length+3)&~3
  elif token==4:pass
  elif token==9:assert not stack;return props
  else:raise AssertionError(('FDT token',token))
def verify_initrd_bounds(dtb,rootfs_bytes):
 props=fdt(dtb);number=lambda key:struct.unpack('>I',props[key])[0]
 assert number(('/cpus','timebase-frequency'))==120000000 and number(('/cpus/cpu@0','clock-frequency'))==120000000
 assert number(('/chosen','linux,initrd-start'))==0x03000000
 assert number(('/chosen','linux,initrd-end'))-0x03000000==rootfs_bytes,'Actual rootfs differs from DTB initrd bounds'
 return props
def verify(root,manifest,output,host_gcc):
 root=Path(root).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
 tmp=output/'tmp';tmp.mkdir();tempfile.tempdir=str(tmp)
 selection=read(safe(root,manifest));assert selection['schema']=='PDS25_CPU120_BOARD_RELEASE_V1' and selection['evidence_mode']=='BoardRelease'
 assert selection['implementation_commit']==IMPL and selection['cpu_implementation_commit']==CPU and selection['native_run']==RUN
 e=root/'docs/validation/cpu120-20261101';frozen=read(e/'frozen-inputs.json')
 compressed=read(e/'compressed-native-logs.json');assert compressed['status']=='LOSSLESS_GZIP_ALL_ORIGINAL_BYTES_SHA256_VERIFIED' and len(compressed['files'])==3
 for item in compressed['files']:
  path=safe(root,item['path']);assert sha(path)==item['sha256'] and path.stat().st_size==item['bytes']
  digest=hashlib.sha256();size=0
  with gzip.open(path,'rb') as stream:
   while chunk:=stream.read(1024*1024):digest.update(chunk);size+=len(chunk)
  assert size==item['original_bytes'] and digest.hexdigest()==item['original_sha256']
 packed=next(x for x in compressed['files'] if x['original_path'].endswith('/packed-info.txt'))
 assert packed['original_sha256']==read(e/'fc1-final-readback-01/result.json')['packed_info_sha256']
 assert frozen['source_commit']==IMPL and frozen['cpu_source_commit']==CPU
 overlays=read(e/'runtime-overlay.json')['files']
 for group,count in [('native_inputs_sha256',523),('verification_inputs_sha256',82)]:
  assert len(frozen[group])==count
  for name,digest in frozen[group].items():
   if name in overlays:
    q=overlays[name];assert name.startswith('linux/boot/') and q['frozen_sha256']==digest and sha(safe(root,q['frozen_path']))==digest
    assert q['runtime_path']==name and sha(safe(root,name))==q['runtime_sha256']
   else:assert sha(safe(root,name))==digest,name
 for name in ['artifacts/soc_top.sbit','artifacts/soc_v2_top.sbit']:assert sha(safe(root,name))==BIT
 snap=read(e/'native/build_snapshot.json');assert snap['run_id']==RUN and snap['inputs']==frozen['native_inputs_sha256']
 native=read(e/'tool-qualification-01/result.json');assert native['status']=='PDS25_CPU120_NATIVE_CONTROL_CDC_QUALIFICATION_PASS'
 assert native['source_commit']==IMPL and native['cpu_commit']==CPU and native['native_run']==RUN
 assert native['netlist_sha256']==sha(e/'native/soc_top_syn.vm')
 for name,info in native['receipts'].items():assert sha(e/'tool-qualification-01'/name)==info['sha256'] and 'PASS' in read(e/'tool-qualification-01'/name)['status']
 correctness=read(e/'correctness-for-native.json');assert correctness['unit_tests']==131 and correctness['unit_suites']==48 and correctness['architectural_cases']==8 and correctness['fresh_accelerator_primitive_cases']==38
 sta=read(e/'final-review-02/result.json');assert sta['final_sta_pass'] and sta['native_run']==RUN and sta['clock_count']==18
 report=e/'native/final-timing/soc_top.rtr';assert sha(report)==sta['artifact_sha256'][next(k for k in sta['artifact_sha256'] if k.endswith('report_timing\\soc_top.rtr'))]
 text=report.read_text();assert 'Design Summary : All Constraints Met.' in text
 summary=text.split('Design Summary :',1)[1].split('\nSlow Corner',1)[0];rows=[]
 for m in re.finditer(r'(?m)^\s*([^\r\n]+?) Summary\((Slow|Fast) Corner\):([\s\S]*?)\n=+',summary):
  for line in m[3].splitlines():
   q=line.split();offset=1 if m[1].strip()=='Minimum Pulse Width' else 2
   if len(q)==offset+4 and re.fullmatch(r'[-\d.]+',q[offset]) and q[-1].isdigit():
    assert float(q[offset])>=0 and float(q[offset+1])==0 and int(q[offset+2])==0 and int(q[offset+3])>0
    rows.append(q)
 assert len(rows)==124
 clocks=text.split('Clock Summary:',1)[1].split('Clock Groups:',1)[0]
 parsed={m[1]:float(m[2]) for m in re.finditer(r'(?m)^\s*(\S+)\s+(\d+\.\d+)\s+\{',clocks)}
 assert len(parsed)==18 and parsed['cpu_clk']==8.325 and parsed['sys_clk']==20.202
 physical=read(e/'physical-verification-01/result.json');assert 'PASS' in physical['status'] and '31_' in physical['status'] and '165_' in physical['status'] and '23_' in physical['status'] and '20_' in physical['status']
 program=read(e/'board-20261101-01/result.json');assert program['board_programmed'] and not program['flash_written'] and program['bitstream_sha256']==BIT
 cm=read(e/'coremark-board-01/result.json');assert cm['status']=='PASS' and cm['bitstream']['sha256']==BIT
 with CrcReference(root,host_gcc) as oracle:runs=parse_uart((e/'coremark-board-01/uart.log').read_text(),120000000,oracle)
 assert len(runs)==4
 waiver=read(e/'user-waiver-coremark-comparison.json');assert waiver['user_instruction']=='无需对照coremark' and not waiver['control_programmed']
 gui=read(e/'user-gui-confirmation.json');assert gui['answer']=='界面和鼠标正常' and gui['bitstream_sha256']==BIT
 logs=['sdboot','runtime-inspect-01','nnue-strict-01','nnue-force-01','nnue-verify-01','nnue-formal200-01','dedicated-probe-01','images-conv-01','engine-voice-clock-01','concurrent-02','gui-status-02']
 for name in logs:
  r=read(e/'linux-board-01'/(name+'.result.json'));assert 'PASS' in r['status'] and sha(e/'linux-board-01'/(name+'.uart'))==r['uart_sha256']
 probe=(e/'linux-board-01/dedicated-probe-01.uart').read_text();cases=re.findall(r'DEDICATED_OFFICIAL_CASE[^\n]*actual=(-?\d+) expected=(-?\d+)',probe)
 assert len(cases)==65 and all(a==b for a,b in cases) and 'mismatches=0 cases=65' in probe and 'actual=2392 expected=2392' in probe
 for name in ['nnue-strict-01','nnue-force-01','nnue-verify-01','nnue-formal200-01','concurrent-02']:
  log=(e/'linux-board-01'/(name+'.uart')).read_text();assert 'NNUE_LATENCY_CORRECTNESS_PASS' in log and 'fallbacks=0 mismatches=0' in log
  assert not re.search(r'failures=[1-9]|retries=[1-9]|errors=[1-9]',log)
 mixed=(e/'linux-board-01/concurrent-02.uart').read_text();assert all(x in mixed for x in ['samples=80000','overflows=0','MIXED_RESULT_audio=0','MIXED_RESULT_image=0','MIXED_RESULT_voice=0','output_crc=956e6551 no_fallback=1'])
 sd=root/'linux/boot';kit=read(root/'software/cpu120/sd/manifest.json');assert kit['bitstream_sha256']==BIT and len(kit['sd_root_files'])==8
 for name,info in kit['sd_root_files'].items():assert sha(sd/name)==info['sha256'] and (sd/name).stat().st_size==info['bytes']
 for row in kit['payloads']:
  raw=(sd/row['name']).read_bytes();assert len(raw)==row['bytes'] and f'{zlib.crc32(raw):08x}'==row['crc32']
 props=verify_initrd_bounds(sd/'soc.dtb',(sd/'rootfs.cpio').stat().st_size)
 assert (sd/'soc.dtb').read_bytes()==(sd/'mmode.dtb').read_bytes()
 archive=cpio(sd/'rootfs.cpio');component=json.loads(archive['etc/cpu120-software.json'][1]);assert component['bitstream_sha256']==BIT and component['native_run']==RUN and component['sbi_ratio']==[33,80]
 for line in archive['opt/main-xinyi/runtime.sha256'][1].decode().splitlines():
  digest,name=line.split('  ',1);assert hashlib.sha256(archive[name.lstrip('/')][1]).hexdigest()==digest,name
 for remote,local in [('xinyi-one','xinyi120'),('xinyi-engine','xinyi-engine'),('pikafish-nnue-latency-clint','pikafish-nnue-latency-clint')]:
  fields,data=archive['usr/bin/'+remote];assert data==(root/'software/cpu120/bin'/local).read_bytes()
  assert fields[1]&0o111 and data[:5]==b'\x7fELF\x01' and struct.unpack_from('<H',data,18)[0]==243 and struct.unpack_from('<I',data,36)[0]&7==0
 assert archive['usr/bin/pikafish-nnue-latency'][1]==archive['usr/bin/pikafish-nnue-latency-clint'][1]
 cpu_meta=read(root/'rtl/cpu/source.json');assert cpu_meta['sha256']==sha(root/'rtl/cpu/CoreTop.sv')
 if (root/'CPU_SOURCE').is_dir():assert sha(root/'CPU_SOURCE'/cpu_meta['source_path'])==cpu_meta['sha256']
 r=dict(status='PDS25_CPU120_PORTABLE_NATIVE_BOARD_COREMARK_CRC_SD_BOUNDS_RUNTIME_PASS_PACKAGE_COMPLETION_SEPARATE',native_run=RUN,bitstream_sha256=BIT,sta_rows=124,clocks=18,native_inputs=523,verification_inputs=82,coremark_runs=4,coremark_all_four_mean_per_mhz=statistics.mean(x['coremark_per_mhz'] for x in runs),coremark_comparison_required=False,nnue_official_cases=65,nnue_10ms_goal_met=False,sd_files=8,initrd_bytes=(sd/'rootfs.cpio').stat().st_size,formal_delivery_complete=False)
 (output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status']);return r
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--manifest',default='docs/validation/cpu120-20261101/release-manifest.json');p.add_argument('--output',type=Path,required=True);p.add_argument('--host-gcc',required=True);a=p.parse_args();verify(a.root,a.manifest,a.output,a.host_gcc)
