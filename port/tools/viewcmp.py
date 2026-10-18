# Compare view structure (loops, mirroring, cel counts, sizes, displacement) between two resource dumps.
# viewcmp.py DUMP_A DUMP_B [-v]
import os, sys, struct
from collections import Counter
def parse(p):
    d = open(p, 'rb').read(); u16 = lambda o: struct.unpack('<H', d[o:o+2])[0]
    nl = d[0]; mirror = u16(2); loops = []
    for l in range(nl):
        lo = u16(8 + 2*l); cc = u16(lo); cels = []
        for c in range(cc):
            co = u16(lo + 4 + 2*c)
            cels.append((u16(co), u16(co+2), struct.unpack('b', d[co+4:co+5])[0], d[co+5], d[co+6]))
        loops.append(((mirror >> l) & 1, lo if (mirror >> l) & 1 else None, cels))
    return loops
A, B = sys.argv[1], sys.argv[2]; verbose = '-v' in sys.argv
na = {int(f) for f in os.listdir(f'{A}/view') if f.isdigit()}; nb = {int(f) for f in os.listdir(f'{B}/view') if f.isdigit()}
stats = Counter(); bad = []
for n in sorted(na & nb):
    a, b = parse(f'{A}/view/{n}'), parse(f'{B}/view/{n}')
    if len(a) != len(b): stats['loop count differs'] += 1; bad.append((n, 'loops', len(a), len(b))); continue
    if [x[0] for x in a] != [x[0] for x in b]: stats['mirror flags differ'] += 1; bad.append((n, 'mirror')); continue
    ca = [len(x[2]) for x in a]; cb = [len(x[2]) for x in b]
    if ca != cb: stats['cel counts differ'] += 1; bad.append((n, 'cels', ca, cb)); continue
    pa = [c for x in a for c in x[2]]; pb = [c for x in b for c in x[2]]
    if [c[:2] for c in pa] != [c[:2] for c in pb]: stats['cel sizes differ'] += 1; bad.append((n, 'size', [(x[:2], y[:2]) for x, y in zip(pa, pb) if x[:2] != y[:2]][:3])); continue
    if [c[2:4] for c in pa] != [c[2:4] for c in pb]: stats['displacement differs'] += 1; bad.append((n, 'disp')); continue
    stats['structurally identical'] += 1
print(f'common views: {len(na & nb)}', dict(stats))
print('only in', A, sorted(na - nb)); print('only in', B, sorted(nb - na))
if verbose:
    for b in bad: print(' ', b)
