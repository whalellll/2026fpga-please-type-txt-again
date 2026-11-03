/* v2_1_sd startup with explicit fence.i mnemonic for GCC16 ISA/mapping audit. */
    .section .text.start
    .globl _start
    .option norvc
_start:
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, __stack_top
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sw zero, 0(t0)
    addi t0, t0, 4
    j 1b
2:  call main
3:  j 3b
    .globl jump_to
jump_to:
    mv t0, a0
    mv a0, a1
    mv a1, a2
    fence.i
    jr t0
