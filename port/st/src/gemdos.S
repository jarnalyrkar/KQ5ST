| GEMDOS / BIOS / XBIOS wrappers with the GCC calling convention (args 32-bit on the stack).
| TOS traps clobber d0-d2/a0-a2; d2/a2 are callee-saved for GCC, so every wrapper saves them.
| After "movem d2/a2" (8 bytes) + return address, argument N is at 12+4*N(sp).

	.text
	.macro	ENTER
	movem.l	%d2/%a2,-(%sp)
	.endm
	.macro	LEAVE				| GCC's m68k ABI returns pointers in a0
	move.l	%d0,%a0
	movem.l	(%sp)+,%d2/%a2
	rts
	.endm
#define ARG(n, k) (12+4*(n)+(k))(%sp)

	.globl	Fopen
Fopen:	ENTER				| (name, mode)
	move.w	ARG(1, 0+2),-(%sp)
	move.l	ARG(0, 0+2),-(%sp)
	move.w	#0x3d,-(%sp)
	trap	#1
	addq.l	#8,%sp
	LEAVE

	.globl	Fcreate
Fcreate: ENTER				| (name, attr)
	move.w	ARG(1, 0+2),-(%sp)
	move.l	ARG(0, 0+2),-(%sp)
	move.w	#0x3c,-(%sp)
	trap	#1
	addq.l	#8,%sp
	LEAVE

	.globl	Fclose
Fclose:	ENTER				| (h)
	move.w	ARG(0, 0+2),-(%sp)
	move.w	#0x3e,-(%sp)
	trap	#1
	addq.l	#4,%sp
	LEAVE

	.globl	Fread
Fread:	ENTER				| (h, n, buf)
	move.l	ARG(2, 0),-(%sp)
	move.l	ARG(1, 0+4),-(%sp)
	move.w	ARG(0, 0+2+8),-(%sp)
	move.w	#0x3f,-(%sp)
	trap	#1
	lea	12(%sp),%sp
	LEAVE

	.globl	Fwrite
Fwrite:	ENTER				| (h, n, buf)
	move.l	ARG(2, 0),-(%sp)
	move.l	ARG(1, 0+4),-(%sp)
	move.w	ARG(0, 0+2+8),-(%sp)
	move.w	#0x40,-(%sp)
	trap	#1
	lea	12(%sp),%sp
	LEAVE

	.globl	Fseek
Fseek:	ENTER				| (off, h, mode)
	move.w	ARG(2, 0+2),-(%sp)
	move.w	ARG(1, 0+2+2),-(%sp)
	move.l	ARG(0, 0+4),-(%sp)
	move.w	#0x42,-(%sp)
	trap	#1
	lea	10(%sp),%sp
	LEAVE

	.globl	Fdelete
Fdelete: ENTER				| (name)
	move.l	ARG(0, 0),-(%sp)
	move.w	#0x41,-(%sp)
	trap	#1
	addq.l	#6,%sp
	LEAVE

	.globl	Fsetdta
Fsetdta: ENTER				| (dta)
	move.l	ARG(0, 0),-(%sp)
	move.w	#0x1a,-(%sp)
	trap	#1
	addq.l	#6,%sp
	LEAVE

	.globl	Fsfirst
Fsfirst: ENTER				| (spec, attr)
	move.w	ARG(1, 0+2),-(%sp)
	move.l	ARG(0, 0+2),-(%sp)
	move.w	#0x4e,-(%sp)
	trap	#1
	addq.l	#8,%sp
	LEAVE

	.globl	Fsnext
Fsnext:	ENTER
	move.w	#0x4f,-(%sp)
	trap	#1
	addq.l	#2,%sp
	LEAVE

	.globl	Dgetdrv
Dgetdrv: ENTER
	move.w	#0x19,-(%sp)
	trap	#1
	addq.l	#2,%sp
	ext.l	%d0
	LEAVE

	.globl	Dgetpath
Dgetpath: ENTER				| (buf, drive)
	move.w	ARG(1, 0+2),-(%sp)
	move.l	ARG(0, 0+2),-(%sp)
	move.w	#0x47,-(%sp)
	trap	#1
	addq.l	#8,%sp
	LEAVE

	.globl	Dfree
Dfree:	ENTER				| (info, drive)
	move.w	ARG(1, 0+2),-(%sp)
	move.l	ARG(0, 0+2),-(%sp)
	move.w	#0x36,-(%sp)
	trap	#1
	addq.l	#8,%sp
	LEAVE

	.globl	Malloc
