| SCI bytecode interpreter ("PMachine") rewritten for speed (2026-11-07). Replaces the dispatch
| loop and opcode handlers of Prog hunk 4 (+$402..+$2126), the call-frame helper (+$308) and the
| calle/callb helper (+$2a8). Entered through the data-hunk vector 3 (hunk 4 +$402, patched to
| pm_entry in prog.patch), which hunk 23's send uses to run a method; everything else in hunk 4
| that is still used (game start +$204, export lookup +$33e) is untouched.
|
| Same semantics as the original, opcode by opcode (docs/ARCHITECTURE.md "Bytecode interpreter");
| checked against it with tools/equiv/pmtest.py. What is different is only where the state lives
| while bytecode runs:
|   a0 = PC            a2 = SCI stack top (points at the top word; push = addq #2 then store)
|   a3 = globals base  a5 = self (OBJ)   a6 = dispatch table   d7 = acc   d2 = prev (as Prog)
| The original kept acc and every base pointer in A4 globals and reloaded them per opcode. Here the
| globals (-$7134 acc, -$7174 globals, -$7160 self) are written back before every call out of the
| loop (kernel functions, send, script loader, error) and reloaded after it, because those read or
| change them (kernel functions return their result in acc). The PC is passed as an offset from the
| current script's code across such calls, as Prog does, since a script can move while one runs.
| Locals/temps/params/rest stay in the globals (they change per call frame and hunk 23 uses them).
| d4-d6 are untouched; d7/a3/a5 are saved and restored around the external entry.

	.set	ACC,       -0x7134
	.set	CALLKPC,   -0x7144	| PC at the last callk operand (Prog debug aid)
	.set	SCRIPTNUM, -0x7148
	.set	SCRIPT,    -0x7150	| handle of the running script: *SCRIPT = code base
	.set	CLASSTBL,  -0x715c	| class table: word near pointer of the class object, word script
	.set	OBJ,       -0x7160
	.set	REST,      -0x7164	| bytes pushed by &rest for the next call
	.set	PARAMS,    -0x7168	| -> argc word of the current frame
	.set	TEMPS,     -0x716c
	.set	LOCALS,    -0x7170
	.set	GLOBALS,   -0x7174
	.set	STKLIM,    -0x7178
	.set	STKSAVE,   -0x7180
	.set	PCSAVE,    -0x7184
	.set	KMAX,      -0x7626	| highest kernel function number
	.set	KTAB,      -0x7816	| kernel function table (longs)
	.set	HEAP,      -0x5912	| base of SCI near pointers (word offsets; 0 = NULL)
	.set	ERROR,     -0x7b90	| vector 189: PError(pc, sp, code, ...), does not return
	.set	LOADSCRIPT,-0x7f9e	| vector 16: hunk 8 +$10, script struct for a script number
	.set	LOADCLASS, -0x7f98	| vector 17: hunk 8 +$38, load the script of a class

| ---- fetch and dispatch -------------------------------------------------------------------
	.macro	NEXT
	moveq	#0,%d1
	move.b	(%a0)+,%d1
	add.w	%d1,%d1
	move.w	(%a6,%d1.w),%d1
	jmp	(%a6,%d1.w)
	.endm
	.macro	FETCHB reg		| unsigned byte operand
	moveq	#0,\reg
	move.b	(%a0)+,\reg
	.endm
	.macro	FETCHW reg		| little-endian word operand (any alignment)
	movep.w	1(%a0),\reg
	move.b	(%a0)+,\reg
	addq.l	#1,%a0
	.endm
	.macro	SYNC_OUT		| before calling out of the loop
	move.w	%d7,ACC(%a4)
	.endm
	.macro	SYNC_IN			| after a call out of the loop
	lea	pm_tab,%a6
	move.l	GLOBALS(%a4),%a3
	move.l	OBJ(%a4),%a5
	move.w	ACC(%a4),%d7
	.endm
| PC -> offset from the running script's code (what Prog keeps on its stack across calls)
	.macro	PC_TO_OFF
	move.l	SCRIPT(%a4),%a1
	move.l	(%a1),%a1
	sub.l	%a1,%a0
	.endm

	.text

| ---- external entry (vector 3): a0 = PC, a2 = stack; runs until the matching ret ----------
	.globl	pm_entry
pm_entry:
	movem.l	%d2/%d4-%d7/%a3/%a5,-(%sp)
	lea	pm_tab,%a6
	move.l	GLOBALS(%a4),%a3
	move.l	OBJ(%a4),%a5
	move.w	ACC(%a4),%d7
	bsr	pm_loop
	move.w	%d7,ACC(%a4)
	movem.l	(%sp)+,%d2/%d4-%d7/%a3/%a5
	rts

| Call frame (Prog hunk 4 +$308): d0.w = argument bytes, a0 = code, a2 = stack. Sets up
| params (argc word adjusted by &rest), runs the code, pops the frame.
pm_callframe:
	move.l	PARAMS(%a4),-(%sp)
	move.l	TEMPS(%a4),-(%sp)
	move.l	%a2,%a1
	suba.w	%d0,%a1
	move.w	REST(%a4),%d0
	suba.w	%d0,%a1
	move.l	%a1,PARAMS(%a4)
	lsr.w	#1,%d0
	add.w	%d0,(%a1)
	clr.w	REST(%a4)
	bsr	pm_loop
	move.l	PARAMS(%a4),%a2
	subq.l	#2,%a2
	move.l	%a2,STKSAVE(%a4)
	move.l	(%sp)+,TEMPS(%a4)
	move.l	(%sp)+,PARAMS(%a4)
	rts

pm_loop:
	NEXT
pm_ret:
	rts

| ---- dispatch table: one word per opcode byte (bit 0 = byte-sized operands) ----------------
	.macro	OP w, b
	.word	\w-pm_tab, \b-pm_tab
	.endm
	.macro	OPV n			| word and byte form of a variable-access handler
	.word	\n\()w-pm_tab, \n\()b-pm_tab
	.endm
	.balign	2
pm_tab:
	OP pm_bnot, pm_bnot		| 00
	OP pm_add, pm_add		| 02
	OP pm_sub, pm_sub		| 04
	OP pm_mul, pm_mul		| 06
	OP pm_div, pm_div		| 08
	OP pm_mod, pm_mod		| 0a
	OP pm_shr, pm_shr		| 0c
	OP pm_shl, pm_shl		| 0e
	OP pm_xor, pm_xor		| 10
	OP pm_and, pm_and		| 12
	OP pm_or, pm_or			| 14
	OP pm_neg, pm_neg		| 16
	OP pm_not, pm_not		| 18
	OP pm_eq, pm_eq			| 1a
	OP pm_ne, pm_ne			| 1c
	OP pm_gt, pm_gt			| 1e
	OP pm_ge, pm_ge			| 20
	OP pm_lt, pm_lt			| 22
	OP pm_le, pm_le			| 24
	OP pm_ugt, pm_ugt		| 26
	OP pm_uge, pm_uge		| 28
	OP pm_ult, pm_ult		| 2a
	OP pm_ule, pm_ule		| 2c
	OP pm_btw, pm_btb		| 2e
	OP pm_bntw, pm_bntb		| 30
	OP pm_jmpw, pm_jmpb		| 32
	OP pm_ldiw, pm_ldib		| 34
	OP pm_push, pm_push		| 36
	OP pm_pushiw, pm_pushib		| 38
	OP pm_toss, pm_toss		| 3a
	OP pm_dup, pm_dup		| 3c
	OP pm_linkw, pm_linkb		| 3e
	OP pm_callw, pm_callb		| 40
	OP pm_callkw, pm_callkb		| 42
	OP pm_callbw, pm_callbb		| 44
	OP pm_callew, pm_calleb		| 46
	OP pm_ret, pm_ret		| 48
	OP pm_send, pm_send		| 4a
	OP pm_bad, pm_bad		| 4c
	OP pm_bad, pm_bad		| 4e
	OP pm_classw, pm_classb		| 50
	OP pm_bad, pm_bad		| 52
	OP pm_self, pm_self		| 54
	OP pm_superw, pm_superb		| 56
	OP pm_rest, pm_rest		| 58
	OP pm_leaw, pm_leab		| 5a
	OP pm_selfid, pm_selfid		| 5c
	OP pm_bad, pm_bad		| 5e
	OP pm_pprev, pm_pprev		| 60
	OP pm_ptoaw, pm_ptoab		| 62
	OP pm_atopw, pm_atopb		| 64
	OP pm_ptosw, pm_ptosb		| 66
	OP pm_stopw, pm_stopb		| 68
	OP pm_iptoaw, pm_iptoab		| 6a
	OP pm_dptoaw, pm_dptoab		| 6c
	OP pm_iptosw, pm_iptosb		| 6e
	OP pm_dptosw, pm_dptosb		| 70
	OP pm_lofsa, pm_bad		| 72
	OP pm_lofss, pm_bad		| 74
	OP pm_push0, pm_push0		| 76
	OP pm_push1, pm_push1		| 78
	OP pm_push2, pm_push2		| 7a
	OP pm_pushself, pm_pushself	| 7c
	OP pm_bad, pm_bad		| 7e
| 80..ff: variable access. Byte bits: 6-5 kind (load, store, inc, dec), 4 add acc to the
| index, 3 via the stack (push / pop) instead of acc, 2-1 type (global, local, temp, param).
	.irp	k,l,s,i,d
	.irp	x,0,1
	.irp	s,0,1
	.irp	t,g,l,t,p
	OPV pm_v\k\x\s\t
	.endr
	.endr
	.endr
	.endr

| ---- arithmetic (acc and the stack) -------------------------------------------------------
pm_bnot:
	not.w	%d7
	NEXT
pm_add:
	add.w	(%a2),%d7
	subq.l	#2,%a2
	NEXT
pm_sub:
	move.w	(%a2),%d0
	subq.l	#2,%a2
	sub.w	%d7,%d0
	move.w	%d0,%d7
	NEXT
pm_mul:
	move.w	(%a2),%d0
	subq.l	#2,%a2
	mulu.w	%d7,%d0
	move.w	%d0,%d7
	NEXT
pm_div:
	move.w	(%a2),%d0
	subq.l	#2,%a2
	ext.l	%d0
	tst.w	%d7
	beq	pm_err_divzero
	divs.w	%d7,%d0
	move.w	%d0,%d7
	NEXT
pm_mod:					| result has the sign of |acc| (0 .. |acc|-1), as Prog
	move.w	(%a2),%d0
	subq.l	#2,%a2
	ext.l	%d0
	tst.w	%d7
	beq	pm_err_divzero
	bpl	1f
	neg.w	%d7
1:	divs.w	%d7,%d0
	swap	%d0
	tst.w	%d0
	bmi	2f
	move.w	%d0,%d7
	NEXT
2:	add.w	%d0,%d7
	NEXT
pm_shr:
	move.w	(%a2),%d0
	subq.l	#2,%a2
	move.w	%d7,%d2
	lsr.w	%d2,%d0
	move.w	%d0,%d7
	NEXT
pm_shl:
	move.w	(%a2),%d0
	subq.l	#2,%a2
	move.w	%d7,%d2
	lsl.w	%d2,%d0
	move.w	%d0,%d7
	NEXT
pm_xor:
	move.w	(%a2),%d0
	subq.l	#2,%a2
	eor.w	%d0,%d7
	NEXT
pm_and:
	and.w	(%a2),%d7
	subq.l	#2,%a2
	NEXT
pm_or:
	or.w	(%a2),%d7
	subq.l	#2,%a2
	NEXT
pm_neg:
	neg.w	%d7
	NEXT
pm_not:
	tst.w	%d7
	bne	1f
	moveq	#1,%d7
	NEXT
1:	moveq	#0,%d7
	NEXT

| comparisons: acc = (popped value <op> acc); prev (d2) = acc as Prog leaves it
	.macro	CMPOP name, cc
pm_\name:
	move.w	%d7,%d2
	cmp.w	(%a2),%d2
	subq.l	#2,%a2
	b\cc	pm_true
	moveq	#0,%d7
	NEXT
	.endm
	CMPOP	eq, eq
	CMPOP	ne, ne
	CMPOP	gt, lt
	CMPOP	ge, le
	CMPOP	lt, gt
	CMPOP	le, ge
	CMPOP	ugt, cs
	CMPOP	uge, ls
	CMPOP	ult, hi
	CMPOP	ule, cc
pm_true:
	moveq	#1,%d7
	NEXT

| ---- branches -----------------------------------------------------------------------------
pm_jmpb:
	move.b	(%a0)+,%d0
	ext.w	%d0
	adda.w	%d0,%a0
	NEXT
pm_jmpw:
	FETCHW	%d0
	adda.w	%d0,%a0
	NEXT
pm_btb:
	tst.w	%d7
	bne	pm_jmpb
	addq.l	#1,%a0
	NEXT
pm_btw:
	tst.w	%d7
	bne	pm_jmpw
	addq.l	#2,%a0
	NEXT
pm_bntb:
	tst.w	%d7
	beq	pm_jmpb
	addq.l	#1,%a0
	NEXT
pm_bntw:
	tst.w	%d7
	beq	pm_jmpw
	addq.l	#2,%a0
	NEXT

| ---- constants and the stack --------------------------------------------------------------
pm_ldib:
	move.b	(%a0)+,%d7
	ext.w	%d7
	NEXT
pm_ldiw:
	FETCHW	%d7
	NEXT
pm_push:
	addq.l	#2,%a2
	move.w	%d7,(%a2)
	NEXT
pm_pushib:
	move.b	(%a0)+,%d0
	ext.w	%d0
	addq.l	#2,%a2
	move.w	%d0,(%a2)
	NEXT
pm_pushiw:
	FETCHW	%d0
	addq.l	#2,%a2
	move.w	%d0,(%a2)
	NEXT
pm_push0:
	addq.l	#2,%a2
	clr.w	(%a2)
	NEXT
pm_push1:
	addq.l	#2,%a2
	move.w	#1,(%a2)
	NEXT
pm_push2:
	addq.l	#2,%a2
	move.w	#2,(%a2)
	NEXT
pm_pushself:
	move.l	%a5,%d0
	beq	1f
	sub.l	HEAP(%a4),%d0
1:	addq.l	#2,%a2
	move.w	%d0,(%a2)
	NEXT
pm_selfid:
	move.l	%a5,%d0
	beq	1f
	sub.l	HEAP(%a4),%d0
1:	move.w	%d0,%d7
	NEXT
pm_toss:
	subq.l	#2,%a2
	NEXT
pm_dup:
	move.w	(%a2),%d0
	addq.l	#2,%a2
	move.w	%d0,(%a2)
	NEXT
pm_pprev:
	addq.l	#2,%a2
	move.w	%d2,(%a2)
	NEXT
pm_lofsa:
	FETCHW	%d7
	NEXT
pm_lofss:
	FETCHW	%d0
	addq.l	#2,%a2
	move.w	%d0,(%a2)
	NEXT
pm_linkb:				| temps = stack + 2, reserve n words
	FETCHB	%d0
	bra	1f
pm_linkw:
	FETCHW	%d0
1:	lea	2(%a2),%a1
	move.l	%a1,TEMPS(%a4)
	add.w	%d0,%d0
	adda.w	%d0,%a2
	cmpa.l	STKLIM(%a4),%a2
	bcc	pm_err_stack
	NEXT
pm_rest:				| push params n.. and count them for the next call
	move.l	PARAMS(%a4),%a1
	move.w	(%a1),%d2
	FETCHB	%d0
	sub.w	%d0,%d2
	addq.w	#1,%d2
	bpl	1f
	clr.w	%d2
1:	add.w	%d2,REST(%a4)
	add.w	%d2,REST(%a4)
	add.w	%d0,%d0
	adda.w	%d0,%a1
	bra	3f
2:	addq.l	#2,%a2
	move.w	(%a1)+,(%a2)
3:	dbra	%d2,2b
	NEXT
pm_leab:				| acc = near pointer of variable (type, index [+acc])
	FETCHB	%d1
	FETCHB	%d0
	bra	1f
pm_leaw:
	FETCHW	%d1
	FETCHW	%d0
1:	move.w	%d0,%d3
	add.w	%d3,%d3
	btst	#4,%d1
	beq	2f
	move.w	%d7,%d0
	add.w	%d0,%d0
	add.w	%d0,%d3
2:	and.w	#6,%d1
	add.w	%d1,%d1
	lea	GLOBALS(%a4),%a1
	move.l	(%a1,%d1.w),%d0
	beq	3f
	sub.l	HEAP(%a4),%d0
3:	add.w	%d3,%d0
	move.w	%d0,%d7
	NEXT

| ---- properties of self -------------------------------------------------------------------
	.macro	PROPOP name
pm_\name\()b:
	FETCHB	%d0
	bra	1f
pm_\name\()w:
	FETCHW	%d0
1:
	.endm
	PROPOP	ptoa
	move.w	(%a5,%d0.w),%d7
	NEXT
	PROPOP	atop
	move.w	%d7,(%a5,%d0.w)
	NEXT
	PROPOP	ptos
	addq.l	#2,%a2
	move.w	(%a5,%d0.w),(%a2)
	NEXT
	PROPOP	stop
	move.w	(%a2),(%a5,%d0.w)
	subq.l	#2,%a2
	NEXT
	PROPOP	iptoa
	addq.w	#1,(%a5,%d0.w)
	move.w	(%a5,%d0.w),%d7
	NEXT
	PROPOP	dptoa
	subq.w	#1,(%a5,%d0.w)
	move.w	(%a5,%d0.w),%d7
	NEXT
	PROPOP	iptos
	addq.w	#1,(%a5,%d0.w)
	addq.l	#2,%a2
	move.w	(%a5,%d0.w),(%a2)
	NEXT
	PROPOP	dptos
	subq.w	#1,(%a5,%d0.w)
	addq.l	#2,%a2
	move.w	(%a5,%d0.w),(%a2)
	NEXT

| ---- variables: globals (a3), locals, temps, params ---------------------------------------
| VAR kind, idx, stk, type, size, base register, global holding the base ("" = a3 already)
	.macro	VAR k, x, s, t, z, base, off
pm_v\k\x\s\t\z:
	.ifc	\z,b
	FETCHB	%d0
	.else
	FETCHW	%d0
	.endif
	.if	\x
	add.w	%d7,%d0
	.endif
	add.w	%d0,%d0
	.ifnc	"\off",""
	move.l	\off(%a4),\base
	.endif
	.ifc	\k,l
	.if	\s
	addq.l	#2,%a2
	move.w	(\base,%d0.w),(%a2)
	.else
	move.w	(\base,%d0.w),%d7
	.endif
	.endif
	.ifc	\k,s
	.if	\s
	move.w	(%a2),(\base,%d0.w)
	subq.l	#2,%a2
	.else
	.if	\x
	move.w	(%a2),%d7
	subq.l	#2,%a2
	.endif
	move.w	%d7,(\base,%d0.w)
	.endif
	.endif
	.ifc	\k,i
	addq.w	#1,(\base,%d0.w)
	.if	\s
	addq.l	#2,%a2
	move.w	(\base,%d0.w),(%a2)
	.else
	move.w	(\base,%d0.w),%d7
	.endif
	.endif
	.ifc	\k,d
	subq.w	#1,(\base,%d0.w)
	.if	\s
	addq.l	#2,%a2
	move.w	(\base,%d0.w),(%a2)
	.else
	move.w	(\base,%d0.w),%d7
	.endif
	.endif
	NEXT
	.endm
	.irp	k,l,s,i,d
	.irp	x,0,1
	.irp	s,0,1
	.irp	z,w,b
	VAR	\k,\x,\s,g,\z,%a3,""
	VAR	\k,\x,\s,l,\z,%a1,LOCALS
	VAR	\k,\x,\s,t,\z,%a1,TEMPS
	VAR	\k,\x,\s,p,\z,%a1,PARAMS
	.endr
	.endr
	.endr
	.endr

| ---- calls ---------------------------------------------------------------------------------
pm_callb:				| call: relative target, frame size
	move.b	(%a0)+,%d1
	ext.w	%d1
	bra	1f
pm_callw:
	FETCHW	%d1
1:	FETCHB	%d0
	move.l	SCRIPT(%a4),-(%sp)
	move.l	SCRIPT(%a4),%a1
	move.l	(%a1),%a1
	move.l	%a0,%d3
	sub.l	%a1,%d3
	move.l	%d3,-(%sp)
	adda.w	%d1,%a0
	bsr	pm_callframe
	move.l	(%sp)+,%a0
	move.l	SCRIPT(%a4),%a1
	adda.l	(%a1),%a0
	move.l	(%sp)+,SCRIPT(%a4)
	NEXT

pm_callbb:				| callb: export of script 0
	FETCHB	%d1
	clr.w	%d2
	FETCHB	%d0
	bsr	pm_callext
	NEXT
pm_callbw:
	FETCHW	%d1
	clr.w	%d2
	FETCHB	%d0
	bsr	pm_callext
	NEXT
pm_calleb:				| calle: script, export
	FETCHB	%d0
	move.w	%d0,%d2
	FETCHB	%d1
	FETCHB	%d0
	bsr	pm_callext
	NEXT
pm_callew:
	FETCHW	%d0
	move.w	%d0,%d2
	FETCHW	%d1
	FETCHB	%d0
	bsr	pm_callext
	NEXT

| External call (Prog hunk 4 +$2a8 with its export lookup +$3b8): d0.w = argument bytes,
| d1.w = export number, d2.w = script number. The loader can move scripts: the PC is kept as
| an offset. The current script number, script handle and locals are switched for the callee.
pm_callext:
	move.l	SCRIPT(%a4),-(%sp)
	move.w	SCRIPTNUM(%a4),-(%sp)
	move.w	%d2,SCRIPTNUM(%a4)
	move.l	%a0,-(%sp)
	PC_TO_OFF
	move.l	%a0,-(%sp)
	move.l	LOCALS(%a4),-(%sp)
	move.w	%d0,-(%sp)
	SYNC_OUT
	move.l	%a2,-(%sp)
	move.w	%d1,-(%sp)
	move.w	%d2,-(%sp)
	jsr	LOADSCRIPT(%a4)
	addq.l	#2,%sp
	move.w	(%sp)+,%d1
	move.l	(%sp)+,%a2
	move.w	%d1,-(%sp)
	SYNC_IN				| the loader is C code: assume nothing about registers
	move.l	%d0,%d2			| script struct (d2.w as Prog leaves it)
	move.l	%d0,%a1
	move.l	0xa(%a1),%a0
	move.l	(%a0),%d3		| code base
	move.l	%d3,%a0
	adda.w	0xe(%a1),%a0		| export table: count, then 4-byte entries (offset, unused)
	move.w	(%sp)+,%d1
	cmp.w	(%a0),%d1
	bge	pm_err_export
	add.w	%d1,%d1
	add.w	%d1,%d1
	move.w	2(%a0,%d1.w),%d0
	move.l	%d3,%a0
	adda.w	%d0,%a0			| export address
	move.l	0xa(%a1),SCRIPT(%a4)
	move.l	0x10(%a1),LOCALS(%a4)
	move.w	(%sp)+,%d0
	bsr	pm_callframe
	move.l	(%sp)+,LOCALS(%a4)
	move.l	(%sp)+,%a0
	move.l	(%sp)+,%d0
	move.w	(%sp)+,SCRIPTNUM(%a4)
	move.l	(%sp)+,SCRIPT(%a4)
	move.l	SCRIPT(%a4),%a1
	move.l	(%a1),%d1
	beq	1f
	adda.l	%d1,%a0
	rts
1:	move.l	%d0,%a0
	rts

pm_callkb:				| callk: kernel function number, frame size
	move.l	%a0,CALLKPC(%a4)
	FETCHB	%d1
	bra	1f
pm_callkw:
	move.l	%a0,CALLKPC(%a4)
	FETCHW	%d1
1:	cmp.w	KMAX(%a4),%d1
	bgt	pm_err_kernel
	add.w	%d1,%d1
	add.w	%d1,%d1
	FETCHB	%d0
	suba.w	%d0,%a2
	move.w	REST(%a4),%d0
	suba.w	%d0,%a2
	lsr.w	#1,%d0
	add.w	%d0,(%a2)
	clr.w	REST(%a4)
	move.l	%a0,PCSAVE(%a4)
	move.l	%a2,STKSAVE(%a4)
	SYNC_OUT
	move.l	%a0,-(%sp)
	move.l	%a2,-(%sp)
	PC_TO_OFF
	move.l	%a0,-(%sp)
	move.l	%a2,-(%sp)		| the argument: -> argc, args
	lea	KTAB(%a4),%a6
	move.l	(%a6,%d1.w),%a6
	tst.l	ktrace_on
	bne	pm_callk_trace
	jsr	(%a6)
pm_callk_back:
	addq.l	#4,%sp
	move.l	(%sp)+,%a0
	move.l	(%sp)+,%a2
	move.l	(%sp)+,%d0
	subq.l	#2,%a2
	SYNC_IN
	move.l	SCRIPT(%a4),%a1
	move.l	(%a1),%d1
	beq	1f
	adda.l	%d1,%a0
	NEXT
1:	move.l	%d0,%a0
	NEXT
| KTRACE file present: log the call (shim.c c_ktrace_pre/post; d1 = number*4, a2 = args)
pm_callk_trace:
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
	bra	pm_callk_back

| ---- sends ----------------------------------------------------------------------------------
| Replaces hunk 23 +$152 (send to a3, self unchanged: self/super) and +$312 (send to an object,
| which becomes self) for sends made by bytecode; the C-level Send of hunk 23 (+$324, used by a
| few kernel functions) keeps Prog's code and runs the method through pm_entry. Prog's bookkeeping
| minus what nothing reads: the debug send stack (-$726a, hunk 1 +$d3c..$d90), SUPER (-$7132) and
| the long at -$4f3e are not maintained; the locals pointer is only switched (to the script of
| the class whose method runs) when a method is called, not while the class chain is searched;
| and the script handle, locals, PC and params are only saved once a method is actually called,
| so a send that reads or writes properties only touches none of them (pm_sendfast).
| Properties are found with the fingerprinted lookup cache (tabfind, also used by glue.S).
| pm_dosend: a1 = target object, a0 = PC at the frame byte, a2 = stack, a5 = self.
pm_send:				| send: object in acc becomes self
	moveq	#0,%d0
	move.w	%d7,%d0
	beq	1f
	add.l	HEAP(%a4),%d0
1:	move.l	%d0,%a1
	move.l	%a5,-(%sp)
	move.l	%a1,%a5
	move.l	%a5,OBJ(%a4)
	bsr	pm_dosend
	move.l	(%sp)+,%a5
	move.l	%a5,OBJ(%a4)
	NEXT
pm_self:
	move.l	%a5,%a1
	bsr	pm_dosend
	NEXT
pm_superb:				| super: class number
	FETCHB	%d1
	bra	1f
pm_superw:
	FETCHW	%d1
1:	add.w	%d1,%d1
	add.w	%d1,%d1
	move.l	CLASSTBL(%a4),%a1
	adda.w	%d1,%a1
	move.w	(%a1),%d1
	beq	3f
2:	moveq	#0,%d0
	move.w	%d1,%d0
	add.l	HEAP(%a4),%d0
	move.l	%d0,%a1
	bsr	pm_dosend
	NEXT
3:	bsr	pm_loadclass
	move.w	(%a1),%d1
	bne	2b
	bra	pm_err_class

pm_dosend:
	FETCHB	%d0
	move.w	%d0,%d3
	add.w	REST(%a4),%d3		| d3 = bytes of selectors and arguments
	move.l	%a1,%d0
	beq	pm_err_notobj
	cmpi.w	#0x1234,-10(%a1)
	bne	pm_err_notobj
	move.l	%a0,%d6			| bytecode PC
	move.l	%d2,-(%sp)		| prev survives a send, as in Prog
	move.l	%a1,-(%sp)		| the object
	move.l	%a2,%a0
	suba.w	%d3,%a0
	move.l	%a0,-(%sp)		| frame base (stack top before the frame)
	addq.l	#2,%a0
| Properties only, so far: no frame state has been saved. a0 = selector, a1 = object.
pm_sendfast:
	tst.w	%d3
	beq	pm_sendfastdone
	move.w	(%a0)+,%d4		| selector
	move.w	(%a0),%d2
	add.w	%d2,%d2
	add.w	REST(%a4),%d2
	sub.w	%d2,%d3
	subq.w	#4,%d3
	move.w	%d2,%d5			| argc with &rest
	lsr.w	#1,%d5
	move.w	%d5,(%a0)
	| property: selector list of the class, in script -4(obj) at offset (obj); count -2(obj)
	moveq	#0,%d0
	move.w	-4(%a1),%d0
	beq	1f
	add.l	HEAP(%a4),%d0
1:	move.l	%d0,%a6
	move.l	0xa(%a6),%a6
	move.l	(%a6),%a6
	adda.w	(%a1),%a6
	move.w	-2(%a1),%d2
	beq	pm_sendmethod		| (no properties: Prog would scan 65536 words)
	move.l	%a6,%d0			| index hint
	eor.w	%d4,%d0
	and.w	#0x1fe,%d0
	lea	propcache,%a1
	adda.w	%d0,%a1
	move.w	(%a1),%d0
	lsr.w	#1,%d0
	cmp.w	%d2,%d0
	bcc	2f
	add.w	%d0,%d0
	cmp.w	(%a6,%d0.w),%d4
	beq	3f
2:	move.w	%d3,%d1
	exg	%a1,%a6
	bsr	tabfind			| d3 = index or -1
	exg	%a1,%a6
	move.w	%d3,%d0
	move.w	%d1,%d3
	tst.w	%d0
	bmi	pm_sendmethod
	move.w	%d0,(%a1)
	add.w	%d0,(%a1)
	add.w	%d0,%d0
3:	move.l	4(%sp),%a1
	tst.w	%d5
	bne	4f
	move.w	(%a1,%d0.w),%d7
	bra	5f
4:	move.w	2(%a0),(%a1,%d0.w)	| first argument
5:	clr.w	REST(%a4)
	add.w	%d5,%d5
	adda.w	%d5,%a0
	addq.l	#2,%a0
	bra	pm_sendfast
pm_sendfastdone:
	move.l	(%sp)+,%a2
	addq.l	#4,%sp
	move.l	(%sp)+,%d2
	move.l	%d6,%a0
	lea	pm_tab,%a6
	rts

| A method: save what the call can change (Prog does this for every send), then the full loop.
pm_sendmethod:
	move.l	SCRIPT(%a4),-(%sp)
	move.l	LOCALS(%a4),-(%sp)
	move.l	%d6,-(%sp)
	move.l	SCRIPT(%a4),%a6
	move.l	(%a6),%a6
	move.l	%d6,%d0
	sub.l	%a6,%d0
	move.l	%d0,-(%sp)		| PC offset
	move.l	PARAMS(%a4),-(%sp)
	move.l	24(%sp),%a1		| the object
	move.l	%a0,PARAMS(%a4)
	add.w	%d5,%d5
	adda.w	%d5,%a0
	addq.l	#2,%a0
	move.w	%d3,-(%sp)
	move.l	%a0,-(%sp)
	move.l	%a1,-(%sp)
	bra	pm_sendmeth
pm_sendloop:
	tst.w	%d3
	beq	pm_senddone
	move.w	(%a0)+,%d4		| selector
	move.w	(%a0),%d2
	add.w	%d2,%d2
	add.w	REST(%a4),%d2
	sub.w	%d2,%d3
	subq.w	#4,%d3
	move.w	%d2,%d5			| argc with &rest
	lsr.w	#1,%d5
	move.w	%d5,(%a0)
	move.l	%a0,PARAMS(%a4)
	adda.w	%d2,%a0
	addq.l	#2,%a0
	move.w	%d3,-(%sp)
	move.l	%a0,-(%sp)
	move.l	%a1,-(%sp)
	moveq	#0,%d0
	move.w	-4(%a1),%d0
	beq	2f
	add.l	HEAP(%a4),%d0
2:	move.l	%d0,%a6
	move.l	0xa(%a6),%a6
	move.l	(%a6),%a6
	adda.w	(%a1),%a6
	move.w	-2(%a1),%d2
	beq	pm_sendmeth
	move.l	%a6,%d0			| index hint
	eor.w	%d4,%d0
	and.w	#0x1fe,%d0
	lea	propcache,%a0
	adda.w	%d0,%a0
	move.w	(%a0),%d3
	lsr.w	#1,%d3
	cmp.w	%d2,%d3
	bcc	3f
	add.w	%d3,%d3
	cmp.w	(%a6,%d3.w),%d4
	beq	4f
3:	move.l	%a6,%a1
	bsr	tabfind			| d3 = index or -1
	tst.w	%d3
	bmi	5f
	move.w	%d3,(%a0)
	add.w	%d3,(%a0)
	add.w	%d3,%d3
4:	move.l	(%sp),%a1
	tst.w	%d5
	bne	6f
	move.w	(%a1,%d3.w),%d7
	clr.w	REST(%a4)
	bra	pm_sendnext
6:	move.l	PARAMS(%a4),%a6
	move.w	2(%a6),(%a1,%d3.w)
	clr.w	REST(%a4)
	bra	pm_sendnext
5:	move.l	(%sp),%a1
	move.l	4(%sp),%a0
pm_sendmeth:				| method dictionaries up the class chain: a1 = object or class
	cmpi.w	#0x1234,-10(%a1)
	bne	pm_err_notobj3
	moveq	#0,%d0
	move.w	-8(%a1),%d0
	beq	1f
	add.l	HEAP(%a4),%d0
1:	move.l	%d0,%a6
	move.l	0xa(%a6),%a6
	move.l	%a6,SCRIPT(%a4)
	move.l	(%a6),%a6
	adda.w	-6(%a1),%a6		| dictionary: count at -2, selectors, a word, offsets
	move.l	%a6,%a0			| (Prog leaves the dictionary in a0; its errors report it)
	move.w	-2(%a6),%d2
	beq	pm_sendsuper
	move.w	%d2,%d3
	subq.w	#1,%d2
2:	cmp.w	(%a6)+,%d4
	dbeq	%d2,2b
	bne	pm_sendsuper
	add.w	%d3,%d3
	sub.w	%d2,%d3
	add.w	%d3,%d3
	move.w	(%a0,%d3.w),%d0		| method offset in the class's script
	move.l	SCRIPT(%a4),%a6
	move.l	(%a6),%a0
	adda.w	%d0,%a0
	bsr	pm_objlocals		| the method runs with the locals of its class's script
	move.l	TEMPS(%a4),-(%sp)
	clr.w	REST(%a4)
	lea	pm_tab,%a6
	bsr	pm_loop
	move.l	(%sp)+,TEMPS(%a4)
	bra	pm_sendnext
pm_sendsuper:
	moveq	#0,%d0
	move.w	2(%a1),%d0
	beq	pm_err_nomethod
	add.l	HEAP(%a4),%d0
	move.l	%d0,%a1
	bra	pm_sendmeth
pm_sendnext:
	move.l	(%sp)+,%a1
	move.l	(%sp)+,%a0
	move.w	(%sp)+,%d3
	bra	pm_sendloop
pm_senddone:
	move.l	(%sp)+,PARAMS(%a4)
	move.l	(%sp)+,%a0
	move.l	(%sp)+,%d0
	move.l	(%sp)+,LOCALS(%a4)
	move.l	(%sp)+,SCRIPT(%a4)
	move.l	(%sp)+,%a2
	addq.l	#4,%sp
	move.l	(%sp)+,%d2
	move.l	SCRIPT(%a4),%a6
	move.l	(%a6),%d1
	lea	pm_tab,%a6
	tst.l	%d1
	beq	1f
	adda.l	%d1,%a0
	rts
1:	move.l	%d0,%a0
	rts
pm_objlocals:				| LOCALS = locals of the script of object a1 (near pointer at -8)
	moveq	#0,%d0
	move.w	-8(%a1),%d0
	beq	1f
	add.l	HEAP(%a4),%d0
1:	move.l	%d0,%a6
	move.l	0x10(%a6),LOCALS(%a4)
	rts

pm_classb:				| class: acc = near pointer of the class object
	FETCHB	%d0
	bra	1f
pm_classw:
	FETCHW	%d0
1:	add.w	%d0,%d0
	add.w	%d0,%d0
	move.l	CLASSTBL(%a4),%a1
	adda.w	%d0,%a1
	move.w	(%a1),%d0
	beq	2f
	move.w	%d0,%d7
	NEXT
2:	bsr	pm_loadclass
	move.w	(%a1),%d0
	beq	pm_err_class
	move.w	%d0,%d7
	NEXT
| Load the script of the class whose table entry a1 points at (entry: near pointer 0, script
| number). Keeps a1; the PC is kept as an offset across the loader.
pm_loadclass:
	move.l	%a2,-(%sp)
	move.l	%a1,-(%sp)
	move.l	%a0,-(%sp)
	SYNC_OUT
	PC_TO_OFF
	move.l	%a0,-(%sp)
	move.l	8(%sp),%a1
	move.w	2(%a1),-(%sp)
	jsr	LOADCLASS(%a4)
	addq.l	#2,%sp
	move.l	(%sp)+,%a0
	move.l	(%sp)+,%d0
	move.l	(%sp)+,%a1
	move.l	(%sp)+,%a2
	move.l	SCRIPT(%a4),%a6
	move.l	(%a6),%d1
	SYNC_IN
	tst.l	%d1
	beq	1f
	adda.l	%d1,%a0
	rts
1:	move.l	%d0,%a0
	rts

| ---- selector-table lookup cache (moved from glue.S; hook_proplookup there uses it too) -------
| Property lookup in SCI send (hunk 23 +$22c): a1 = selector list, d4 = selector, a3 = values.
| A 256-entry cache maps (list, selector) to the index; a hit is used only after checking that the
| list holds the selector at that index (selectors are unique in a list, so it is then correct).
| Continues at +$23c (found; d2 = count-1-index, d3 = count) or +$25e (not found), as the original.
| Selector-table lookup cache for send's property lookup (performance, 2026-11-07; docs/GRAPHICS.md
| "Performance"): every method send first scans the object's whole property selector list (30-50
| entries) and misses; that scan was 3.9 % of all cycles. A cache for method dictionaries too
| (hunk 23 +$286) was tried and gave nothing (the tables are short).
| Property selector lists and method dictionaries are read straight from loaded script resources.
| An entry keeps the table address, selector, count and three sample selectors (first, middle,
| last); in KQ5's 190 scripts no two different tables share (count, first, middle, last)
| (tools/equiv/tabproof.py), so a matching entry describes the very table now at that address,
| even after scripts were unloaded and others loaded there. Caches "absent" too.
| tabfind: a1 = table (selector words), d2.w = count (> 0), d4.w = selector -> d3.w = index or -1.
| Word operations only on d3 (its upper half is kept); preserves everything else.
	.globl	tabfind, tabcache, propcache
