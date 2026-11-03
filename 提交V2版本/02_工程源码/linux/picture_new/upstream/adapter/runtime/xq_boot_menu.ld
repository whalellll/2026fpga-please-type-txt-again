OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { DDR (rwx) : ORIGIN = 0x01400000, LENGTH = 1M }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) *(.srodata*) . = ALIGN(4); } > DDR
 .data : { *(.sdata*) *(.data*) . = ALIGN(4); __image_end = .; } > DDR
 __image_bytes = __image_end - ORIGIN(DDR);
 .bss (NOLOAD) : { . = ALIGN(4); __bss_start = .; *(.sbss*) *(.bss*) *(COMMON); . = ALIGN(4); __bss_end = .; } > DDR
 __global_pointer$ = MIN(__bss_start + 0x800, ORIGIN(DDR) + LENGTH(DDR) - 4);
 __stack_top = ORIGIN(DDR) + LENGTH(DDR) - 16;
 ASSERT(__bss_end < __stack_top - 16384, "menu needs 16 KiB stack")
 ASSERT(__image_bytes < 19968, "menu must fit the existing 20468-byte SD entry prefix")
}
