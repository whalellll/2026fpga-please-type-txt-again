"""Whole-core machine traps/interrupts and uncached GPIO regression."""
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
    csrw mtvec,t0
    li s0,0
    li s1,0
    li s2,0
    li t1,11
    ecall
    li t1,3
    ebreak
    li t1,2
    .word 0xffffffff
    csrr t0,satp
    .word 0x10200073
    li t1,4
    li t0,0x1c010001
    lw t2,0(t0)
    li t1,6
    sw t2,0(t0)
    li t0,7
    bne s0,t0,fail
    li t3,0x1fe00000
    lw t0,0(t3)
    li t2,0x12345678
    bne t0,t2,fail
    li t0,0x89abcdef
    sw t0,4(t3)
    lw t2,4(t3)
    bne t0,t2,fail
    li t0,0x12
    sb t0,5(t3)
    lw t2,4(t3)
    li t0,0x89ab12ef
    bne t0,t2,fail
    li t0,-1
    sw t0,8(t3)
    lw t2,8(t3)
    bne t0,t2,fail
    sw zero,4(t3)
    li t0,0x80
    csrw mie,t0
    csrsi mstatus,8
    li t1,0x80000007
    li t0,1
    sw t0,4(t3)
wait_irq:
    beqz s1,wait_irq
    li t0,1
    bne s1,t0,fail
    csrr t0,misa
    li t2,0x40001101
    bne t0,t2,fail
    beqz s2,pass
    j fail
.balign 4
trap:
    csrr t4,mcause
    bne t4,t1,trap_fail
    bltz t4,irq_trap
    csrr t4,mepc
    addi t4,t4,4
    csrw mepc,t4
    addi s0,s0,1
    mret
irq_trap:
    li t4,0x1fe00004
    sw zero,0(t4)
    fence
    addi s1,s1,1
    mret
trap_fail:
    li s2,1
    j fail
'''
for label, marker in [('pass','CPU_TEST_PASS!'),('fail','CPU_TEST_FAIL!')]:
    assembly+=f'\n{label}:\nli x29,0x1fe001e0\n'
    for char in marker: assembly+=f'li x30,{ord(char)}\nsb x30,0(x29)\n'
    assembly+=f'{label}_halt:\nj {label}_halt\n'
(out/'test.S').write_text(assembly)
tb=(out/'tb_cpu_architecture.v').read_text().replace(".interrupts(8'b0)",".interrupts(dut.gpio_out == 32'd1 ? 8'h80 : 8'h00)")
tb=tb.replace('$fatal(1,"Unexpected architectural trap in CoreMark pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);',
    '$display("MACHINE_TRAP pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);')
(out/'tb_cpu_architecture.v').write_text(tb)
(out/'oracle.json').write_text(json.dumps({'traps':7,'timer_interrupts':1,
    'checks':'ECALL EBREAK illegal S CSR/SRET, misaligned load/store, GPIO byte strobes/input/enable, MRET, misa'},indent=2))