tabfind:
	cmp.w	#8,%d2				| short table: a plain scan is cheaper than the cache
	bhi.s	8f
	move.l	%d1,-(%sp)
	clr.w	%d3
1:	move.w	%d3,%d1
	add.w	%d1,%d1
	cmp.w	(%a1,%d1.w),%d4
	beq.s	2f
	addq.w	#1,%d3
	cmp.w	%d2,%d3
	bne.s	1b
	move.w	#-1,%d3
2:	move.l	(%sp)+,%d1
	rts
8:	movem.l	%d0-%d1/%a0,-(%sp)
	move.l	%a1,%d0
	move.l	%d0,%d1
	lsr.l	#8,%d1
	eor.w	%d1,%d0
	eor.w	%d4,%d0
	and.w	#0x1ff,%d0
	lsl.w	#4,%d0
	lea	tabcache,%a0
	adda.w	%d0,%a0
	cmpa.l	(%a0),%a1
	bne.s	5f
	cmp.w	4(%a0),%d4
	bne.s	5f
	cmp.w	6(%a0),%d2
	bne.s	5f
	move.w	(%a1),%d1
	cmp.w	8(%a0),%d1
	bne.s	5f
	move.w	%d2,%d3
	lsr.w	#1,%d3
	add.w	%d3,%d3
	move.w	(%a1,%d3.w),%d1
	cmp.w	10(%a0),%d1
	bne.s	5f
	move.w	%d2,%d3
	add.w	%d3,%d3
	move.w	-2(%a1,%d3.w),%d1
	cmp.w	12(%a0),%d1
	bne.s	5f
	move.w	14(%a0),%d3			| hit
	movem.l	(%sp)+,%d0-%d1/%a0
	rts
