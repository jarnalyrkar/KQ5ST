import struct
def kn(p): return open(p, 'rb').read().split(b'\0')[:-1]
def sel(p):
    d = open(p, 'rb').read(); cnt = struct.unpack('<H', d[:2])[0] + 1; out = []
    for i in range(cnt):
        if 4 + 2*i > len(d): break
        o = struct.unpack('<H', d[2 + 2*i:4 + 2*i])[0]
        if o + 2 > len(d): out.append(None); continue
        l = struct.unpack('<H', d[o:o+2])[0]; out.append(d[o+2:o+2+l].decode('latin1'))
    return out
a = [x.decode() for x in kn('res_dos/vocab/999')]; b = [x.decode() for x in kn('res_amiga/vocab/999')]
print('kernel functions: DOS', len(a), 'Amiga', len(b))
for i in range(max(len(a), len(b))):
    x = a[i] if i < len(a) else '-'; y = b[i] if i < len(b) else '-'
    if x != y: print(f'  0x{i:02x}: DOS {x:20} Amiga {y}')
a = sel('res_dos/vocab/997'); b = sel('res_amiga/vocab/997')
d = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
print('selectors: DOS', len(a), 'Amiga', len(b), '| renumbered within common range:', len(d))
print('  first mismatches:', [(i, a[i], b[i]) for i in d[:6]])
print('  Amiga-only selectors:', b[len(a):][:60])
ks = [l.strip() for l in open(__import__('os').path.join(__import__('os').path.dirname(__file__),'kernel_selectors.txt')) if l.strip()]
ia = {n: i for i, n in enumerate(a) if n}; ib = {n: i for i, n in enumerate(b) if n}
same = moved = 0; mv = []
for n in ks:
    if n in ia and n in ib:
        if ia[n] == ib[n]: same += 1
        else: moved += 1; mv.append((n, ia[n], ib[n]))
print(f'kernel-used selectors present in both: same number {same}, renumbered {moved}')
print('  renumbered (name, DOS, Amiga):', mv)
print('  in DOS only :', [n for n in ks if n in ia and n not in ib])
print('  in Amiga only:', [n for n in ks if n in ib and n not in ia])
