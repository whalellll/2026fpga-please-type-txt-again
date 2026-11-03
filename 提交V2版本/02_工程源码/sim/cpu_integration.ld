OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x1c000000, LENGTH = 128K }
SECTIONS {
    .text : { __cpu_code_start = .; KEEP(*(.text.start)) *(.text*) __cpu_code_end = .; *(.rodata*) } > RAM
    .data : { *(.sdata*) *(.data*) } > RAM
    .bss (NOLOAD) : { *(.sbss*) *(.bss*) *(COMMON) } > RAM
    __stack_top = ORIGIN(RAM) + LENGTH(RAM) - 16;
}