5:	move.l	%a1,(%a0)			| miss: linear scan, then fill the entry
	move.w	%d4,4(%a0)
	move.w	%d2,6(%a0)
	move.w	(%a1),8(%a0)
	move.w	%d2,%d3
	lsr.w	#1,%d3
	add.w	%d3,%d3
	move.w	(%a1,%d3.w),10(%a0)
	move.w	%d2,%d3
	add.w	%d3,%d3
	move.w	-2(%a1,%d3.w),12(%a0)
	clr.w	%d3
6:	move.w	%d3,%d1
	add.w	%d1,%d1
	cmp.w	(%a1,%d1.w),%d4
	beq.s	7f
	addq.w	#1,%d3
	cmp.w	%d2,%d3
	bne.s	6b
	move.w	#-1,%d3
7:	move.w	%d3,14(%a0)
	movem.l	(%sp)+,%d0-%d1/%a0
	rts

	.bss
tabcache:	.space	512*16		| tabfind: 512 entries of 16 bytes
propcache:	.space	512		| index hints: cached index * 2 by (list ^ selector)
	.text

| ---- errors: PError(pc, stack, code, ...) in hunk 61 prints a box and exits -------------
pm_err_class:				| 3: class not loaded; a1 = table entry
	move.l	%a1,%d1
	sub.l	CLASSTBL(%a4),%d1
	lsr.w	#2,%d1
	move.w	%d1,-(%sp)
	move.w	#3,-(%sp)
	bra	pm_err
pm_err_kernel:				| 2: kernel function number out of range
	move.w	%d1,-(%sp)
	move.w	#2,-(%sp)
	bra	pm_err
pm_err_export:				| 0: export number out of range
	move.w	%d1,-(%sp)
	clr.w	-(%sp)
	bra	pm_err
pm_bad:					| 1: unknown opcode (Prog passed a table offset here)
	move.b	-1(%a0),%d1
	and.w	#0xff,%d1
	move.w	%d1,-(%sp)
	move.w	#1,-(%sp)
	subq.l	#1,%a0
	bra	pm_err
pm_err_notobj:				| 4: send to something that is not an object (a1), a0 = after the frame byte
	move.l	%a1,%d0
	beq	1f
	sub.l	HEAP(%a4),%d0
1:	move.w	%d0,-(%sp)
	move.w	#4,-(%sp)
	bra	pm_err
pm_err_notobj3:				| 4, from the class chain (Prog has switched locals to it by then)
	bsr	pm_objlocals
	bra	pm_err_notobj
pm_err_nomethod:			| 5: selector d4 not found; Prog pushes the (NULL) class too
	bsr	pm_objlocals
	move.w	%d4,-(%sp)
	clr.w	-(%sp)
	move.w	#5,-(%sp)
	bra	pm_err
pm_err_divzero:				| 7
	move.w	#7,-(%sp)
	bra	pm_err
pm_err_stack:				| 8: stack overflow
	move.w	#8,-(%sp)
pm_err:
	SYNC_OUT
	move.l	%a2,-(%sp)
	move.l	%a0,-(%sp)
	jsr	ERROR(%a4)
1:	bra	1b
