OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { DDR (rwx) : ORIGIN = 0x01000000, LENGTH = 256K }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > DDR
 .data : { *(.data*) } > DDR
 .bss : {
    __bss_start = .;
    *(.bss*) *(COMMON)
    __bss_end = .;
 } > DDR
 __stack_top = ORIGIN(DDR) + LENGTH(DDR) - 16;
}
