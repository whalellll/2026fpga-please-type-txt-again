OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { DDR (rwx) : ORIGIN = 0x01000000, LENGTH = 64K }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > DDR
 .data : { __global_pointer$ = . + 0x800; *(.data*) *(.sdata*) } > DDR
 .bss : { . = ALIGN(4); __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __bss_end = .; } > DDR
 __stack_top = ORIGIN(DDR)+LENGTH(DDR)-16;
 ASSERT(__bss_end < __stack_top-8192, "SD8 payload leaves insufficient stack")
}
