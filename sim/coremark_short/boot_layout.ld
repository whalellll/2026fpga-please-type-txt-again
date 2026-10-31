OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { BRAM (rwx) : ORIGIN = 0x1c000000, LENGTH = 128K }
SECTIONS {
 .text : { __cpu_code_start = .; KEEP(*(.text.start)) *(.text*) __cpu_code_end = .; *(.rodata*) } > BRAM
 .data : { *(.sdata*) *(.data*) } > BRAM
 /* Match the current complete GCC14/O2 bootloader work area. This isolates
    the historical CPU PMA carve-out without modifying production firmware. */
 .bss 0x1c01b0a8 (NOLOAD) : {
   __bss_start = .;
   __coremark_work_start = .;
   KEEP(*(.bss.static_memblk))
   __coremark_work_end = .;
   *(.sbss*) *(.bss*) *(COMMON)
   . = ALIGN(4); __bss_end = .;
 } > BRAM
 __global_pointer$ = MIN(__bss_start + 0x800, ORIGIN(BRAM) + LENGTH(BRAM) - 4);
 __stack_top = ORIGIN(BRAM) + LENGTH(BRAM) - 16;
 ASSERT(__coremark_work_start == 0x1c01b0a8 && __coremark_work_end - __coremark_work_start == 2000, "CoreMark work area moved from the production comparison address")
 ASSERT(__bss_end < __stack_top - 16384, "fixture leaves less than 16 KiB stack")
}
