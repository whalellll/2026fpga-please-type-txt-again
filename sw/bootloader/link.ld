OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { BRAM (rwx) : ORIGIN = 0x1c000000, LENGTH = 128K }
SECTIONS {
 .text : { __cpu_code_start = .; KEEP(*(.text.start)) *(.text*) __cpu_code_end = .; *(.rodata*) } > BRAM
 .data : { *(.sdata*) *(.data*) } > BRAM
 .bss (NOLOAD) : { . = ALIGN(4); __bss_start = .; *(.sbss*) *(.bss*) *(COMMON); . = ALIGN(4); __bss_end = .; } > BRAM
 __global_pointer$ = MIN(__bss_start + 0x800, ORIGIN(BRAM) + LENGTH(BRAM) - 4);
 __stack_top = ORIGIN(BRAM) + LENGTH(BRAM) - 16;
 ASSERT(__bss_end < __stack_top - 16384, "bootloader leaves less than 16 KiB stack")
}

