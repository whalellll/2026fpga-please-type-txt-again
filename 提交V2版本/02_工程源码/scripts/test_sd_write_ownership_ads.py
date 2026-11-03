"""Independent CNF truth tables and synthetic SD ownership faults; no PDS/board."""
import json
import argparse
import hashlib
from pathlib import Path
import random
import re
import pycosat
from audit_sd_write_ownership_ads import audit,BooleanCNF,Symbolic
from audit_rob_owner_ads import Hierarchy


def cpu_table(bank,full_guard=True):
    return sum(int(bool((k&1) and (k&2) and (not(k&4) or (k&8)) and
                        (not full_guard or not(k&16)) and bool(k&32)==bool(bank)))<<k for k in range(64))


def fixture():
    scalars=['wr','normal_path','busy','write_multi_active','tx0_full','tx1_full','cpu_bank','rx_bank','rx_valid','clk']
    header='\n'.join('input '+n+',' for n in scalars)+'\ninput [3:0] l_wstrb\n);\n'
    lines=['module soc_top (',header,'sd_native_mmio u_sd ('+
           ','.join('.'+n+'('+n+')' for n in scalars+['l_wstrb'])+');\nendmodule',
           'module sd_native_mmio (',header]
    for bank in range(2):
        params=f"64'h{cpu_table(bank):016x}"
        signals=['wr','normal_path','busy','write_multi_active',f'tx{bank}_full','cpu_bank']
        lines.append(f'GTP_LUT6 #(.INIT({params})) cpu{bank}_g (.Z(cpu{bank}),'+
                     ','.join(f'.I{i}({n})' for i,n in enumerate(signals))+');')
        lines.append(f"GTP_LUT2 #(.INIT(4'h{'8' if bank else '2'})) rx{bank}_g "
                     f'(.Z(rx_write{bank}),.I0(rx_valid),.I1(rx_bank));')
        lines.append(f'sd_native_sector_bank u_buffer{bank} (.cpu_owner(cpu{bank}),.rx_owner(rx_write{bank}),'
                     '.l_wstrb(l_wstrb),.clk(clk));')
    lines+=['endmodule','module sd_native_sector_bank (\ninput cpu_owner,\ninput rx_owner,\ninput clk,\ninput [3:0] l_wstrb\n);']
    for b in range(4):
        lines.append(f"GTP_LUT3 #(.INIT(8'hec)) we{b}_g (.Z(we{b}),.I0(cpu_owner),.I1(rx_owner),.I2(l_wstrb[{b}]));")
    for view in ['cpu','tx']:
        for bit in range(32):
            lines.append(f'GTP_RAM128X1DP {view}_mem{bit} (.DI(write_data[{bit}]),.DO({view}_data[{bit}]),'
                         f'.WE(we{bit//8}),.WCLK(clk),.WADDR(write_addr),.RADDR({view}_read_addr));')
    lines+=['endmodule'];return '\n'.join(lines)+'\n'


def truth_tables():
    rng=random.Random(0x5dca);cases=0
    # The CNF compiler is compared to direct table indexing, with both output
    # polarities checked for every assignment; no SAT proof may be vacuous.
    for width in range(1,7):
        for init in [0,(1<<(1<<width))-1,rng.getrandbits(1<<width),rng.getrandbits(1<<width)]:
            variables=[((),f'x{i}') for i in range(width)]
            text='module soc_top (\n'+''.join(f'input x{i},\n' for i in range(width))+'output y\n);\n'
            text+=f"GTP_LUT{width} #(.INIT({1<<width}'h{init:x})) g (.Z(y),"+','.join(f'.I{i}(x{i})' for i in range(width))+');\nendmodule\n'
            symbolic=Symbolic(Hierarchy(text));cnf=BooleanCNF(variables);walk=symbolic.evaluator(cnf);output=walk(((),'y'))
            for value in range(1<<width):
                assumptions=[[cnf.var(k) if (value>>i)&1 else -cnf.var(k)] for i,k in enumerate(variables)]
                for want in [0,1]:
                    literal=output if want else cnf.inv(output)
                    actual=False if literal==0 else pycosat.solve(cnf.clauses+assumptions+([] if literal==1 else [[literal]]))!='UNSAT'
                    assert actual==(want==((init>>value)&1)),(width,init,value,want)
                    cases+=1
            BooleanCNF.ite.cache_clear();Symbolic.step.cache_clear();Symbolic.memory_outputs.cache_clear()
    return cases


