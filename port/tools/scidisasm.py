#!/usr/bin/env python3
"""Disassemble an SCI0/SCI1 script resource: scidisasm.py <res dir> <script no> [method-name-filter]
Prints the objects/classes (with property values) and the bytecode of every method and
exported procedure. Selector names from vocab.997, kernel names from vocab.999."""
import sys, os, struct
res, num = sys.argv[1], sys.argv[2]
filt = sys.argv[3] if len(sys.argv) > 3 else None
d = open(os.path.join(res, 'script', num), 'rb').read()
def words(b): return [struct.unpack('<H', b[i:i+2])[0] for i in range(0, len(b) - 1, 2)]
v = open(os.path.join(res, 'vocab', '997'), 'rb').read()
n = struct.unpack('<H', v[:2])[0] + 1
SEL = []
for i in range(n):
    off = struct.unpack('<H', v[2+2*i:4+2*i])[0]; l = struct.unpack('<H', v[off:off+2])[0]
    SEL.append(v[off+2:off+2+l].decode('latin1'))
KERN = [s.decode('latin1') for s in open(os.path.join(res, 'vocab', '999'), 'rb').read().split(b'\0')]
def sel(i): return SEL[i] if i < len(SEL) else '?%d' % i
OPS = ['bnot','add','sub','mul','div','mod','shr','shl','xor','and','or','neg','not','eq?','ne?','gt?',
 'ge?','lt?','le?','ugt?','uge?','ult?','ule?','bt','bnt','jmp','ldi','push','pushi','toss','dup','link',
 'call','callk','callb','calle','ret','send','?26','?27','class','?29','self','super','&rest','lea','selfID',
 '?2f','pprev','pToa','aTop','pTos','sTop','ipToa','dpToa','ipTos','dpTos','lofsa','lofss','push0','push1',
 'push2','pushSelf','line']
LS = []
for pre in ['l', 's', '+', '-']:
    for ix in ['', 'i']:
        for kind in ['a', 's']:
            for var in 'gltp': LS.append(pre + kind + var + ix)
# order: lag lal lat lap lsg lsl lst lsp lagi lali lati lapi lsgi lsli lsti lspi sag ... +ag ... -ag ...
def opname(op):
    o = op >> 1
    return OPS[o] if o < 0x40 else LS[o - 0x40]

# blocks
blocks = []; p = 0; strings = {}
while p + 4 <= len(d):
    t, sz = struct.unpack('<HH', d[p:p+4])
    if t == 0: break
    blocks.append((t, p + 4, sz - 4)); p += sz
exports = []; objs = []
for t, off, sz in blocks:
    if t == 7:
        cnt = struct.unpack('<H', d[off:off+2])[0]
        exports = words(d[off+2:off+2+cnt*2])
    if t in (1, 6):
        magic, locofs, fsel = struct.unpack('<HHH', d[off:off+6])
        nvars = struct.unpack('<H', d[off+6:off+8])[0]
        vals = words(d[off+8:off+8+nvars*2])
        vnames = words(d[off+8+nvars*2:off+8+nvars*4]) if t == 6 else None
        q = off + 6 + fsel   # method selector count (fsel is relative to the nvars field)
        nmeth = struct.unpack('<H', d[q:q+2])[0]
        msel = words(d[q+2:q+2+nmeth*2]); mofs = words(d[q+4+nmeth*2:q+4+nmeth*4])
        objs.append((t, off, vals, vnames, list(zip(msel, mofs))))
def cstr(o):
    e = d.find(b'\0', o); return d[o:e].decode('latin1', 'replace')
def objname(vals):
    return cstr(vals[3]) if len(vals) > 3 and 0 < vals[3] < len(d) else '?'
classnames = {}
def disasm(start, label):
    print('  %s @ %04x' % (label, start)); pc = start
    while pc < len(d):
        op = d[pc]; nm = opname(op); b = op & 1; a = pc + 1; args = []
        o = op >> 1
        def w():
            nonlocal a
            if b: v = d[a]; a += 1
            else: v = struct.unpack('<H', d[a:a+2])[0]; a += 2
            return v
        def sb():
            nonlocal a
            if b: v = struct.unpack('<b', d[a:a+1])[0]; a += 1
            else: v = struct.unpack('<h', d[a:a+2])[0]; a += 2
            return v
        txt = nm
        if nm in ('bt', 'bnt', 'jmp'): off = sb(); txt += ' %04x' % (a + off)
        elif nm in ('ldi', 'pushi'):
            v = w(); txt += ' %d' % (v if v < 0x8000 else v - 0x10000)
            if nm == 'pushi' and v < len(SEL): txt += ' ; %s' % sel(v)
        elif nm == 'link': txt += ' %d' % w()
        elif nm == 'call': off = sb(); nargs = d[a]; a += 1; txt += ' %04x %d' % (a + off, nargs)
        elif nm == 'callk': k = w(); nargs = d[a]; a += 1; txt += ' %s %d' % (KERN[k] if k < len(KERN) else k, nargs)
        elif nm == 'callb': k = w(); nargs = d[a]; a += 1; txt += ' proc%d %d' % (k, nargs)
        elif nm == 'calle': s = w(); k = w(); nargs = d[a]; a += 1; txt += ' script%d proc%d %d' % (s, k, nargs)
        elif nm in ('send', 'self'): txt += ' %d' % d[a]; a += 1
        elif nm == 'class': c = w(); txt += ' %d' % c
        elif nm == 'super': c = w(); nargs = d[a]; a += 1; txt += ' %d %d' % (c, nargs)
        elif nm == '&rest': txt += ' %d' % w()
        elif nm == 'lea': t1 = w(); t2 = w(); txt += ' %d %d' % (t1, t2)
        elif nm in ('pToa', 'aTop', 'pTos', 'sTop', 'ipToa', 'dpToa', 'ipTos', 'dpTos'):
            v = w(); txt += ' %d' % v
        elif nm in ('lofsa', 'lofss'):
            v = struct.unpack('<H', d[a:a+2])[0]; a += 2; txt += ' %04x' % v
            if v < len(d): txt += ' ; "%s"' % cstr(v)[:30]
        elif o >= 0x40: txt += ' %d' % w()
        print('    %04x: %-24s %s' % (pc, d[pc:a].hex(), txt)); pc = a
        if nm == 'ret' and pc >= end: break
    print()
# print objects
for t, off, vals, vnames, meths in objs:
    nm = objname(vals)
    print('%s %s @ %04x  species %d super %d' % ('class' if t == 6 else 'object', nm, off, vals[0], vals[1]))
    if vnames:
        for s, v in zip(vnames, vals): print('    %s = %d (%04x)' % (sel(s), v, v))
    else:
        print('    props:', ' '.join('%04x' % v for v in vals))
    for s, mo in meths:
        if filt and filt not in sel(s): continue
        # end = next method start or end of code
        ends = sorted(set([m for _, m in sum([o[4] for o in objs], [])] + exports + [len(d)]))
        end = min([e for e in ends if e > mo] + [len(d)])
        disasm(mo, '%s::%s' % (nm, sel(s)))
if filt and filt.startswith('@'):           # scidisasm.py res N @hexoffset: code at an arbitrary offset
    end = len(d); disasm(int(filt[1:], 16), 'code')
for i, e in enumerate(exports):
    if e and (not filt or filt == 'proc'):
        ends = sorted(set([m for _, m in sum([o[4] for o in objs], [])] + exports + [len(d)]))
        end = min([x for x in ends if x > e] + [len(d)])
        disasm(e, 'export %d' % i)
