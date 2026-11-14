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

| ---- CPU cache flush (supervisor; run through Supexec). Code the shim writes at run time (the
| library jump tables, the 68060 interpreter entry) must reach memory before it is executed: the
| 68040/68060 data cache is copyback and the instruction cache does not see it. Encoded as words
| because the file is assembled for the 68000.
	.globl	cache_flush_040
cache_flush_040:			| 68040/68060: cpusha bc (push + invalidate both caches)
	.word	0xf4f8
	moveq	#0,%d0
	rts
	.globl	cache_flush_030
cache_flush_030:			| 68020/68030: set CD + CI in CACR (clear data + instruction cache)
	move.l	%d1,-(%sp)
	.word	0x4e7a,0x1002		| movec cacr,d1
	or.w	#0x0808,%d1
	.word	0x4e7b,0x1002		| movec d1,cacr
	move.l	(%sp)+,%d1
	moveq	#0,%d0
	rts

| ---- 68060: movep emulation (vector 61, unimplemented integer instruction) ------------------
| The 68060 has no movep in hardware and Prog uses it all over (SCI reads little-endian words with
| "movep.w 1(an),dn; move.b (an),dn": send, resource loader, graphics). Normally the 060 support
| package in TOS/MiNT emulates it; this handler does it without one. Other unimplemented integer
| instructions (64-bit mul/div, cas2, chk2, cmp2), and movep through a7, go to the previous
| handler. Installed by shim.c only when _CPU = 60. Frame (format 0): sr.w, pc.l (= the movep).
| movep: 0000 ddd1 oo00 1aaa disp16, oo: 00 word to reg, 01 long to reg, 10 word to mem, 11 long
| to mem (bit 8 set with mode 001 is no other instruction).
	.globl	movep_handler, movep_old
movep_handler:
	movem.l	%d0-%d7/%a0-%a6,-(%sp)	| d n at 4n(sp), a n at 32+4n(sp); frame at 60(sp)
	move.l	62(%sp),%a0		| pc
	move.w	(%a0),%d0
	move.w	%d0,%d1
	and.w	#0xf138,%d1
	cmp.w	#0x0108,%d1
	bne.s	9f
	moveq	#7,%d1
	and.w	%d0,%d1
	cmp.w	#7,%d1
	beq.s	9f
	lsl.w	#2,%d1
	move.l	32(%sp,%d1.w),%a1	| an
	adda.w	2(%a0),%a1		| + displacement
	move.w	%d0,%d1
	lsr.w	#7,%d1
	and.w	#0x1c,%d1
	lea	(%sp,%d1.w),%a2		| saved dn (big-endian long)
	btst	#7,%d0
	bne.s	3f
	btst	#6,%d0
	bne.s	2f
	move.b	(%a1),2(%a2)		| word to register
	move.b	2(%a1),3(%a2)
	bra.s	8f
2:	move.b	(%a1),(%a2)		| long to register
	move.b	2(%a1),1(%a2)
	move.b	4(%a1),2(%a2)
	move.b	6(%a1),3(%a2)
	bra.s	8f
3:	btst	#6,%d0
	bne.s	4f
	move.b	2(%a2),(%a1)		| word to memory
	move.b	3(%a2),2(%a1)
	bra.s	8f
4:	move.b	(%a2),(%a1)		| long to memory
	move.b	1(%a2),2(%a1)
	move.b	2(%a2),4(%a1)
	move.b	3(%a2),6(%a1)
8:	addq.l	#4,62(%sp)		| past the movep
	movem.l	(%sp)+,%d0-%d7/%a0-%a6
	rte
9:	movem.l	(%sp)+,%d0-%d7/%a0-%a6
	move.l	movep_old,-(%sp)	| not ours: the previous handler, frame untouched
	rts

	.data
	.balign	2
movep_old:	.long	0
	.text
