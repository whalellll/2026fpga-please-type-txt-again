    .section .text.start
    .globl _start
_start:
    la sp, __stack_top
    la t0, trap_handler
    csrw mtvec, t0
    li s3, 0
    li s4, 0
    li s5, 0
    li s6, 0
    # RV32 I/M/A advertised by the actual generated CPU; C is disabled.
    csrr t0, misa
    # V3.5 advertises RV32IMA plus S/U; retain its Sv32 profile in this test.
    li t1, 0x40141101
    bne t0, t1, fail
    li t0, 12345
    li t1, 37
    mul t2, t0, t1
    div t2, t2, t1
    bne t2, t0, fail
    li t0, 1
    li t1, 0x1fe003f8
    sw t0, 0(t1)
    # A pair of 16-bit C.NOP encodings must trap, never execute as RVC.
    li s5, 1
    .balign 4
__cpu_illegal_start:
    .word 0x00010001
__cpu_illegal_end:
    li t0, 1
    bne s6, t0, fail
    # IALIGN=32: JALR may clear bit zero, but must trap on target bit one.
    li s5, 2
    la t0, misaligned_target
    addi t0, t0, 2
    jalr zero, 0(t0)
    li t0, 3
    bne s6, t0, fail
    li s5, 0

    # CLINT stays on the fixed SYS timebase behind the CPU/SYS bridge.
    li s0, 0x02000000
    li s1, 0x0200bff8
    lw t0, 0(s1)
    li t1, 30
1:  addi t1, t1, -1
    bnez t1, 1b
    lw t2, 0(s1)
    bleu t2, t0, fail
    li t0, 1
    sw t0, 4(s1)
    lw t1, 4(s1)
    bne t0, t1, fail
    # MSIP software interrupt and return to interrupted code.
    li t0, 8
    csrw mie, t0
    csrs mstatus, t0
    li t0, 1
    sw t0, 0(s0)
2:  beqz s3, 2b
    lw t0, 0(s0)
    bnez t0, fail
    # MTIMECMP timer interrupt; handler masks it by writing all ones.
    li s2, 0x02004000
    li t0, -1
    sw t0, 4(s2)
    lw t0, 0(s1)
    addi t0, t0, 1000
    sw t0, 0(s2)
    li t0, 1
    sw t0, 4(s2)
    li t0, 128
    csrw mie, t0
3:  beqz s4, 3b
    csrw mie, zero
    li t0, 2
    li t1, 0x1fe003f8
    sw t0, 0(t1)

    # Real cache line AXI traffic, AMO/LR-SC, and uncached DDR alias.
    li s0, 0x00100000
    li t0, 0x12345678
    sw t0, 0(s0)
    li t1, 5
    amoadd.w t2, t1, (s0)
    bne t2, t0, fail
    add t0, t0, t1
    lr.w t2, (s0)
    bne t2, t0, fail
    addi t0, t0, 1
    sc.w t2, t0, (s0)
    bnez t2, fail
    fence.i
    li s1, 0x80100000
    lw t1, 0(s1)
    bne t1, t0, fail
    li t0, 0xa5
    sb t0, 1(s1)
    li t0, 0xbeef
    sh t0, 2(s1)
    lw t1, 0(s1)
    li t0, 0xbeefa57e
    bne t0, t1, fail
    fence.i
    lw t1, 0(s0)
    bne t0, t1, fail

    # These are DDR in the production SoC, not the old PLIC/UART apertures.
    # Write code through the data cache, flush it, and execute at both windows.
    li s0, 0x0c000100
    li t0, 0x00500513              # addi a0, zero, 5
    sw t0, 0(s0)
    li t0, 0x00008067              # jalr zero, 0(ra)
    sw t0, 4(s0)
    fence.i
    jalr ra, 0(s0)
    li t0, 5
    bne a0, t0, fail
    li s0, 0x10000200
    li t0, 0x00b00513              # addi a0, zero, 11
    sw t0, 0(s0)
    li t0, 0x00008067
    sw t0, 4(s0)
    fence.i
    jalr ra, 0(s0)
    li t0, 11
    bne a0, t0, fail

    # UART TX, real serialized UART RX, and console byte echo.
    li t0, 3
    li t1, 0x1fe003f8
    sw t0, 0(t1)
    li s0, 0x1fe001e0
    li t0, 'V'
    sw t0, 0(s0)
    li t0, '3'
    sb t0, 0(s0)
4:  lw t0, 4(s0)
    andi t0, t0, 256
    beqz t0, 4b
    lw t0, 0(s0)
    li t1, 'Z'
    bne t0, t1, fail
    sw t0, 0(s0)
    li t0, 0x600dbeef
    li t1, 0x1fe003fc
    sw t0, 0(t1)
5:  j 5b

trap_handler:
    csrr t4, mcause
    li t5, 2
    beq t4, t5, illegal_instruction
    beqz t4, instruction_misaligned
    li t5, 0x80000003
    beq t4, t5, software_irq
    li t5, 0x80000007
    beq t4, t5, timer_irq
    j fail
illegal_instruction:
    li t5, 1
    bne s5, t5, fail
    ori s6, s6, 1
    csrr t4, mepc
    addi t4, t4, 4
    csrw mepc, t4
    mret
instruction_misaligned:
    li t5, 2
    bne s5, t5, fail
    csrr t4, mtval
    andi t4, t4, 3
    bne t4, t5, fail
    ori s6, s6, 2
    csrr t4, mepc
    addi t4, t4, 4
    csrw mepc, t4
    mret
software_irq:
    li t4, 0x02000000
    sw zero, 0(t4)
    addi s3, s3, 1
    mret
timer_irq:
    li t4, 0x02004004
    li t5, -1
    sw t5, 0(t4)
    addi s4, s4, 1
    mret
fail:
    csrr t3, mcause
    li t1, 0x1fe003f4
    sw t3, 0(t1)
    li t0, 0xbad0beef
    li t1, 0x1fe003fc
    sw t0, 0(t1)
6:  j 6b
    .balign 4
misaligned_target:
    j fail
