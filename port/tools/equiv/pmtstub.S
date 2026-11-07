| Stand-ins for the shim symbols pmachine.S references, for tools/equiv/pmtest.py only.
	.text
	.globl	ktrace_on, c_ktrace_pre, c_ktrace_post
ktrace_on:	.long	0
c_ktrace_pre:	rts
c_ktrace_post:	rts
