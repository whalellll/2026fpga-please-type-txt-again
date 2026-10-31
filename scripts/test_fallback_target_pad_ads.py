"""Synthetic native-mapping fault fixtures; never STA or board evidence."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
from audit_fallback_target_pad_ads import audit, bind_result


def fixture():
    pieces=[]
    for parent,kind,name in [('soc_top','core_top','u_cpu'),('core_top','cpu_core_top','u_cpu_wrapper'),
        ('cpu_core_top','CoreTop','u_cpu'),('CoreTop','Core','core'),
        ('Core','CoreFrontend','frontend'),('CoreFrontend','FallbackBtb','fallback')]:
        pieces.append(f'module {parent};\n {kind} {name} ();\nendmodule\n')
    pairs=[]
    for n in range(16):
        pairs.append(f''' (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCCAAAAAAAA))
 \\data_pad[{n}].u_hold_dual_lut (
 .I0(dataIn[{2*n}]),.I1(dataIn[{2*n+1}]),.I2(1'b0),.I3(1'b0),.I4(1'b0),.I5(1'b1),
 .Z5(dataOut[{2*n}]),.Z(dataOut[{2*n+1}]));\n''')
    pieces.append('module PangoFallbackTargetPad(input [31:0] dataIn, output [31:0] dataOut);\n'+''.join(pairs)+'endmodule\n')
    padded=','.join(f'padded[{i}]' for i in reversed(range(32)))
    pieces.append('''module FallbackBtb(input [31:0] io_updTarget,input clock);
 wire [31:0] padded;
 PangoFallbackTargetPad targetHoldPad (.dataIn(io_updTarget),.dataOut(padded));
'''+''.join(f''' entryMem_64x64 entryMem_{way}_ext (
 .W0_data({{32'b0,{padded}}}),.R0_clk(clock),.W0_en(we{way}),.R0_addr(upd),.R1_addr(query));
''' for way in range(2))+'endmodule\n')
    ram='''module entryMem_64x64(input [63:0] W0_data,input [5:0] R0_addr,input [5:0] R1_addr,
 input R0_clk,input W0_en,output [63:0] R1_data);
'''
    for bit in range(32):
        ram+=f''' GTP_RAM64X1DP Memory_1_{bit} (
 .DI(W0_data[{bit}]),.DO(R1_data[{bit}]),.RADDR(R1_addr),.WADDR(R0_addr),.WCLK(R0_clk),.WE(W0_en));
'''
    pieces.append(ram+'endmodule\n')
    return ''.join(pieces)


def main():
    source=fixture();result=audit(source)
    assert result['status']=='PASS' and result['di_pins_checked']==64 and result['source_pairs']==16
    assert audit(source.replace('PangoFallbackTargetPad targetHoldPad ',
        'PangoFallbackTargetPad targetForWrite_targetHoldPad '))['di_pins_checked']==64
    bad={
        'identity_init':source.replace("64'hCCCCCCCCAAAAAAAA","64'hCCCCCCCCAAAAAAAB",1),
        'preservation':source.replace('(* PAP_DONT_TOUCH *)','',1),
        'source_swap':source.replace('.I0(dataIn[0])','.I0(dataIn[1])',1),
        'fixed_pin':source.replace(".I5(1'b1)",".I5(1'b0)",1),
        'output_swap':source.replace('.Z5(dataOut[0])','.Z5(dataOut[1])',1),
        'source_tied':source.replace('.dataIn(io_updTarget)',".dataIn(32'b0)",1),
        'ram_bypass':source.replace('padded[0]}','io_updTarget[0]}',1),
        'ram_bit_swap':source.replace('.DI(W0_data[25])','.DI(W0_data[26])',1),
        'capacity':source.replace('input [5:0] R1_addr','input [4:0] R1_addr',1),
        'ram_clock':source.replace('.R0_clk(clock)','.R0_clk(wrongClock)',1),
        'primitive_clock':source.replace('.WCLK(R0_clk)','.WCLK(wrongClock)',1),
        'actual_hierarchy':source.replace('FallbackBtb fallback ();','FallbackBtb decoy ();',1),
        'unknown_pad_instance':source.replace('PangoFallbackTargetPad targetHoldPad ',
            'PangoFallbackTargetPad unrelatedPad ',1),
        'extra_driver':source.replace('wire [31:0] padded;',
            "wire [31:0] padded;\n GTP_LUT1 evil (.Z(padded[0]),.I0(1'b0));",1),
        'output_alias':source.replace('wire [31:0] padded;',
            "wire [31:0] padded;\n assign padded[0]=1'b0;",1),
    }
    first=re.search(r'(?ms)^ \(\* PAP_DONT_TOUCH \*\) GTP_LUT6D.*?\);\n',source)[0]
    bad['missing_pair']=source.replace(first,'',1)
    bad['duplicate_pair']=source.replace(first,first+first,1)
    child=re.search(r'(?ms)^ entryMem_64x64 entryMem_1_ext.*?\);\n',source)[0]
    bad['missing_way']=source.replace(child,'',1)
    for name,text in bad.items():
        assert text!=source,name
        try:audit(text)
        except (ValueError,AssertionError):pass
        else:raise AssertionError('Accepted fallback target fault: '+name)
    with tempfile.TemporaryDirectory(prefix='fallback-pad-binding-') as directory:
        root=Path(directory).resolve()
        (root/'pds').mkdir();(root/'rtl/cpu').mkdir(parents=True)
        rtl=root/'rtl/cpu/CoreTop.sv';vm=root/'pds/native.vm';snapshot=root/'pds/build_snapshot.json'
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        def make_snapshot():
            value={'run_id':'1'*32,'inputs':{'rtl/cpu/CoreTop.sv':digest(rtl),
                'scripts/audit_fallback_target_pad_ads.py':digest(Path(__file__).with_name('audit_fallback_target_pad_ads.py')),
                'scripts/audit_icache_pad_ads.py':digest(Path(__file__).with_name('audit_icache_pad_ads.py'))}}
            snapshot.write_text(json.dumps(value),encoding='utf-8')
            return value
        rtl.write_text('module CoreTop; endmodule\n',encoding='utf-8')
        vm.write_text('SYNTHETIC LEGACY ONLY\n',encoding='utf-8');make_snapshot()
        assert bind_result(vm,snapshot)['required'] is False
        rtl.write_text('module CoreTop; endmodule\nmodule PangoFallbackTargetPad; endmodule\n',encoding='utf-8')
        vm.write_text(source,encoding='utf-8');value=make_snapshot()
        assert bind_result(vm,snapshot)['required'] is True
        rtl.write_text('changed CPU source\n',encoding='utf-8')
        try:bind_result(vm,snapshot)
        except ValueError:pass
        else:raise AssertionError('Accepted wrong CPU RTL source binding')
        rtl.write_text('module CoreTop; endmodule\nmodule PangoFallbackTargetPad; endmodule\n',encoding='utf-8')
        value=make_snapshot();value['inputs']['scripts/audit_fallback_target_pad_ads.py']='0'*64
        snapshot.write_text(json.dumps(value),encoding='utf-8')
        try:bind_result(vm,snapshot)
        except ValueError:pass
        else:raise AssertionError('Accepted wrong frozen checker binding')
        rtl.write_text('module CoreTop; endmodule\n',encoding='utf-8');make_snapshot()
        try:bind_result(vm,snapshot)
        except ValueError:pass
        else:raise AssertionError('Accepted undeclared native pad in legacy source')
    print('FALLBACK_TARGET_PAD_ADS_MUTATIONS_PASS faults='+str(len(bad))+' source_binding_cases=5 synthetic_only=true hardware_operations=0')


if __name__=='__main__':main()
