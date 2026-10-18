; Toolchain smoke test: print via Hatari NatFeats (NF_STDERR) and GEMDOS, then exit.
	section	text
start:	pea	nf_name(pc)
	bsr	nf_id
	addq.l	#4,sp
	move.l	d0,d7
	beq.s	.nonf
	pea	msg(pc)
	move.l	d7,-(sp)
	bsr	nf_call
	addq.l	#8,sp
.nonf:	pea	msg(pc)
	move.w	#9,-(sp)		; Cconws
	trap	#1
	addq.l	#6,sp
	clr.w	-(sp)			; Pterm0
	trap	#1

nf_id:	dc.w	$7300			; NatFeat ID opcode
	rts
nf_call: dc.w	$7301			; NatFeat call opcode
	rts

	section data
nf_name: dc.b	"NF_STDERR",0
msg:	dc.b	"hello from the ST",13,10,0
