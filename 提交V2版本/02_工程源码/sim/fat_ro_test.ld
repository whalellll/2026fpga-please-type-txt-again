OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY { RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 128K }

SECTIONS
{
    .text : {
        __cpu_code_start = .; KEEP(*(.text.start))
        *(.text*) __cpu_code_end = .;
        *(.rodata*)
    } > RAM
    .data : { *(.sdata*) *(.data*) } > RAM
    .bss (NOLOAD) : {
        . = ALIGN(4);
        __bss_start = .;
        *(.sbss*) *(.bss*) *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > RAM

    __global_pointer$ = MIN(__bss_start + 0x800, ORIGIN(RAM) + LENGTH(RAM) - 4);
    __stack_top = ORIGIN(RAM) + LENGTH(RAM) - 16;
    ASSERT(__bss_end < __stack_top - 4096, "FAT test firmware exceeds simulation RAM")
}