def reconstructed_fixture():
    source=re.sub(r'\bwr\b','write_accept',fixture())
    source=source.replace('input write_accept,\n','',1)
    source=source.replace('input [3:0] l_wstrb\n);',
        'input raw_valid,\ninput raw_xbusy,\ninput raw_ddr,\ninput raw_active,\ninput raw_good,\n'
        'input [31:0] raw_addr,\ninput [3:0] l_wstrb\n);',1)
    cells="""core_top u_cpu (.raw(raw_valid),.wvalid(cpu_valid));
axi_1x2 u_xbar (.raw_busy(raw_xbusy),.raw_ddr(raw_ddr),.wr_busy(xbusy),.wr_ddr(ddr));
axi_boot_periph u_local (.raw_active(raw_active),.raw_good(raw_good),.wr_addr(raw_addr),
 .wr_active(active),.wr_good(good),.wr_is_mmio(mmio));
GTP_LUT6 #(.INIT(64'h0800000000000000)) accepted (.Z(write_accept),
 .I0(cpu_valid),.I1(xbusy),.I2(ddr),.I3(active),.I4(mmio),.I5(good));
"""
    source=source.replace('sd_native_mmio u_sd (',cells+'sd_native_mmio u_sd (',1)
    source += """module core_top (
input raw,
output wvalid
);
assign wvalid=raw;
endmodule
module axi_1x2 (
input raw_busy,
input raw_ddr,
output wr_busy,
output wr_ddr
);
assign wr_busy=raw_busy;
assign wr_ddr=raw_ddr;
endmodule
module axi_boot_periph (
input raw_active,
input raw_good,
input [31:0] wr_addr,
output wr_active,
output wr_good,
output wr_is_mmio
);
assign wr_active=raw_active;
assign wr_good=raw_good;
assign wr_is_mmio=wr_addr[9];
endmodule
"""
    return source


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path);args=ap.parse_args()
    cases=truth_tables();source=fixture();positive=audit(source)
    assert positive['bank_cpu_ownership_exclusive'] and positive['bank_rx_ownership_exclusive']
    faults={
        'constant_we':('.WE(we0)',".WE(1'b1)"),
        'missing_ram':('GTP_RAM128X1DP cpu_mem0','GTP_RAM_LOST cpu_mem0'),
        'wrong_data_bit':('.DI(write_data[0])','.DI(write_data[1])'),
        'strobe_bypass':("8'hec","8'hee"),
        'cpu_path_lost':("8'hec","8'hcc"),
        'rx_path_lost':("8'hec","8'ha0"),
        'tx_full_bypass':(f"64'h{cpu_table(0):016x}",f"64'h{cpu_table(0,False):016x}"),
        'cpu_bank_overlap':(f"64'h{cpu_table(1):016x}",f"64'h{cpu_table(0):016x}"),
        'rx_bank_overlap':("4'h8)) rx1_g","4'h2)) rx1_g"),
        'wrong_byte':('.I2(l_wstrb[1])','.I2(l_wstrb[0])'),
        'disconnected_owner':('.cpu_owner(cpu1)','.cpu_owner(missing)'),
    }
    rejected={}
    for name,(before,after) in faults.items():
        assert before in source,name
        try:audit(source.replace(before,after,1))
        except (ValueError,AssertionError,KeyError) as e:rejected[name]=str(e)
        else:raise AssertionError('Accepted SD fault '+name)
        finally:
            BooleanCNF.ite.cache_clear();Symbolic.step.cache_clear();Symbolic.memory_outputs.cache_clear()
    rebuilt=reconstructed_fixture();reconstructed=audit(rebuilt)
    assert reconstructed['write_event_binding']=='reconstructed_axi_mmio_contract'
    reference_faults={}
    for pin,name in enumerate(['valid','xbar_busy','ddr_owner','local_active','mmio','write_good']):
        # Add acceptance for the assignment obtained by flipping one guard.
        damaged=(1<<59)|(1<<(59^(1<<pin)))
        mutant=rebuilt.replace("64'h0800000000000000",f"64'h{damaged:016x}")
        try:audit(mutant)
        except (ValueError,AssertionError,KeyError) as e:reference_faults[name]=str(e)
        else:raise AssertionError('Accepted reconstructed write guard bypass '+name)
        finally:
            BooleanCNF.ite.cache_clear();Symbolic.step.cache_clear();Symbolic.memory_outputs.cache_clear()
    try:audit(rebuilt.replace('assign wr_is_mmio=wr_addr[9];',"assign wr_is_mmio=1'b1;"))
    except ValueError as e:
        assert 'overlaps UART' in str(e);reference_faults['uart_overlap']=str(e)
    else:raise AssertionError('Accepted MMIO/UART overlap')
    record=dict(status='SD_WRITE_OWNERSHIP_MUTATIONS_PASS',truth_table_output_cases=cases,
                reconstructed_write_reference_faults=reference_faults,
                reconstructed_write_reference_positive='PASS',
                synthetic_faults=rejected,scope='Software checker tests only, not native hardware acceptance',
                source_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                               for n in ['test_sd_write_ownership_ads.py','audit_sd_write_ownership_ads.py']})
    if args.output:
        assert not args.output.exists();args.output.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))


if __name__=='__main__':main()
