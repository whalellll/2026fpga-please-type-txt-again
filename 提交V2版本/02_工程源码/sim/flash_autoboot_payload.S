    .section .text
    .globl _start
_start:
    li t0, 0x1fe003f0
    li t1, 0xf1a5b007
    or t2, a0, a1
    beqz t2, 1f
    li t1, 0xbad00001
1:  sw t1, 0(t0)
2:  j 2b
