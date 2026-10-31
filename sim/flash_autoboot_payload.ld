OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
    . = 0x00100000;
    .text : { __cpu_code_start = .; *(.text*) __cpu_code_end = .; }
    /DISCARD/ : { *(.comment) }
}
