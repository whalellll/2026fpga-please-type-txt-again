OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { DDR (rwx) : ORIGIN = 0x00000000, LENGTH = 1M }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > DDR
 .data : { *(.sdata*) *(.data*) } > DDR
 .bss (NOLOAD) : { . = ALIGN(4); __bss_start = .; *(.sbss*) *(.bss*) *(COMMON); . = ALIGN(4); __bss_end = .; } > DDR
 __global_pointer$ = MIN(__bss_start + 0x800, ORIGIN(DDR) + LENGTH(DDR) - 4);
 __stack_top = ORIGIN(DDR) + LENGTH(DDR) - 16;
 ASSERT(__bss_end < __stack_top - 16384, "loader leaves less than 16 KiB stack")
}
