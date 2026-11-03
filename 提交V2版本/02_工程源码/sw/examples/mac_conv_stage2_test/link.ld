OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { DDR (rwx) : ORIGIN = 0x01000000, LENGTH = 64K }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > DDR
 .data : { *(.data*) } > DDR
 .bss : { *(.bss*) *(COMMON) } > DDR
 __stack_top = ORIGIN(DDR) + LENGTH(DDR) - 16;
}
