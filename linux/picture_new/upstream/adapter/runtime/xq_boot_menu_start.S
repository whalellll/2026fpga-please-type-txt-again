    .section .text.start
    .globl _start
_start:
    /* Absolute addresses: the ROM initially executes this image 4 MiB below
       its link address. No stack or globals may be used until relocation. */
    li t0, 0x01000000
    li t1, 0x01400000
    li t4, 0x81400000
    lui t2, %hi(__image_bytes)
    addi t2, t2, %lo(__image_bytes)
1:  beqz t2, 2f
    lw t3, 0(t0)
    sw t3, 0(t1)
    sw t3, 0(t4)
    addi t0, t0, 4
    addi t1, t1, 4
    addi t4, t4, 4
    addi t2, t2, -4
    j 1b
2:  fence iorw, iorw
    .word 0x0000100f
    lui t0, %hi(relocated_entry)
    addi t0, t0, %lo(relocated_entry)
    jr t0
relocated_entry:
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, __stack_top
    la t0, __bss_start
    la t1, __bss_end
3:  bgeu t0, t1, 4f
    sw zero, 0(t0)
    addi t0, t0, 4
    j 3b
4:  call main
5:  j 5b
    .globl jump_to
jump_to:
    mv t0, a0
    mv a0, a1
    mv a1, a2
    .word 0x0000100f
    jr t0
