# Parse an AmigaDOS load file (hunk format). hunks.py <file> [outdir]  -> prints layout, optionally dumps hunks + relocs as JSON
import sys, struct, json, os
d = open(sys.argv[1], 'rb').read(); p = 0
def L():
    global p; v = struct.unpack('>I', d[p:p+4])[0]; p += 4; return v
NAMES = {0x3e7:'UNIT',0x3e8:'NAME',0x3e9:'CODE',0x3ea:'DATA',0x3eb:'BSS',0x3ec:'RELOC32',0x3ed:'RELOC16',0x3ee:'RELOC8',
         0x3ef:'EXT',0x3f0:'SYMBOL',0x3f1:'DEBUG',0x3f2:'END',0x3f3:'HEADER',0x3f5:'OVERLAY',0x3f6:'BREAK',0x3f7:'DREL32',0x3fc:'RELOC32SHORT'}
assert L() == 0x3f3
while L(): pass  # resident lib names
tab = L(); first = L(); last = L(); sizes = [L() for _ in range(last - first + 1)]
print('hunks', tab, 'first', first, 'last', last)
hunks = []; cur = None
while p < len(d):
    t = L(); tt = t & 0x3fffffff; n = NAMES.get(tt, hex(tt))
    if tt in (0x3e9, 0x3ea):
        sz = L() * 4; cur = {'type': n, 'size': sz, 'off': p, 'relocs': {}}; hunks.append(cur); p += sz
    elif tt == 0x3eb:
        cur = {'type': 'BSS', 'size': L() * 4, 'relocs': {}}; hunks.append(cur)
    elif tt == 0x3ec:
        while True:
            c = L()
            if not c: break
            h = L(); cur['relocs'].setdefault(h, []).extend(L() for _ in range(c))
    elif tt == 0x3fc or tt == 0x3f7:
        while True:
            c = struct.unpack('>H', d[p:p+2])[0]; p += 2
            if not c: break
            h = struct.unpack('>H', d[p:p+2])[0]; p += 2
            cur['relocs'].setdefault(h, []).extend(struct.unpack('>%dH' % c, d[p:p+2*c])); p += 2 * c
        if p & 2: p += 2
    elif tt == 0x3f0:
        while True:
            nl = L()
            if not nl: break
            nm = d[p:p+nl*4].rstrip(b'\0').decode('latin1'); p += nl * 4; cur.setdefault('symbols', []).append((nm, L()))
    elif tt == 0x3f1:
        p += L() * 4
    elif tt == 0x3f2:
        pass
    elif tt == 0x3f5:
        sz = L(); print('OVERLAY table at', p, 'size', sz); p += (sz + 1) * 4
    elif tt == 0x3f6:
        print('BREAK')
    else:
        print('unknown hunk', hex(t), 'at', p - 4); break
for i, h in enumerate(hunks):
    rel = sum(len(v) for v in h['relocs'].values())
    print(f"{i:3d} {h['type']:4} {h['size']:7d} relocs {rel:5d} -> hunks {sorted(h['relocs'])}" + (f" syms {len(h['symbols'])}" if 'symbols' in h else ''))
if len(sys.argv) > 2:
    os.makedirs(sys.argv[2], exist_ok=True)
    for i, h in enumerate(hunks):
        if 'off' in h: open(os.path.join(sys.argv[2], f'hunk{i:02d}.bin'), 'wb').write(d[h['off']:h['off']+h['size']])
    json.dump([{k: v for k, v in h.items() if k != 'off'} for h in hunks], open(os.path.join(sys.argv[2], 'hunks.json'), 'w'))
