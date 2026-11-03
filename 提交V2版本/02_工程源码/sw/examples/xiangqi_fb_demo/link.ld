OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    DDR (rwx) : ORIGIN = 0x01000000, LENGTH = 64K
}

SECTIONS
{
    . = ORIGIN(DDR);
    .text : ALIGN(4) { __cpu_code_start = .; KEEP(*(.text.start)) *(.text .text.*) __cpu_code_end = .; } > DDR
    .rodata : ALIGN(16) { *(.rodata .rodata.*) *(.srodata .srodata.*) } > DDR
    .data : ALIGN(4)
    {
        __data_start = .;
        *(.data .data.*) *(.sdata .sdata.*)
        __data_end = .;
    } > DDR
    PROVIDE(__global_pointer$ = __data_start + 0x800);
    .bss (NOLOAD) : ALIGN(4)
    {
        __bss_start = .;
        *(.sbss .sbss.*) *(.bss .bss.*) *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > DDR
    __image_end = .;
    __stack_top = ORIGIN(DDR) + LENGTH(DDR);
    ASSERT(__image_end < __stack_top - 4096, "Framebuffer demo overlaps stack")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
