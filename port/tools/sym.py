# Resolve absolute addresses from a run log: sym.py SYMFILE HUNK0_ABS ADDR...
import sys, bisect
syms = sorted((int(l.split()[0], 16), l.split()[2]) for l in open(sys.argv[1]) if len(l.split()) == 3)
h0 = dict((n, a) for a, n in syms)['hunk0']; load = int(sys.argv[2], 16) - h0
addrs = [a for a, _ in syms]
for x in sys.argv[3:]:
    v = int(x, 16) - load; i = bisect.bisect_right(addrs, v) - 1
    print(f'${int(x,16):x} = {syms[i][1]}+{v - syms[i][0]:#x}')
