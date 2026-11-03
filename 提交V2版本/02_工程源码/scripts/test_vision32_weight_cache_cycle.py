"""Compare the registered weight cache to an immutable old layer and independent integer oracle."""
from pathlib import Path
import argparse,difflib,hashlib,importlib.util,json,os,re,shutil,subprocess,sys
from datetime import datetime,timezone
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--wsl-distro',default='pikafish-verify')
args=ap.parse_args();S=args.source_root.resolve()
sys.path.insert(0,str(S/'scripts'))
from workspace_paths import workspace_path
O=workspace_path(args.output)
R=S/'sim/reference/vision32_layer_lut_weight_reference.v'
assert hashlib.sha256(R.read_bytes().replace(b'\r\n',b'\n')).hexdigest()=='a9b06115f4dfd53a0ba040180c2a0c6adee9d0b38afd2cbf5be03e3de9bc4484'
source_head=subprocess.check_output(['git','-C',str(S),'rev-parse','HEAD'],text=True).strip() if (S/'.git').exists() else None
assert not O.exists();O.mkdir();T=O/'src';T.mkdir();E=O/'evidence';E.mkdir();TMP=O/'tmp';TMP.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
linux=lambda p:'/mnt/g/fpga/'+p.resolve().relative_to(Path('G:/fpga')).as_posix()
sys.path.insert(0,str(S/'scripts'))
spec=importlib.util.spec_from_file_location('frozen_vision_fixture',S/'scripts/test_vision32.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
inputs=['sim/reference/vision32_layer_lut_weight_reference.v','rtl/mac_accel/vision32_layer.v','rtl/mac_accel/vision32_pe.v','sim/tb_vision32_layer.sv',
    'scripts/test_vision32.py','sim/vectors/vision32_shapes.json','config/clocks.json',
    'linux/mac_accel/kernel/pango_mac.c','linux/mac_accel/pango_mac_uapi.h']
origin={n:sha(S/n) for n in inputs}
record=dict(status='RUNNING_ISOLATED_CACHE_CYCLE_STUDY_NOT_NATIVE_NOT_BOARD',
    source_commit=source_head,reference_implementation_commit='082b737d3cbbdfc536915b5e506008c0819c82c4',source_sha256=origin,
    device='PG2L100H-6-FBG676',native_tool='PDS2022.2-SP6.4 (not invoked)',
    cpu_hz=80000000,sys_hz=49500000,testbench_period_ns=10,
    scope='Synthetic integer full-layer reference/variant cycle lockstep. Simulation time is not board latency; no actual BRAM inference/resource/STA claim.',
    commands=[],started_utc=datetime.now(timezone.utc).isoformat())
def save():(O/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
save()
old=R.read_text(encoding='utf-8')
(T/'original.v').write_text(old,encoding='utf-8',newline='\n')
assert old.count('module vision32_layer #(')==1
reference=old.replace('module vision32_layer #(','module vision32_layer_reference #(',1)
(T/'reference.v').write_text(reference,encoding='utf-8',newline='\n')
shutil.copyfile(S/'rtl/mac_accel/vision32_pe.v',T/'vision32_pe.v')
shutil.copyfile(S/'sim/tb_vision32_layer.sv',T/'tb.sv')
shutil.copyfile(R,T/'original-source-bytes.v.raw')
test=(T/'tb.sv').read_text(encoding='utf-8')
assert test.count(' integer b;')==1
test=test.replace(' integer b;',' integer b;\n integer cache_feed_aborts=0,cache_feed_resets=0;')
anchor='     if((fault==3 && active && !is_write && !aborted) ||'
assert test.count(anchor)==1
test=test.replace(anchor,'''     if(fault==6 && g_direct.dut.reference.state==16 && !aborted)begin
       write_reg(8'h48,2);aborted=1;cache_feed_aborts=cache_feed_aborts+1;
     end
     if(fault==7 && g_direct.dut.reference.state==16 && !aborted)begin
       @(negedge clk);resetn=0;
       repeat(3)@(negedge clk);resetn=1;
       read_beats=0;write_beats=0;writes_seen=0;
       for(j=0;j<16;j=j+1)begin write_reg(8'h4c,j);write_reg(8'h50,cfg[j]);end
       write_reg(8'h48,1);fault=0;aborted=1;cache_feed_resets=cache_feed_resets+1;
     end
'''+anchor)
anchor='  $display("VISION32_ALL_PASS cases=%0d soc=%0d",CASES,SOC);$finish;'
assert test.count(anchor)==1
test=test.replace(anchor,'''  if(cache_feed_aborts!=1 || cache_feed_resets!=1)$fatal(1,"CACHE_FEED_EVENT_COVERAGE_MISSING");
  $display("CACHE_FEED_EVENTS abort=%0d reset_restart=%0d",cache_feed_aborts,cache_feed_resets);
'''+anchor)
(T/'tb.sv').write_text(test,encoding='utf-8',newline='\n')
outputs={'reg_rd_data':32,'mem_req_valid':1,'mem_req_write':1,'mem_req_addr':32,'mem_req_len':3,
    'mem_w_valid':1,'mem_w_data':32,'mem_w_strb':4,'mem_w_last':1,'mem_rsp_ready':1,'mem_abort':1,'busy_out':1}
ins='clk resetn reg_wr_en reg_wr_addr reg_wr_data reg_wr_strb reg_rd_addr mem_req_ready mem_w_ready mem_rsp_valid mem_rsp_rdata mem_rsp_last mem_rsp_error'.split()
header=old[:old.index('\n);')+4].replace('output reg','output wire')
wrapper=header+'\n'
for name,width in outputs.items():wrapper+=' wire '+('['+str(width-1)+':0] ' if width>1 else '')+'c_'+name+';\n'
params='#(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES),.SERIAL_LEGACY_QUANT(SERIAL_LEGACY_QUANT))'
for module,instance,prefix in [('vision32_layer_reference','reference',''),('vision32_layer_candidate','candidate','c_')]:
    conns=['.'+n+'('+n+')' for n in ins]+['.'+n+'('+prefix+n+')' for n in outputs]
    wrapper+=' '+module+' '+params+' '+instance+'('+','.join(conns)+');\n'
wrapper+='''
 integer compared_cycles=0,feed_cycles=0,row1023=0,row1024=0,row1151=0,tail_feeds=0;
 always @(posedge clk) if(resetn && reference.state==16)begin
  feed_cycles=feed_cycles+1;
  if(reference.weight_ra==1023)row1023=row1023+1;
  if(reference.weight_ra==1024)row1024=row1024+1;
  if(reference.weight_ra==1151)row1151=row1151+1;
  if(reference.weight_ra[10])tail_feeds=tail_feeds+1;
 end
 always @(negedge clk)begin
  #2;
  if(resetn)begin
   compared_cycles=compared_cycles+1;
'''
for name in outputs:
    wrapper+='   if('+name+' !== c_'+name+')$fatal(1,"CACHE_LOCKSTEP_OUTPUT_MISMATCH '+name+' cycle%0d",compared_cycles);\n'
wrapper+='''
   if(reference.read_valid !== candidate.read_valid)$fatal(1,"CACHE_LOCKSTEP_VALID_MISMATCH");
   if(reference.read_valid && (reference.weight_q !== candidate.weight_q || reference.activations_q !== candidate.activations_q))
    $fatal(1,"CACHE_LOCKSTEP_FEED_MISMATCH cycle%0d old%h new%h",compared_cycles,reference.weight_q,candidate.weight_q);
  end
 end
 final begin
  $display("CACHE_LOCKSTEP_COVER cycles=%0d feeds=%0d row1023=%0d row1024=%0d row1151=%0d tail=%0d",compared_cycles,feed_cycles,row1023,row1024,row1151,tail_feeds);
  if(!row1023 || !row1024 || !row1151 || !tail_feeds)$error("CACHE_LOCKSTEP_BOUNDARY_COVERAGE_MISSING");
 end
endmodule
'''
(T/'dual_wrapper.sv').write_text(wrapper,encoding='utf-8',newline='\n')
vectors=O/'vectors';vectors.mkdir()
jobs=[dict(name='random1152_tail17',w=4,h=3,ci=128,co=17,k=3,s=1,p=0,flags=2),
      dict(name='random1026_boundary',w=3,h=3,ci=114,co=9,k=3,s=1,p=0,flags=2),
      dict(name='kernel6_1044_exact',w=6,h=6,ci=29,co=9,k=6,s=1,p=0,flags=4),
      dict(name='extreme1152',w=3,h=3,ci=128,co=17,k=3,s=1,p=0,flags=2,extreme=True)]
jobs+=fixture.cases()[:4]
jobs += [j for j in fixture.cases() if j['name'].startswith(('fault_','zero_width','high_channel','too_deep','overlap','out_of_range','bad_scale','bad_shift'))]
jobs += [dict(name='exact_silu_tail',w=3,h=3,ci=7,co=9,k=3,s=1,p=1,flags=5),
         dict(name='quant_edges',w=1,h=1,ci=1,co=64,k=1,s=1,p=0,flags=0,quant_edges=True)]
jobs += [dict(name='abort_during_feed',w=3,h=3,ci=128,co=9,k=3,s=1,p=0,flags=2,study_event=6),
         dict(name='reset_feed_and_restart',w=3,h=3,ci=128,co=9,k=3,s=1,p=0,flags=2,study_event=7),
         dict(name='post_reset_different_weights',w=3,h=3,ci=114,co=17,k=3,s=1,p=0,flags=2)]
manifest=[fixture.fixture(j,i,vectors) for i,j in enumerate(jobs)]
for i,j in enumerate(jobs):
    if j.get('study_event'):
        ctl=vectors/('case-'+str(i)+'.ctl');fields=ctl.read_text().splitlines()
        fields[1]='00000001' if j['study_event']==6 else '00000000'
        fields[2]=f"{j['study_event']:08x}";ctl.write_text('\n'.join(fields)+'\n')
        manifest[i]['expected_error']=j['study_event']==6
(vectors/'vectors.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
vector_hashes={p.name:sha(p) for p in vectors.iterdir() if p.is_file()}
record.update(cases=len(jobs),vector_files_sha256=vector_hashes,
    wrapper_sha256=sha(T/'dual_wrapper.sv'),baseline_integer_oracle='independent NumPy NHWC/OIHW fixture; expected MAC counts and DDR byte counters from original maintained test')
save()
env=dict(os.environ,TEMP=str(TMP),TMP=str(TMP),TMPDIR=str(TMP),PYTHONUTF8='1')
def run(label,command_args,negative=False,timeout=1200):
    cmd=['wsl.exe','-d',args.wsl_distro,'--cd',linux(vectors),'--','env','PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'TMPDIR='+linux(TMP),'TMP='+linux(TMP),'TEMP='+linux(TMP),*map(str,command_args)]
    log=E/(label+'.log')
    with log.open('xb') as f:p=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    raw=log.read_bytes();record['commands'].append(dict(name=label,argv=cmd,exit=p.returncode,log_sha256=sha(log)));save()
    if negative:
        assert p.returncode!=0 and b'CACHE_LOCKSTEP_' in raw and b'MISMATCH' in raw,(label,raw[-2000:])
    else:assert p.returncode==0,(label,raw[-2500:])
    print(label+': '+('EXPECTED_REJECTION' if negative else 'PASS'),flush=True)
    return raw
def simulate(label,text,negative=False):
    rtl=T/(label+'.v');rtl.write_text(text.replace('module vision32_layer #(','module vision32_layer_candidate #(',1),encoding='utf-8',newline='\n')
    binary=O/(label+'.vvp')
    record.setdefault('simulation_sources_sha256',{})[label]={p.name:sha(p) for p in [T/'vision32_pe.v',T/'reference.v',rtl,T/'dual_wrapper.sv',T/'tb.sv']};save()
    run(label+'-compile',['iverilog','-g2012','-s','tb_vision32_layer','-Ptb_vision32_layer.CASES='+str(len(jobs)),
        '-Ptb_vision32_layer.SOC=0','-o',linux(binary),linux(T/'vision32_pe.v'),linux(T/'reference.v'),linux(rtl),linux(T/'dual_wrapper.sv'),linux(T/'tb.sv')],timeout=120)
    # Avoid Windows/WSL sh -c argument quoting entirely.
    raw=run(label+'-run',['vvp',linux(binary)],negative=negative)
    if not negative:
        assert ('VISION32_ALL_PASS cases='+str(len(jobs))).encode() in raw
        assert b'CACHE_LOCKSTEP_COVER' in raw and b'COVERAGE_MISSING' not in raw
    return raw
try:
    baseline=simulate('baseline-selfcheck-01',old)
    new=(S/'rtl/mac_accel/vision32_layer.v').read_text(encoding='utf-8')
    (T/'candidate.v').write_text(new,encoding='utf-8',newline='\n')
    candidate=simulate('candidate-cycle-01',new)
    base_cases=re.findall(rb'VISION32_CASE_PASS[^\r\n]+',baseline)
    new_cases=re.findall(rb'VISION32_CASE_PASS[^\r\n]+',candidate)
    assert len(base_cases)==len(jobs) and base_cases==new_cases,'Case cycle/byte counts changed'
    mutants={
      'tail-selection-disabled':new.replace('assign weight_q=weight_tail_selected_q ?','assign weight_q=1\'b0 ?'),
      'tail-row-off-by-one':new.replace('weight_tail_lo_q<=weight_tail_lo[weight_ra[6:0]];','weight_tail_lo_q<=weight_tail_lo[(weight_ra[6:0]+7\'d1)&7\'h7f];'),
      'tail-high-write-lost':new.replace('if(load_index[0])weight_tail_hi[load_index[7:1]]<=mem_rsp_rdata;','if(1\'b0)weight_tail_hi[load_index[7:1]]<=mem_rsp_rdata;')}
    for name,mutant in mutants.items():
        assert mutant!=new,name;simulate('negative-'+name,mutant,True)
    assert all(sha(S/n)==h for n,h in origin.items())
    assert all(sha(vectors/n)==h for n,h in vector_hashes.items())
    patch=''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/rtl/mac_accel/vision32_layer.v',tofile='b/rtl/mac_accel/vision32_layer.v'))
    (O/'weight-bram-cycle-candidate.patch').write_text(patch,encoding='utf-8',newline='\n')
    record.update(status='VISION_WEIGHT_CACHE_BANKED_REGISTERED_READ_CYCLE_LOCKSTEP_AND_INTEGER_ORACLE_PASS_NOT_NATIVE_NOT_BOARD',
        changed_rtl_sha256=sha(T/'candidate.v'),patch_sha256=sha(O/'weight-bram-cycle-candidate.patch'),
        baseline_log_sha256=sha(E/'baseline-selfcheck-01-run.log'),candidate_log_sha256=sha(E/'candidate-cycle-01-run.log'),
        feed_abort_and_reset_restart_covered=True,prepared_sources_sha256={p.name:sha(p) for p in T.iterdir() if p.is_file()},
        per_case_cycle_and_byte_lines_identical=True,negative_mutations_rejected=sorted(mutants),
        source_inputs_untouched=True,actual_bram_inference_verified=False,whole_soc_resource_gain_verified=False,
        completed_utc=datetime.now(timezone.utc).isoformat());save();print(record['status'],flush=True)
except BaseException as error:
    record.update(status='ISOLATED_CACHE_STUDY_FAILED_PRESERVED_NOT_NATIVE_NOT_BOARD',error=repr(error),completed_utc=datetime.now(timezone.utc).isoformat());save();raise
