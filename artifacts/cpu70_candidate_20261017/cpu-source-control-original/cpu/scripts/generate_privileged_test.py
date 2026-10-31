"""Whole-core Sv32, coherent page table, delegation and return regression."""
from pathlib import Path
import runpy
import json

root = Path(__file__).resolve().parent.parent
runpy.run_path(str(root/'scripts/generate_cpu_test.py'))
out = root/'work/cpu-test'
assembly = r'''
.section .init,"ax"
.globl _start
_start:
    la t0, machine_fail
    csrw mtvec, t0
    # Clear the root and level-zero table using normal cached stores.
    li t0, 0x1c014000
    li t1, 2048
clear_tables:
    sw zero, 0(t0)
    addi t0, t0, 4
    addi t1, t1, -1
    bnez t1, clear_tables
    li t0, 0x1c014000
    li t1, 0x070000cf
    sw t1, 0x1c0(t0) # identity executable supervisor superpage
    sw t1, 0x400(t0) # 0x40000000 alias of physical 0x1c000000
    li t1, 0x07f000c7
    sw t1, 0x1fc(t0) # identity UART superpage
    li t1, 0x07005401
    sw t1, 0x404(t0) # 0x40400000 level-zero table
    li t0, 0x1c015000
    li t1, 0x070040d7
    sw t1, 0(t0)     # user data page -> physical 0x1c010000
    li t0, 0x1c010000
    li t1, 0x719246ab
    sw t1, 0(t0)
    la t0, supervisor_trap
    csrw stvec, t0
    li t0, 0xb100
    csrw medeleg, t0
    li t0, 0x8001c014
    csrw satp, t0
    sfence.vma
    la t0, supervisor_start
    csrw mepc, t0
    li t0, 0x800
    csrw mstatus, t0
    mret
supervisor_start:
    li s0, 0
    li t0, 0x40010000
    lw t1, 0(t0)
    li t2, 0x719246ab
    bne t1, t2, fail
    # An unmapped load must report its virtual address and restart at sepc+4.
    li s1, 13
    li s2, 0x40800000
    lw t1, 0(s2)
    li t0, 1
    bne s0, t0, fail
    # SUM takes effect immediately on a user page.
    li t0, 0x40000
    csrs sstatus, t0
    li t0, 0x40400000
    lw t1, 0(t0)
    bne t1, t2, fail
    li t0, 0x40000
    csrc sstatus, t0
    li s2, 0x40400000
    lw t1, 0(s2)
    li t0, 2
    bne s0, t0, fail
    # Change cached PTE, then SFENCE must make the next walk see the store.
    li t0, 0x1c015000
    li t1, 0x070044d7
    sw t1, 0(t0)
    li t0, 0x1c011000
    li t1, 0x1234abcd
    sw t1, 0(t0)
    sfence.vma
    li t0, 0x40000
    csrs sstatus, t0
    li t0, 0x40400000
    lw t2, 0(t0)
    bne t1, t2, fail
    # Map executable U page, enter it using SRET, then delegate its ECALL.
    li t0, 0x1c015000
    la t1, user_start
    srli t1, t1, 12
    slli t1, t1, 10
    ori t1, t1, 0xdb
    sw t1, 4(t0)
    sfence.vma
    la t0, user_start
    li t1, 0xfff
    and t0, t0, t1
    li t1, 0x40401000
    or t0, t0, t1
    csrw sepc, t0
    li t0, 0x100
    csrc sstatus, t0
    li s1, 8
    li s2, 0
    sret
user_start:
    ecall
    j machine_fail
supervisor_trap:
    csrr t3, scause
    bne t3, s1, fail
    csrr t3, stval
    bne t3, s2, fail
    addi s0, s0, 1
    li t3, 8
    beq s1, t3, user_finished
    csrr t3, sepc
    addi t3, t3, 4
    csrw sepc, t3
    sret
user_finished:
    li t3, 3
    bne s0, t3, fail
    j pass
machine_fail:
    csrw satp, zero
    j fail
'''
for label, marker in [('pass','CPU_TEST_PASS!'),('fail','CPU_TEST_FAIL!')]:
    assembly += f'\n{label}:\n    li t4, 0x1fe001e0\n'
    for char in marker:
        assembly += f'    li t5, {ord(char)}\n    sb t5, 0(t4)\n'
    assembly += f'{label}_halt:\n    j {label}_halt\n'
(out/'test.S').write_text(assembly)
tb = (out/'tb_cpu_architecture.v').read_text().replace(
    '$fatal(1,"Unexpected architectural trap in CoreMark pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);',
    '$display("PRIV_TRAP pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);')
(out/'tb_cpu_architecture.v').write_text(tb)
(out/'oracle.json').write_text(json.dumps({'checks': ['MRET to S', 'Sv32 instruction/data',
    'superpage alias', 'load page fault and stval', 'SUM immediate permission',
    'cached PTE coherence after SFENCE', 'SRET to U', 'delegated U ECALL']}, indent=2))
