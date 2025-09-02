OUTPUT_ARCH("riscv")
ENTRY(_start)

SECTIONS
{
    . = 0x4c;
    .text : 
    {
        *(.text)
        *(.text.*)
    }
    
    . = ALIGN(4);
    .rodata : 
    {
        *(.rodata)
        *(.rodata.*)
    }
    
    . = ALIGN(4);
    .data : 
    {
        *(.data)
        *(.data.*)
    }
    
    . = ALIGN(4);
    .bss : 
    {
        *(.bss)
        *(.bss.*)
    }
}
