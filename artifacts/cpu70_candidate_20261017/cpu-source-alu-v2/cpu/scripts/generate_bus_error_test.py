"""Inject late AXI SLVERR into real cache refills and check precise traps."""
from pathlib import Path
import runpy
import json
root=Path(__file__).resolve().parent.parent
runpy.run_path(str(root/'scripts/generate_cpu_test.py'))
out=root/'work/cpu-test'
assembly=r'''
.section .init,"ax"
.globl _start
_start:
    la t0, trap
    csrw mtvec, t0
    li s0, 0
    li s1, 5
    li s2, 0x1c012000
    la s3, load_return
    li s4, 0x12345678
    lw s4, 0(s2)
    j fail
load_return:
    li t0, 0x12345678
    bne s4, t0, fail
    la s3, load_return_again
    lw s4, 0(s2)
    j fail
load_return_again:
    li s1, 7
    la s3, amo_return
    amoadd.w s4, s4, (s2)
    j fail
amo_return:
    li s1, 5
    la s3, lr_return
    lr.w s4, (s2)
    j fail
lr_return:
    li s1, 1
    li s2, 0x1c018000
    la s3, fetch_return
    jalr zero, 0(s2)
    j fail
fetch_return:
    li t0, 5
    bne s0, t0, fail
    j pass
trap:
    csrr t0, mcause
    bne t0, s1, fail
    csrr t0, mtval
    bne t0, s2, fail
    addi s0, s0, 1
    csrw mepc, s3
    mret
'''
for label,marker in [('pass','CPU_TEST_PASS!'),('fail','CPU_TEST_FAIL!')]:
    assembly += f'\n{label}:\n    li t4, 0x1fe001e0\n'
    for char in marker: assembly+=f'    li t5, {ord(char)}\n    sb t5, 0(t4)\n'
    assembly+=f'{label}_halt:\n    j {label}_halt\n'
(out/'test.S').write_text(assembly)
tb=(out/'tb_cpu_architecture.v').read_text().replace(
    '$fatal(1,"Unexpected architectural trap in CoreMark pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);',
    '$display("BUS_TRAP pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);')
(out/'tb_cpu_architecture.v').write_text(tb)
soc=(root/'coremark_test_soc/rtl/coremark_soc_top.v').read_text()
soc=soc.replace('    CoreTop u_cpu (',r'''
    reg [31:0] fault_read_base;
    reg [7:0] fault_read_beat;
    always @(posedge clk) begin
      if (!sys_resetn) begin fault_read_base <= 0; fault_read_beat <= 0; end
      else begin
        if (arvalid && arready) begin fault_read_base <= araddr; fault_read_beat <= 0; end
        if (rvalid && rready) fault_read_beat <= fault_read_beat + 1;
      end
    end
    wire inject_error = (fault_read_base == 32'h1c012000 || fault_read_base == 32'h1c018000)
                        && fault_read_beat == 7;
    CoreTop u_cpu (''')
soc=soc.replace('.io_rresp              (rresp)', '.io_rresp              (inject_error ? 2\'b10 : rresp)')
(out/'bus_error_soc.v').write_text(soc)
(out/'oracle.json').write_text(json.dumps({'checks':['last-beat load SLVERR',
    'no failed refill installed','AMO store access fault','LR load access fault',
    'instruction access fault','fault virtual address','no faulting rd retirement']},indent=2))
