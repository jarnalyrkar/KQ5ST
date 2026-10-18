"""Build the ST art set as SCI patch files (N.p32 pictures, N.v32 views) in OUTDIR.

Pictures: hybrid pictures from makepic.py (Amiga priority/control + rendered EGA visual).
Views, per resource:
  * EGA version exists with the same loop count, mirroring and cel counts, and no cel much smaller
    than the Amiga one -> EGA art
  * otherwise -> Amiga art reduced to 16 colours (egaconvert)
Both are written in the Amiga view format (cel RLE colour<<3|run, transparent skip runs),
with clear key $ff (as the Amiga views) so no 16-colour pixel can be mistaken for transparency.
Runs never cross row ends (the interpreter decodes row by row).

    makest.py OUTDIR [--report REPORT.tsv]
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
from sciview import decode, encode_amiga_rle
import egaconvert as ec
import makepic

R = os.path.join(os.path.dirname(__file__), '..', 'extracted')
KEY = 0xff

def u16(d, o): return struct.unpack('<H', d[o:o+2])[0]

def encode_rle(px, w):
    return encode_amiga_rle(px, KEY, w)

def build_view(orig, loops):
    """orig: original Amiga view bytes (for header/loop sharing); loops: decoded loops with px in 0-15/KEY."""
    nloops = orig[0]
    loop_offs = [u16(orig, 8 + 2 * l) for l in range(nloops)]
    out = bytearray(orig[:8 + 2 * nloops])
    struct.pack_into('<H', out, 6, 0)                     # no palette
    written = {}
    for l in range(nloops):
        if loop_offs[l] in written:
            struct.pack_into('<H', out, 8 + 2 * l, written[loop_offs[l]]); continue
        lo = len(out); written[loop_offs[l]] = lo
        struct.pack_into('<H', out, 8 + 2 * l, lo)
        cels = loops[l]['cels']
        unk = u16(orig, loop_offs[l] + 2)
        out += struct.pack('<HH', len(cels), unk) + b'\0\0' * len(cels)
        for c, cel in enumerate(cels):
            struct.pack_into('<H', out, lo + 4 + 2 * c, len(out))
            out += struct.pack('<HHbBBB', cel['w'], cel['h'], cel['dx'], cel['dy'], KEY, 0)
            out += encode_rle(cel['px'], cel['w'])
    if len(out) > 0xffff: raise ValueError('view too large')
    return bytes(out)

def ega_loops(e):
    for l in e:
        for c in l['cels']:
            c['px'] = bytes(KEY if p == c['key'] else p for p in c['px'])
    return e

def converted_loops(a, pal, co):
    cels = [c for l in a for c in l['cels']]
    plan = ec.plan_view(cels, pal, co)
    for l in a:
        for c in l['cels']:
            conv = ec.apply(c, plan)
            c['px'] = bytes(KEY if p == c['key'] else conv[i] for i, p in enumerate(c['px']))
    return a

def same_structure(e, a):
    return (len(e) == len(a) and [l['mirror'] for l in e] == [l['mirror'] for l in a]
            and [len(l['cels']) for l in e] == [len(l['cels']) for l in a])

# Close-up ("talker") views shown as a cycling DCIcon inside Print (script 0 proc28, script 967):
# loop 0 cel 0 is the bust, the other cels are mouth/eye frames cycled over NumCels, so a different
# cel count or smaller (transparent, displaced) EGA cels are fine. The Amiga mouth/eye cels carry
# the parchment colour 15 as an opaque background, which turns grey when converted (GRAPHICS.md).
TALKER_VIEWS = {75, 101, 102, 129, 161, 197}

# Views that fail ega_usable as a whole but where some loops match the Amiga ones (same cel count,
# sizes within the ega_usable tolerance): those loops take the EGA art, the rest stay converted.
# 354 = desert oasis (region script 15 `oasis`), loops 0-3 = sand cover (cel 0) and palms (cel 1)
# for pictures 15/16/210/other; the Amiga olive palms convert to grey/red. Loops 4-12 differ.
EGA_LOOPS = {354: {0, 1, 2, 3}}

def same_loops(e, a):
    return len(e) == len(a) and [l['mirror'] for l in e] == [l['mirror'] for l in a]

def ega_usable(e, a):
    """EGA art can replace the Amiga view: same structure and no cel much smaller. Much shorter EGA
    cels mean parts drawn separately in the DOS game (e.g. Graham's head is its own object there)."""
    if not same_structure(e, a): return False
    for le, la in zip(e, a):
        for ce, ca in zip(le['cels'], la['cels']):
            if ca['h'] - ce['h'] >= 5 or ca['w'] - ce['w'] >= 6: return False
    return True

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    report = sys.argv[sys.argv.index('--report') + 1] if '--report' in sys.argv else None
    pal, co = ec.load_model()
    rows = []
    for n in sorted(int(f) for f in os.listdir(f'{R}/res_amiga/pic')):
        if not os.path.exists(f'{R}/res_dos/pic/{n}'): continue
        try:
            data, _, _ = makepic.hybrid(open(f'{R}/res_amiga/pic/{n}', 'rb').read(), open(f'{R}/res_dos/pic/{n}', 'rb').read())
        except ValueError as ex:
            rows.append(('pic', n, 'amiga', str(ex))); continue
        open(os.path.join(out, f'{n}.p32'), 'wb').write(b'\x81\x00' + data)
        rows.append(('pic', n, 'ega-hybrid', len(data)))
    for n in sorted(int(f) for f in os.listdir(f'{R}/res_amiga/view') if f.isdigit()):
        orig = open(f'{R}/res_amiga/view/{n}', 'rb').read()
        a = decode(orig, 'amiga')
        src = 'amiga-16'
        if os.path.exists(f'{R}/res_dos/view/{n}'):
            e = decode(open(f'{R}/res_dos/view/{n}', 'rb').read(), 'ega')
            if ega_usable(e, a) or (n in TALKER_VIEWS and same_loops(e, a)): loops, src = ega_loops(e), 'ega'
            else:
                loops = converted_loops(a, pal, co)
                if n in EGA_LOOPS:
                    eg = ega_loops(e)
                    for l in EGA_LOOPS[n]: loops[l] = eg[l]
                    src = 'amiga-16+ega'
        else:
            loops = converted_loops(a, pal, co)
        data = build_view(orig, loops)
        open(os.path.join(out, f'{n}.v32'), 'wb').write(b'\x80\x00' + data)
        rows.append(('view', n, src, len(data)))
    from collections import Counter
    print(Counter((r[0], r[2]) for r in rows))
    if report:
        open(report, 'w').write('type\tnum\tsource\tsize\n' + '\n'.join('\t'.join(map(str, r)) for r in rows) + '\n')

if __name__ == '__main__':
    main()
