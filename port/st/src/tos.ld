/* Single image for a TOS PRG: .text then .data contiguous, .bss after. reloc_copy (end of .data)
 * receives a copy of the fixup table from elf2prg.py, for _start's re-alignment (glue.S). */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS {
    .text : { __text_start = .; *(.text .text.*) *(.rodata .rodata.*) . = ALIGN(4); }
    .data : { __data_start = .; *(.data .data.*) . = ALIGN(4);
        reloc_copy = .; . += RELOC_COPY_SIZE; __data_end = .; }
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.*) *(COMMON) . = ALIGN(4); __bss_end = .; }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
