# Build hybrid pictures: Amiga picture (priority/control vectors, priority bands) with its embedded
# visual bitmap replaced by the rendered DOS EGA picture (colours 0-15, Amiga cel RLE).
# makepic.py OUTDIR            -> OUTDIR/<n> raw picture resources + report
import os, sys, struct
sys.path.insert(0, os.path.dirname(__file__))
import scipic
from sciview import encode_amiga_rle
R = os.path.join(os.path.dirname(__file__), '..', 'extracted')

def hybrid(amiga_data, ega_data):
    a = scipic.render(amiga_data, False)
    if len(a.cel_blocks) != 1: raise ValueError(f'{len(a.cel_blocks)} embedded cels')
    op_at, hdr, size = a.cel_blocks[0]
    w, h = struct.unpack('<HH', amiga_data[hdr:hdr+4])
    x, y = a.embedded[0][:2]
    if (x, y, w, h) != (0, 0, scipic.W, scipic.H): raise ValueError(f'cel geometry {(x, y, w, h)}')
    e = scipic.render(ega_data, True)
    header = bytearray(amiga_data[hdr:hdr+8]); header[6] = 255   # clear key: no EGA pixel is 255
    cel = bytes(header) + encode_amiga_rle(bytes(e.vis), 255, scipic.W)
    if len(cel) > 0xFFFF: raise ValueError('cel too large')
    head = amiga_data[:hdr - 2] + struct.pack('<H', len(cel)) + cel
    return head + strip_visual(amiga_data, a, hdr + size), a, e

LINES_PATTERNS = (0xF4, 0xF5, 0xF6, 0xF7, 0xFA, 0xFD)

def strip_visual(d, a, start):
    """Re-emit the ops after the embedded cel so lines/patterns never touch the visual screen,
    while fills keep the original colour state (a visual fill over a bitmap aborts in SCI)."""
    starts = [p for p in a.op_starts if p >= start] + [len(d)]
    out = bytearray(); colour = None   # None = visual disabled, else F0 operand
    for p in a.op_starts:              # colour state in effect when the embedded cel is drawn
        if p >= start: break
        if d[p] == 0xF0: colour = d[p + 1]
        elif d[p] == 0xF1: colour = None
    for p, q in zip(starts, starts[1:]):
        op = d[p]
        if op == 0xF0: colour = d[p + 1]; continue
        if op == 0xF1: colour = None; continue
        if op in LINES_PATTERNS: out += b'\xf1'
        elif op == 0xF8: out += (b'\xf0' + bytes([colour])) if colour is not None else b'\xf1'
        out += d[p:q]
    return bytes(out)

if __name__ == '__main__':
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); ok = bad = 0; problems = []
    for n in sorted(int(f) for f in os.listdir(f'{R}/res_amiga/pic')):
        if not os.path.exists(f'{R}/res_dos/pic/{n}'): problems.append((n, 'no EGA version')); continue
        try:
            data, a, e = hybrid(open(f'{R}/res_amiga/pic/{n}', 'rb').read(), open(f'{R}/res_dos/pic/{n}', 'rb').read())
        except ValueError as ex:
            problems.append((n, str(ex))); bad += 1; continue
        chk = scipic.render(data, False)   # verify: visual = EGA, priority/control = Amiga
        # pixels the original Amiga cel could not paint (priority already set) stay unpainted
        assert all(c == v or (c == 255 and o == 255) for c, v, o in zip(chk.vis, e.vis, a.vis)), n
        assert bytes(chk.pri) == bytes(a.pri) and bytes(chk.ctl) == bytes(a.ctl), n
        open(os.path.join(out, str(n)), 'wb').write(data); ok += 1
    print(f'hybrid pictures written: {ok}; skipped: {problems}')