Malloc:	ENTER				| (n)
	move.l	ARG(0, 0),-(%sp)
	move.w	#0x48,-(%sp)
	trap	#1
	addq.l	#6,%sp
	LEAVE

	.globl	Mfree
Mfree:	ENTER				| (p)
	move.l	ARG(0, 0),-(%sp)
	move.w	#0x49,-(%sp)
	trap	#1
	addq.l	#6,%sp
	LEAVE

	.globl	Cconws
Cconws:	ENTER				| (s)
	move.l	ARG(0, 0),-(%sp)
	move.w	#0x09,-(%sp)
	trap	#1
	addq.l	#6,%sp
	LEAVE

	.globl	Setexc
Setexc:	ENTER				| (vec, handler) BIOS 5
	move.l	ARG(1, 0),-(%sp)
	move.w	ARG(0, 0+2+4),-(%sp)
	move.w	#5,-(%sp)
	trap	#13
	addq.l	#8,%sp
	LEAVE

	.globl	Supexec
Supexec: ENTER				| (func) XBIOS 38
	move.l	ARG(0, 0),-(%sp)
	move.w	#38,-(%sp)
	trap	#14
	addq.l	#6,%sp
	LEAVE

	.globl	Vsync
Vsync:	ENTER				| XBIOS 37
	move.w	#37,-(%sp)
	trap	#14
	addq.l	#2,%sp
	LEAVE

	.globl	Physbase
Physbase: ENTER				| XBIOS 2
	move.w	#2,-(%sp)
	trap	#14
	addq.l	#2,%sp
	LEAVE

	.globl	Logbase
Logbase: ENTER				| XBIOS 3
	move.w	#3,-(%sp)
	trap	#14
	addq.l	#2,%sp
	LEAVE

	.globl	Getrez
Getrez:	ENTER				| XBIOS 4
	move.w	#4,-(%sp)
	trap	#14
	addq.l	#2,%sp
	ext.l	%d0
	LEAVE

	.globl	Setscreen
Setscreen: ENTER			| (log, phys, res) XBIOS 5
	move.w	ARG(2, 0+2),-(%sp)
	move.l	ARG(1, 0+2),-(%sp)
	move.l	ARG(0, 0+6),-(%sp)
	move.w	#5,-(%sp)
	trap	#14
	lea	12(%sp),%sp
	LEAVE

	.globl	Setpalette
Setpalette: ENTER			| (pal) XBIOS 6
	move.l	ARG(0, 0),-(%sp)
	move.w	#6,-(%sp)
	trap	#14
	addq.l	#6,%sp
	LEAVE

	.globl	Bconstat
Bconstat: ENTER				| (dev) BIOS 1
	move.w	ARG(0, 0+2),-(%sp)
	move.w	#1,-(%sp)
	trap	#13
	addq.l	#4,%sp
	LEAVE

	.globl	Bconin
Bconin:	ENTER				| (dev) BIOS 2
	move.w	ARG(0, 0+2),-(%sp)
	move.w	#2,-(%sp)
	trap	#13
	addq.l	#4,%sp
	LEAVE

	.globl	Kbshift
Kbshift: ENTER				| (mode) BIOS 11
	move.w	ARG(0, 0+2),-(%sp)
	move.w	#11,-(%sp)
	trap	#13
	addq.l	#4,%sp
	ext.l	%d0
	LEAVE

	.globl	Keytbl
Keytbl:	ENTER				| (unshift, shift, caps) XBIOS 16
	move.l	ARG(2, 0),-(%sp)
	move.l	ARG(1, 0+4),-(%sp)
	move.l	ARG(0, 0+8),-(%sp)
	move.w	#16,-(%sp)
	trap	#14
	lea	14(%sp),%sp
	LEAVE

	.globl	Kbdvbase
Kbdvbase: ENTER				| XBIOS 34
	move.w	#34,-(%sp)
	trap	#14
	addq.l	#2,%sp
	LEAVE

	.globl	Xbtimer
Xbtimer: ENTER				| (timer, control, data, vec) XBIOS 31
	move.l	ARG(3, 0),-(%sp)
	move.w	ARG(2, 0+2+4),-(%sp)
	move.w	ARG(1, 0+2+6),-(%sp)
	move.w	ARG(0, 0+2+8),-(%sp)
	move.w	#31,-(%sp)
	trap	#14
	lea	12(%sp),%sp
	LEAVE

	.globl	Blitmode
Blitmode: ENTER				| (mode) XBIOS 64
	move.w	ARG(0, 0+2),-(%sp)
	move.w	#64,-(%sp)
	trap	#14
	addq.l	#4,%sp
	ext.l	%d0
	LEAVE
