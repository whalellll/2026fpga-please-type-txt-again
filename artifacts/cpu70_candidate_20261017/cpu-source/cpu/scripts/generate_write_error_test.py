"""Committed write errors stop retirement and assert the fatal fabric pin."""
from pathlib import Path
import runpy, json, os
root=Path(__file__).resolve().parent.parent
kind=os.environ.get('WRITE_ERROR_KIND','bresp')
if kind not in ('bresp', 'fill'):
    raise ValueError('WRITE_ERROR_KIND must be bresp or fill')
out=root/'work/cpu-test'
runpy.run_path(str(root/'scripts/generate_bus_error_test.py' if kind=='fill' else root/'scripts/generate_cpu_test.py'))
soc=(out/'bus_error_soc.v').read_text() if kind=='fill' else (root/'coremark_test_soc/rtl/coremark_soc_top.v').read_text()
if kind=='bresp':
    assert soc.count('.io_bresp              (bresp)') == 1
    soc=soc.replace('.io_bresp              (bresp)',".io_bresp              (2'b10)")
(out/'write_error_soc.v').write_text(soc)
address='0x1c012000' if kind=='fill' else '0x1fe001e0'
(out/'test.S').write_text(f'''.section .init,"ax"
.globl _start
_start:
li s0,{address}
li t0,88
sw t0,0(s0)
fence rw,rw
loop:
addi t1,t1,1
j loop
''')
tb=(out/'tb_cpu_architecture.v').read_text()
anchor = '    integer cycle_count = 0;'
if tb.count(anchor) != 1:
    raise RuntimeError('Expected one cycle counter declaration in the CPU testbench')
error_handshake = (
    "dut.u_cpu.io_bvalid && dut.u_cpu.io_bready && dut.u_cpu.io_bresp == 2'b10"
    if kind == 'bresp' else
    "dut.u_cpu.io_rvalid && dut.u_cpu.io_rready && dut.u_cpu.io_rresp == 2'b10 && "
    "dut.inject_error && dut.fault_read_base == 32'h1c012000"
)
tb=tb.replace(anchor, f'''    integer cycle_count = 0;
integer fatal_cycles = 0;
reg saw_injected_error = 1'b0;
reg saw_fatal = 1'b0;
wire injected_error_handshake = {error_handshake};
always @(posedge clk) begin
    if (!rst_n) begin
        saw_injected_error <= 1'b0;
        saw_fatal <= 1'b0;
        fatal_cycles <= 0;
    end else begin
        if (injected_error_handshake) saw_injected_error <= 1'b1;
        if (saw_fatal || dut.u_cpu.io_fatalMemoryError) begin
            if (!saw_injected_error && !injected_error_handshake)
                $fatal(1,"Fatal memory error preceded the injected error handshake");
            saw_fatal <= 1'b1;
            fatal_cycles <= fatal_cycles + 1;
            if (dut.u_cpu.core.backend.cmt_csr_retire_count != 0)
                $fatal(1,"Retirement continued after committed write failure");
            if (fatal_cycles == 12) begin
                $display("TB_CPU_ARCHITECTURE_PASS write bus fault stopped retirement; injected_handshake=1");
                $finish;
            end
        end
    end
end
''')
pass_anchor = 'if (marker_next == "CPU_TEST_PASS!") begin'
if tb.count(pass_anchor) != 1:
    raise RuntimeError('Expected one UART pass marker check in the CPU testbench')
tb = tb.replace(pass_anchor, pass_anchor +
    '\n                $fatal(1,"Unexpected UART pass marker in write-error regression");')
(out/'tb_cpu_architecture.v').write_text(tb)
(out/'oracle.json').write_text(json.dumps({'checks':['actual injected error handshake',
    'fatal output','no later retirement including after a fatal pulse'],'injection':kind}))
