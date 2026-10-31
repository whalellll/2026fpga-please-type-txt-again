    .section .text.start
    .globl _start
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
    .word 0x0000100f
    jr t0
