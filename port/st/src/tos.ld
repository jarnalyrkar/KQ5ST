/* Single image for a TOS PRG: .text then .data contiguous, .bss after. */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS {
    .text : { __text_start = .; *(.text .text.*) *(.rodata .rodata.*) . = ALIGN(4); }
    .data : { __data_start = .; *(.data .data.*) . = ALIGN(4); __data_end = .; }
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.*) *(COMMON) . = ALIGN(4); __bss_end = .; }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
