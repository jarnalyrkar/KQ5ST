| Entry point, Prog launcher, LVO stubs, exception reporting and NatFeats for the KQ5 TOS shim.

	.text
	.globl	_start
_start:
	move.l	4(%sp),%a0		| basepage
| AmigaDOS BPTRs (address >> 2) need longword-aligned code and data, but TOS only word-aligns the
| program: under a real hard-disk driver it can load at 2 mod 4 (Hatari's GEMDOS drive happens
| to give 0 mod 4). Then move the image (text+data+bss) up 2 bytes and add 2 to every relocated
| long, using the copy of the fixup table elf2prg puts in .data (reloc_copy, TOS's format).
| Nothing absolute may be used before this.
	move.l	8(%a0),%a1		| p_tbase
	move.l	%a1,%d0
	btst	#1,%d0
	beq.s	3f
	move.l	0xc(%a0),%d0		| p_tlen + p_dlen + p_blen (multiples of 4)
	add.l	0x14(%a0),%d0
	add.l	0x1c(%a0),%d0
	add.l	%d0,%a1			| source end
	lea	2(%a1),%a2		| destination end
	lsr.l	#1,%d0			| words
	move.l	#0x66fa4e75,-(%sp)	| mover on the stack (the image moves under it):
	move.l	#0x35215380,-(%sp)	| 1: move.w -(a1),-(a2); subq.l #1,d0; bne.s 1b; rts
	lea	1f(%pc),%a3
	addq.l	#2,%a3			| return into the moved copy
	move.l	%a3,-(%sp)
	jmp	4(%sp)
1:	addq.l	#8,%sp
	addq.l	#2,8(%a0)		| p_tbase, p_dbase, p_bbase
	addq.l	#2,0x10(%a0)
	addq.l	#2,0x18(%a0)
	move.l	8(%a0),%a3
	lea	reloc_copy,%a1		| relocated by TOS for the old base
	addq.l	#2,%a1
	move.l	(%a1)+,%d0		| first fixup offset (0 = none)
	beq.s	3f
	add.l	%d0,%a3
2:	addq.l	#2,(%a3)
4:	moveq	#0,%d0
	move.b	(%a1)+,%d0
	beq.s	3f
	cmp.b	#1,%d0
	bne.s	5f
	lea	254(%a3),%a3
	bra.s	4b
5:	add.l	%d0,%a3
	bra.s	2b
3:	move.l	%a0,basepage
	lea	stack_top,%sp
	move.l	0xc(%a0),%d0		| p_tlen
	add.l	0x14(%a0),%d0		| p_dlen
	add.l	0x1c(%a0),%d0		| p_blen
	add.l	#0x102,%d0		| basepage itself, +2 if the image was moved
	move.l	%d0,-(%sp)
	move.l	%a0,-(%sp)
	clr.w	-(%sp)
	move.w	#0x4a,-(%sp)		| Mshrink
	trap	#1
	lea	12(%sp),%sp
	move.l	basepage,-(%sp)
	jsr	shim_main
	move.w	%d0,-(%sp)
	move.w	#0x4c,-(%sp)		| Pterm
	trap	#1

| long run_prog(void *entry, void *stack_top, long stack_size): call Prog's entry like
| AmigaDOS starts a process: own stack, 4(sp) = stack size; returns Prog's exit code.
	.globl	run_prog
run_prog:
	movem.l	%d2-%d7/%a2-%a6,-(%sp)
	clr.l	-(%sp)			| Super(0): continue in supervisor mode on this stack
	move.w	#0x20,-(%sp)
	trap	#1
	addq.l	#6,%sp
	move.l	%d0,saved_ssp
	move.l	%sp,saved_sp
	move.l	48(%sp),%a1		| entry
	move.l	56(%sp),%d1		| stack size
	move.l	52(%sp),%sp		| Prog stack
	move.l	%d1,-(%sp)
	lea	empty_args,%a0
	moveq	#1,%d0
	move.l	SysBase,%a6
	jsr	(%a1)
	move.l	saved_sp,%sp
	move.l	%d0,%d2
	move.l	saved_ssp,-(%sp)	| back to user mode
	move.w	#0x20,-(%sp)
	trap	#1
	addq.l	#6,%sp
	move.l	%d2,%d0
	movem.l	(%sp)+,%d2-%d7/%a2-%a6
	rts

| trap #5 replaces "movea.l $4.w,a6" in Prog: return the fake ExecBase in a6.
	.globl	trap5_handler
trap5_handler:
	move.l	SysBase,%a6
	rte

| Library vector stubs: save all registers, call c_<name>(struct regs *), restore.
| The C function returns results by writing r->d[0] (or any other register).
	.macro	LVO name
	.globl	stub_\name
stub_\name:
	movem.l	%d0-%d7/%a0-%a6,-(%sp)
	move.l	%sp,-(%sp)
	jsr	c_\name
	addq.l	#4,%sp
	movem.l	(%sp)+,%d0-%d7/%a0-%a6
	rts
	.endm
#include "lvos.inc"

| Mid-function hooks: run c_<name>(regs) and continue at a fixed address in Prog.
	.macro	HOOK name, resume
	.globl	hook_\name
hook_\name:
	movem.l	%d0-%d7/%a0-%a6,-(%sp)
	move.l	%sp,-(%sp)
	jsr	c_\name
	addq.l	#4,%sp
	movem.l	(%sp)+,%d0-%d7/%a0-%a6
	jmp	\resume
	.endm
	HOOK	pcfill, hunk55+0x184
	HOOK	setcursor, hunk17+0x180

| Kernel call trace (hunk 4 +$9ee): d1 = kernel number * 4, a2 = args (argc.w, args...). Runs the
| function itself between the two C calls, then resumes after Prog's own jsr.
	.globl	hook_ktrace
hook_ktrace:
	lea	-0x7816(%a4),%a6
	movea.l	(%a6,%d1.w),%a6
	movem.l	%d0-%d7/%a0-%a6,-(%sp)
	move.l	%sp,-(%sp)
	jsr	c_ktrace_pre
	addq.l	#4,%sp
	movem.l	(%sp)+,%d0-%d7/%a0-%a6
	jsr	(%a6)
	movem.l	%d0-%d7/%a0-%a6,-(%sp)
	move.l	%sp,-(%sp)
	jsr	c_ktrace_post
	addq.l	#4,%sp
	movem.l	(%sp)+,%d0-%d7/%a0-%a6
	jmp	hunk4+0x9f8

| IsObject (hunk 23 +$534): Amiga reads -10(NULL) from ROM harmlessly; reject low pointers first.
	.globl	hook_isobject
hook_isobject:
	btst	#0,11(%a5)		| odd pointer -> not an object
	bne.s	1f
	cmpa.w	#0x800,%a0		| NULL / low memory -> not an object
	bcs.s	1f
	cmpi.w	#0x1234,-10(%a0)
	bne.s	1f
	addq.w	#1,%d0
1:	jmp	hunk23+0x546

| Replacement for TOS's ikbdsys (Kbdvbase entry 8): called from the ACIA interrupt handler in
| supervisor mode with d0-d3/a0-a3/a5 saved, once per pending byte. Reads the keyboard ACIA and
| hands the byte to ikbd_byte (input.c); anything else (IRQ without data) goes to the TOS routine.
	.globl	ikbd_handler, old_ikbdsys
ikbd_handler:
	move.b	0xfffffc00,%d0		| ACIA status
	btst	#7,%d0			| IRQ pending?
	beq.s	9f
	btst	#0,%d0			| receive data register full?
	beq.s	8f
	move.b	0xfffffc02,%d0		| the byte (clears the interrupt)
	and.l	#0xff,%d0
	move.l	%d0,-(%sp)
	jsr	ikbd_byte
	addq.l	#4,%sp
9:	rts
8:	move.l	old_ikbdsys,%a0
	jmp	(%a0)

| IKBD relative mouse packet handler (a0 = packet: $f8|buttons, dx, dy). Supervisor mode.
| mouse_packet(pkt) is the C-callable entry (used by ikbd_byte).
	.globl	mouse_handler, mouse_packet, mouse_x, mouse_y, mouse_buttons
mouse_packet:
	move.l	4(%sp),%a0
mouse_handler:
	movem.l	%d0-%d2/%a0-%a2,-(%sp)
	move.b	(%a0),%d0
	and.b	#3,%d0
	move.b	mouse_buttons,%d1
	cmp.b	%d0,%d1
	beq.s	5f
	move.b	%d0,mouse_buttons
	movem.l	%d0/%a0,-(%sp)
	and.l	#3,%d0
	and.l	#3,%d1
	move.l	%d0,-(%sp)		| new
	move.l	%d1,-(%sp)		| old
	jsr	mouse_buttons_changed
	addq.l	#8,%sp
	movem.l	(%sp)+,%d0/%a0
5:	move.b	1(%a0),%d0
	ext.w	%d0
	add.w	mouse_x,%d0
	bpl.s	1f
	clr.w	%d0
1:	cmp.w	#319,%d0
	ble.s	2f
	move.w	#319,%d0
2:	move.w	%d0,mouse_x
	move.b	2(%a0),%d0
	ext.w	%d0
	add.w	mouse_y,%d0
	bpl.s	3f
	clr.w	%d0
3:	cmp.w	#199,%d0
	ble.s	4f
	move.w	#199,%d0
4:	move.w	%d0,mouse_y
	movem.l	(%sp)+,%d0-%d2/%a0-%a2
	rts

| long call_prog1(void *fn, u32 a4, void *arg): call a C function inside Prog with Prog's A4.
	.globl	call_prog1
call_prog1:
	movem.l	%d2-%d7/%a2-%a6,-(%sp)
	move.l	48(%sp),%a0		| fn
	move.l	52(%sp),%a4		| Prog A4
	move.l	56(%sp),-(%sp)		| arg
	jsr	(%a0)
	addq.l	#4,%sp
	movem.l	(%sp)+,%d2-%d7/%a2-%a6
	rts

| ---- Speed hooks in SCI's own code -------------------------------------------------------------

| Free handle slot (hunk 59 +$c16): the original scans the handle table from the start every time.
| Next-fit: continue after the last slot found, wrap once. Returns slot address or 0 in d0.
	.globl	hook_findslot
hook_findslot:
	movem.l	%a1-%a3,-(%sp)
	move.l	-0x4f42(%a4),%a2		| table start
	move.l	-0x590e(%a4),%a3		| table end
	move.l	slot_hint,%a1
	cmp.l	%a2,%a1
	bcs.s	1f
	cmp.l	%a3,%a1
	bcs.s	2f
1:	move.l	%a2,%a1
2:	move.l	%a1,%d0				| d0 = where the first pass started
3:	cmp.l	%a3,%a1				| pass 1: hint .. end
	bcc.s	4f
	tst.l	(%a1)+
	bne.s	3b
	bra.s	6f
4:	move.l	%a2,%a1				| pass 2: start .. hint
5:	cmp.l	%d0,%a1
	bcc.s	7f
	tst.l	(%a1)+
	bne.s	5b
6:	move.l	%a1,slot_hint			| found: slot = a1 - 4
	subq.l	#4,%a1
	move.l	%a1,%d0
	movem.l	(%sp)+,%a1-%a3
	rts
7:	moveq	#0,%d0
	movem.l	(%sp)+,%a1-%a3
	rts

| Property lookup in SCI send (hunk 23 +$22c): a1 = selector list, d4 = selector, a3 = values.
| A 256-entry cache maps (list, selector) to the index; a hit is used only after checking that the
| list holds the selector at that index (selectors are unique in a list, so it is then correct).
| Continues at +$23c (found; d2 = count-1-index, d3 = count) or +$25e (not found), as the original.
	.globl	hook_proplookup
hook_proplookup:
	move.w	-2(%a3),%d2
	move.w	%d2,%d3				| d3 = count
	move.l	%a6,-(%sp)
	move.l	%a1,%d0
	eor.w	%d4,%d0
	and.w	#0x1fe,%d0			| cache slot offset
	lea	propcache,%a6
	move.w	(%a6,%d0.w),%d2			| cached index * 2
	cmp.w	%d3,%d2
	bcc.s	1f				| (index*2 >= count*2 is caught below too)
	lsr.w	#1,%d2
	cmp.w	%d3,%d2
	bcc.s	1f
	add.w	%d2,%d2
	cmp.w	(%a1,%d2.w),%d4
	bne.s	1f
	lsr.w	#1,%d2				| hit: d2 = count - 1 - index
	neg.w	%d2
	add.w	%d3,%d2
	subq.w	#1,%d2
	move.l	(%sp)+,%a6
	jmp	hunk23+0x23c
1:	move.w	%d3,%d2				| miss: the original linear search
	subq.w	#1,%d2
	move.l	%d1,-(%sp)
2:	cmp.w	(%a1)+,%d4
	dbeq	%d2,2b
	bne.s	3f
	move.w	%d3,%d1				| found: remember index * 2
	sub.w	%d2,%d1
	subq.w	#1,%d1
	add.w	%d1,%d1
	move.w	%d1,(%a6,%d0.w)
	move.l	(%sp)+,%d1
	move.l	(%sp)+,%a6
	jmp	hunk23+0x23c
3:	move.l	(%sp)+,%d1
	move.l	(%sp)+,%a6
	jmp	hunk23+0x25e

| Unimplemented vector: each library slot is "jsr unimpl_vector" (6 bytes).
	.globl	unimpl_vector
unimpl_vector:
	move.l	4(%sp),-(%sp)		| caller's return address (in Prog)
	move.l	4(%sp),-(%sp)		| slot+6
	jsr	c_unimpl
	| not reached

| Exception reporting. Each vector pushes its number and joins the common path.
	.macro	EXC n
	.globl	exc_\n
exc_\n:
	move.w	#\n,-(%sp)
	bra	exc_common
	.endm
	EXC	2
	EXC	3
	EXC	4
	EXC	5
	EXC	6
	EXC	7
	EXC	8
	EXC	10
	EXC	11
exc_common:
	movem.l	%d0-%d7/%a0-%a7,-(%sp)	| saved a7 = supervisor sp after the vector word
	move.l	%usp,%a0
	move.l	%a0,-(%sp)
	move.l	%sp,-(%sp)
	jsr	c_exception		| (u32 *frame): usp, d0-d7, a0-a7, vec.w, cpu frame
1:	bra	1b

| VBL queue entry (TOS calls it in supervisor mode every vertical blank): run the Amiga
| VERTB interrupt servers with A1 = is_Data, A5 = is_Code, A6 = ExecBase, unless Disable()d.
	.globl	vbl_dispatch, vbl_servers, int_disable, vbl_count
vbl_dispatch:
	addq.l	#1,vbl_count
	movem.l	%d0-%d1/%a0-%a1,-(%sp)
	jsr	vbl_hook
	jsr	input_vbl
	jsr	display_vbl
	movem.l	(%sp)+,%d0-%d1/%a0-%a1
	tst.w	int_disable
	bne.s	2f
	movem.l	%d0-%d7/%a0-%a6,-(%sp)
	lea	vbl_servers,%a2
1:	move.l	(%a2)+,%d0
	beq.s	3f
	move.l	%d0,%a0
	move.l	14(%a0),%a1		| is_Data
	move.l	18(%a0),%a5		| is_Code
	move.l	SysBase,%a6
	move.l	%a2,-(%sp)
	jsr	(%a5)
	move.l	(%sp)+,%a2
	bra.s	1b
3:	movem.l	(%sp)+,%d0-%d7/%a0-%a6
2:	rts

| Silent SCI sound driver with the interface of amiga3v.drv (entry = seglist + 4, d7 = function).
| LoadSeg("*.drv") returns this segment until the YM2149 driver exists.
	.data
	.balign	4
	.globl	silent_seg
silent_seg:
	.long	0			| next segment (BPTR)
	jmp	silent_dispatch
	.text
silent_dispatch:
	tst.w	%d7
	beq.s	sd_info
	cmp.w	#1,%d7
	beq.s	sd_init
	cmp.w	#12,%d7
	beq.s	sd_volume
	cmp.w	#13,%d7
	beq.s	sd_flag
	cmp.w	#17,%d7
	beq.s	sd_query
	rts
sd_info:	move.l	#0x00010065,%d0		| as amiga3v: no patch file, device $13 (PCjr/Tandy tracks)
	move.l	#0x00130004,%d1
	rts
sd_init:	move.l	#0x000f0000,%d0
	rts
sd_volume:	cmp.w	#0xff,%d0
	bne.s	1f
	move.w	sd_vol,%d0
	rts
1:	move.w	%d0,sd_vol
	rts
sd_flag:	cmp.b	#0xff,%d0
	bne.s	1f
	clr.w	%d0
	move.b	sd_flg,%d0
	rts
1:	move.b	%d0,sd_flg
	rts
sd_query:	move.w	#0xffff,%d0
	rts

| PC sampler: wraps the level-4 autovector ($70) and records the interrupted PC every VBL.
	.globl	pcsample_entry, old_vbl_vector, pc_samples, pc_sample_idx
pcsample_entry:
	move.l	%a0,-(%sp)
	move.l	pc_sample_idx,%a0
	add.l	#pc_samples,%a0
	move.l	2+4(%sp),(%a0)		| PC from the exception frame (after the saved a0)
	addq.l	#4,pc_sample_idx
	and.l	#0x3ff,pc_sample_idx	| ring of 256 samples
	tas	in_vbl			| run our VBL work unless already running
	bmi.s	1f
	bsr	vbl_dispatch
	clr.b	in_vbl
1:	move.l	(%sp)+,%a0
	move.l	old_vbl_vector,-(%sp)
	rts

| Profiler sample on MFP Timer A (not locked to the VBL): histogram of PCs in 64-byte buckets.
	.globl	timera_prof, prof_hist_ptr, prof_base, prof_limit, prof_total_a, prof_other_a
timera_prof:
	movem.l	%d0/%a0,-(%sp)
	move.l	2+8(%sp),%d0			| interrupted PC
	addq.l	#1,prof_total_a
	sub.l	prof_base,%d0
	cmp.l	prof_limit,%d0
	bcc.s	1f
	lsr.l	#6,%d0
	add.l	%d0,%d0
	move.l	prof_hist_ptr,%a0
	addq.w	#1,(%a0,%d0.l)
	bra.s	2f
1:	addq.l	#1,prof_other_a
2:	movem.l	(%sp)+,%d0/%a0
	bclr	#5,0xfffffa0f.w			| end of interrupt (ISRA timer A)
	rte

| Start the blitter (shared bus) and wait: the restart loop re-triggers it until BUSY clears.
	.globl	blitter_go
blitter_go:
	move.b	#0x80,0xffff8a3c.w
1:	bset.b	#7,0xffff8a3c.w
	nop
	bne.s	1b
	rts

| NatFeats (Hatari): nf_id(name) / nf_call(id, ...)
nf_id_op:	.short	0x7300
	rts
nf_call_op:	.short	0x7301
	rts

	.globl	nf_available
nf_available:
	move.l	nf_stderr_id,%d0
	rts

| Illegal-instruction handler while probing: without NatFeats (real ST, Steem, Hatari with
| natfeats off) $7300 traps here; answer id 0 (feature absent) and skip the opcode.
	.globl	nf_illegal
nf_illegal:
	moveq	#0,%d0
	addq.l	#2,2(%sp)
	rte

	.globl	nf_init
nf_init:
	pea	nf_name_stderr
	bsr	nf_id_op
	addq.l	#4,%sp
	move.l	%d0,nf_stderr_id
	pea	nf_name_exit
	bsr	nf_id_op
	addq.l	#4,%sp
	move.l	%d0,nf_exit_id
	rts

	.globl	nf_stderr
nf_stderr:
	move.l	nf_stderr_id,%d0
	beq.s	1f
	move.l	4(%sp),-(%sp)
	move.l	%d0,-(%sp)
	bsr	nf_call_op
	addq.l	#8,%sp
1:	rts

	.globl	nf_exit
nf_exit:
	move.l	nf_exit_id,%d0
	beq.s	1f
	move.l	4(%sp),-(%sp)
	move.l	%d0,-(%sp)
	bsr	nf_call_op
	addq.l	#8,%sp
1:	rts

	.data
nf_name_stderr:	.asciz	"NF_STDERR"
nf_name_exit:	.asciz	"NF_EXIT"
empty_args:	.asciz	"\n"
	.even

	.bss
vbl_servers:	.space	4*8		| NULL-terminated list of struct Interrupt *
vbl_count:	.space	4
slot_hint:	.space	4
propcache:	.space	512
prof_hist_ptr:	.space	4
prof_base:	.space	4
prof_limit:	.space	4
prof_total_a:	.space	4
prof_other_a:	.space	4
old_vbl_vector:	.space	4
in_vbl:	.space	2
pc_sample_idx:	.space	4
pc_samples:	.space	1024
sd_vol:	.space	2
mouse_x:	.space	2
mouse_y:	.space	2
mouse_buttons:	.space	2
sd_flg:	.space	2
int_disable:	.space	2
	.even
	.globl	basepage
basepage:	.space	4
saved_sp:	.space	4
saved_ssp:	.space	4
nf_stderr_id:	.space	4
nf_exit_id:	.space	4
	.space	16384
stack_top:
