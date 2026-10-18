| 68000-safe 32-bit multiply/divide helpers for GCC (same algorithms as libgcc lb1sf68.S).

	.text
	.globl	__mulsi3, __udivsi3, __divsi3, __umodsi3, __modsi3

__mulsi3:
	move.w	4(%sp),%d0		| a.hi
	mulu.w	10(%sp),%d0		| a.hi * b.lo
	move.w	8(%sp),%d1		| b.hi
	mulu.w	6(%sp),%d1		| b.hi * a.lo
	add.w	%d1,%d0
	swap	%d0
	clr.w	%d0
	move.w	6(%sp),%d1		| a.lo
	mulu.w	10(%sp),%d1		| a.lo * b.lo
	add.l	%d1,%d0
	rts

__udivsi3:
	move.l	%d2,-(%sp)
	move.l	12(%sp),%d1		| divisor
	move.l	8(%sp),%d0		| dividend
	cmp.l	#0x10000,%d1
	bcc.s	3f
	move.l	%d0,%d2
	clr.w	%d2
	swap	%d2
	divu.w	%d1,%d2			| high quotient
	move.w	%d2,%d0
	swap	%d0
	move.w	10(%sp),%d2		| low dividend + high remainder
	divu.w	%d1,%d2
	move.w	%d2,%d0
	bra.s	6f
3:	move.l	%d1,%d2
4:	lsr.l	#1,%d1
	lsr.l	#1,%d0
	cmp.l	#0x10000,%d1
	bcc.s	4b
	divu.w	%d1,%d0
	and.l	#0xffff,%d0
	move.l	%d2,%d1
	mulu.w	%d0,%d1
	swap	%d2
	mulu.w	%d0,%d2
	swap	%d2
	tst.w	%d2
	bne.s	5f
	add.l	%d2,%d1
	bcs.s	5f
	cmp.l	8(%sp),%d1
	bls.s	6f
5:	subq.l	#1,%d0
6:	move.l	(%sp)+,%d2
	rts

__divsi3:
	move.l	%d2,-(%sp)
	moveq	#1,%d2
	move.l	12(%sp),%d1
	bpl.s	1f
	neg.l	%d1
	neg.b	%d2
1:	move.l	8(%sp),%d0
	bpl.s	2f
	neg.l	%d0
	neg.b	%d2
2:	move.l	%d1,-(%sp)
	move.l	%d0,-(%sp)
	bsr	__udivsi3
	addq.l	#8,%sp
	tst.b	%d2
	bpl.s	3f
	neg.l	%d0
3:	move.l	(%sp)+,%d2
	rts

__umodsi3:
	move.l	8(%sp),%d1
	move.l	4(%sp),%d0
	move.l	%d1,-(%sp)
	move.l	%d0,-(%sp)
	bsr	__udivsi3
	addq.l	#8,%sp
	move.l	8(%sp),%d1
	move.l	%d1,-(%sp)
	move.l	%d0,-(%sp)
	bsr	__mulsi3
	addq.l	#8,%sp
	move.l	4(%sp),%d1
	sub.l	%d0,%d1
	move.l	%d1,%d0
	rts

__modsi3:
	move.l	8(%sp),%d1
	move.l	4(%sp),%d0
	move.l	%d1,-(%sp)
	move.l	%d0,-(%sp)
	bsr	__divsi3
	addq.l	#8,%sp
	move.l	8(%sp),%d1
	move.l	%d1,-(%sp)
	move.l	%d0,-(%sp)
	bsr	__mulsi3
	addq.l	#8,%sp
	move.l	4(%sp),%d1
	sub.l	%d0,%d1
	move.l	%d1,%d0
	rts
