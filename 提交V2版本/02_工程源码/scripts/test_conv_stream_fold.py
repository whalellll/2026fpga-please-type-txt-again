"""Compare complete weight DMA protocols with frozen P6, including folded storage."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,shutil,subprocess,traceback

root=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--baseline',action='store_true')
ap.add_argument('--faults',action='store_true')
ap.add_argument('--vendor-models',type=Path,help='Compile the actual synthesis identity LUT using installed vendor models')
a=ap.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
archive=root/'sim/reference/mac_conv_weight_dma_p6.v.gz'
identity=json.loads(archive.with_suffix('.json').read_text())
assert sha(archive)==identity['gzip_sha256']
raw=gzip.decompress(archive.read_bytes());assert hashlib.sha256(raw).hexdigest()==identity['source_sha256']
old=raw.decode();source=a.source.read_text()
reference=out/'reference.v'
reference.write_text(old.replace('module mac_conv_weight_dma #(','module mac_conv_weight_dma_stream_reference #(',1))
result=dict(status='RUNNING',source_sha256=sha(a.source),reference_sha256=identity['source_sha256'],checker_sha256=sha(Path(__file__)),cases=[],negative_cases=[])
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')

inputs=['clk','resetn','load_start','weight_src','weight_lines','model_id','generation','tile_id',
 'activate','compute_idle','window_done','read_en','read_addr','mem_req_ready','mem_rsp_valid',
 'mem_rsp_rdata','mem_rsp_last','mem_rsp_error']
outputs={'load_start_ready':'','activate_ready':'','active_valid':'','active_model_id':'[63:0]',
 'active_generation':'[31:0]','active_tile_id':'[31:0]','active_lines':'[5:0]','reuse_count':'[31:0]',
 'pending_valid':'','read_valid':'','read_data':'[1023:0]','mem_req_valid':'','mem_req_write':'',
 'mem_req_addr':'[31:0]','mem_req_len':'[2:0]','mem_rsp_ready':'','mem_abort':'','load_busy':'',
 'load_done':'','load_error':'','weight_ddr_bytes':'[31:0]','cycles':'[31:0]'}
miter='\n'+''.join('wire '+width+' __ref_'+n+';\n' for n,width in outputs.items())
miter+='mac_conv_weight_dma_stream_reference #('+','.join('.'+n+'('+n+')' for n in
 ['DDR_BASE','DDR_BYTES','TIMEOUT_CYCLES','FOLD_UPPER_HALF'])+') __ref ('+','.join('.'+n+'('+n+')' for n in inputs)+','+','.join('.'+n+'(__ref_'+n+')' for n in outputs)+');\n'
miter+='integer __checks=0;always @(negedge clk)begin __checks=__checks+1;\n'
miter+='if ({'+','.join(outputs)+'} !== {'+','.join('__ref_'+n for n in outputs)+'}) $fatal(1,"STREAM_FOLD_INTERFACE_MISMATCH");\n'
states=['state','source_r','timeout','lines_r','line_index','word_index','model_r','generation_r','tile_r','burst_words','rsp_index']
miter+='if ({'+','.join(states)+'} !== {'+','.join('__ref.'+n for n in states)+'}) $fatal(1,"STREAM_FOLD_PROTOCOL_MISMATCH");\n'
miter+='if(state==S_WRITE && (store_load !== __ref.store_load)) $fatal(1,"STREAM_FOLD_PRELOAD_MISMATCH");\n'
miter+='end\nfinal $display("STREAM_FOLD_CYCLE_MITER_PASS checks=%0d",__checks);\n'
iv=shutil.which('iverilog') or 'G:/fpga/workspace/tools/msys64/ucrt64/bin/iverilog.exe'
vvp=str(Path(iv).with_name('vvp.exe' if os.name=='nt' else 'vvp'))
env=dict(os.environ);env['PATH']=str(Path(iv).parent)+os.pathsep+env['PATH']

def run(label,rtl,fold):
    folder=out/label;folder.mkdir();p=folder/'candidate.v'
    p.write_text(rtl.replace('\nendmodule','\n'+miter+'endmodule',1))
    tb=(root/'sim/tb_mac_conv_weight_dma.sv').read_text()
    param=',.FOLD_UPPER_HALF('+str(fold)+')'+('' if a.baseline else ',.STREAM_UPPER_FOLD(1)')
    tb=tb.replace('.TIMEOUT_CYCLES(100)','.TIMEOUT_CYCLES(100)'+param)
    # The original model has monotonically increasing words. Keep its complete
    # timeout/error/overlap/swap stimulus, with an independent expected folded
    # representation for the 16-channel compute profile.
    if fold:
        tb=tb.replace('reg [31:0] expected_word;',
            'reg [31:0] expected_word; integer fw; reg [31:0] expected_upper;')
        needle='expected_word=base+line*32+j;'
        replacement='''expected_word=base+line*32+j;
                if(j>=16) begin
                    expected_word=0;
                    if(j==31) begin
                        expected_upper=0;
                        for(fw=16;fw<32;fw=fw+1)
                            expected_upper={expected_upper[26:0],expected_upper[31:27]} ^ (base+line*32+fw);
                        expected_word=expected_upper;
                    end
                end'''
        assert tb.count(needle)==1;tb=tb.replace(needle,replacement)
    test=folder/'tb.sv';test.write_text(tb);image=folder/'test.vvp'
    primitive_args=['-DSYNTHESIS','-y',str(a.vendor_models)] if a.vendor_models else []
    command=[iv,'-g2012',*primitive_args,'-s','tb_mac_conv_weight_dma','-o',str(image),str(p),str(reference),str(root/'rtl/mac_accel/mac_weight_double_buffer.v'),str(test)]
    proc=subprocess.run(command,capture_output=True,timeout=120,env=env)
    (folder/'compile.log').write_bytes(proc.stdout+proc.stderr);assert proc.returncode==0,proc.stderr[-2000:]
    proc=subprocess.run([vvp,str(image)],capture_output=True,timeout=120,env=env)
    log=folder/'run.log';log.write_bytes(proc.stdout+proc.stderr)
    return proc,log

try:
    # Independent GF(2) basis proof of the 16-word recurrence, including all
    # possible initial stale states: the first high word overwrites that state.
    def rol(x):return ((x<<5)|(x>>27))&0xffffffff
    for initial in [0,0xffffffff,0x5a812ef3]:
        for bit in range(512):
            words=[(1<<(bit%32)) if n==bit//32 else 0 for n in range(16)]
            streamed=initial
            for n,word in enumerate(words):streamed=word if n==0 else rol(streamed)^word
            expected=0
            for n,word in enumerate(words):
                amount=(5*(15-n))%32
                expected^=((word<<amount)|(word>>((32-amount)%32)))&0xffffffff
            assert streamed==expected
    result['recurrence_basis_checks']=1536
    for fold in [0,1]:
        proc,log=run('raw' if not fold else 'folded',source,fold)
        assert proc.returncode==0,(fold,proc.stdout[-2500:])
        count=re.search(rb'STREAM_FOLD_CYCLE_MITER_PASS checks=(\d+)',proc.stdout)
        assert count and int(count[1])>3000 and b'MAC_CONV_WEIGHT_DMA_PASS' in proc.stdout
        result['cases'].append(dict(profile=fold,cycles=int(count[1]),log_sha256=sha(log)));save()
    if a.faults:
        mutants=[('wrong-rotation',source.replace('{upper_fold[26:0], upper_fold[31:27]}','{upper_fold[25:0], upper_fold[31:26]}',1)),
                 ('stale-first-word',source.replace("word_index == 6'd16 ? mem_rsp_rdata :","word_index == 6'd17 ? mem_rsp_rdata :",1)),
                 ('wrong-low-word-enable',source.replace('!STREAM_FOLDED || !word_index[4]','!STREAM_FOLDED || word_index[4]',1))]
        for label,rtl in mutants:
            assert rtl!=source,label
            proc,log=run(label,rtl,1)
            assert proc.returncode!=0 and re.search(rb'STREAM_FOLD_\w+MISMATCH',proc.stdout+proc.stderr),(label,proc.stdout[-2000:])
            result['negative_cases'].append(dict(label=label,rejected=True,log_sha256=sha(log)));save()
    result['status']='CONV_STREAM_FOLD_RAW_AND_FOLDED_FULL_PROTOCOL_CYCLE_MITERS_PASS_NOT_NATIVE_STA_OR_BOARD'
except Exception:result.update(status='FAILED_CONV_STREAM_FOLD_PRESERVED',error=traceback.format_exc());raise
finally:save();print(result['status'],flush=True)
