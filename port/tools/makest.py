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

# Per-view colour choices that override the learned mapping: {view: {amiga_colour: (ega_a, ega_b)}}.
# 946 = pause/settings panel (script 755 KQ5Controls): the Amiga gold 13 (bevels, slider frames,
# title letters) maps to EGA yellow 14, which glared on the grey window (player report 2026-11-07);
# brown 6 keeps the Amiga's single warm tone with the brown buttons.
COLOUR_OVERRIDES = {946: {13: (6, 6)}}

# Cels redrawn as text: {view: {(loop, cel): (text, pad)}}. 946 loop 0 cels 2-5 = the panel titles
# (Amiga: 2-pixel strokes with a gold outline, unreadable in 16 colours; user, 2026-11-07). Redrawn
# in black capitals of font 69 (the score line's font) on grey 7, as opaque as the originals and
# with the original height 9 (script 755 places them bottom-up by CelHigh). `pad` grey columns on
# each side of the old width: SPEED/DETAIL are drawn at fixed x, so makescr.py moves them left by
# `pad` (755 PATCHES); GAME PAUSED is centred by its CelWide, VOLUME's text has the old width.
TEXT_CELS = {946: {(0, 2): ('SPEED', 1), (0, 3): ('VOLUME', 0), (0, 4): ('DETAIL', 2),
                   (0, 5): ('GAME PAUSED', 2)}}
TEXT_FONT, TEXT_FG, TEXT_BG = 69, 0, 7

def font_text(text):
    """Rows of 0/1 for text in SCI font TEXT_FONT (Amiga resource), blank edge columns trimmed."""
    d = open(f'{R}/res_amiga/font/{TEXT_FONT}', 'rb').read()
    n, h = struct.unpack('<HH', d[2:6]); rows = [[] for _ in range(h)]
    for ch in text.encode('latin1'):
        o = u16(d, 6 + 2 * ch); w, gh = d[o], d[o + 1]; bw = (w + 7) // 8
        for y in range(h):
            b = d[o + 2 + y * bw:o + 2 + (y + 1) * bw] if y < gh else bytes(bw)
            rows[y] += [(b[x // 8] >> (7 - x % 8)) & 1 for x in range(w)]
    used = [x for x in range(len(rows[0])) if any(r[x] for r in rows)]
    return [r[used[0]:used[-1] + 1] for r in rows]

def text_cel(c, text, pad):
    """Replace cel c's pixels with text, keeping its height; width = old width + 2 * pad."""
    t = font_text(text)
    assert not any(any(r) for r in t[8:]), text        # capitals only: nothing below the baseline
    w = c['w'] + 2 * pad; h = c['h']; tw = len(t[0])
    if tw > w: raise ValueError(f'{text!r} ({tw} px) wider than its cel ({w})')
    x0 = (w - tw + 1) // 2; y0 = h - 8   # odd spare column goes left: DETAIL then centres on its slot
    px = bytearray([TEXT_BG] * (w * h))
    for y in range(8):
        for x in range(tw):
            if t[y][x]: px[(y0 + y) * w + x0 + x] = TEXT_FG
    c.update(w=w, px=bytes(px), dx=c['dx'] + pad)

def converted_loops(a, pal, co, n=None):
    cels = [c for l in a for c in l['cels']]
    plan = ec.plan_view(cels, pal, co)
    plan.update(COLOUR_OVERRIDES.get(n, {}))
    for li, l in enumerate(a):
        for ci, c in enumerate(l['cels']):
            if (li, ci) in TEXT_CELS.get(n, {}):
                text_cel(c, *TEXT_CELS[n][(li, ci)]); continue
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

# Views drawn over (or next to) EGA art that fail ega_usable only on cel counts or sizes; the
# converted Amiga cels clash with the EGA picture or with the character's other, EGA views
# (player report 2026-11-07, GRAPHICS.md "Overlay faces and the beast's slip"). The DOS scripts
# place them at the same x/y, so the EGA cels line up. 844 = harpy eyes/mouths (room 91),
# 860 = Cassima/Graham faces and locket (room 96), 894/906 = the blue beast slipping on the peas
# (castle region 550; its walk view 884/898 is EGA).
# Added 2026-11-07 after piccomp.py composites (EGA picture + cels at the script positions):
# 298 queen bee (room 11), 368 horses (214), 761/763 Graham and Cedric in the intro (70/71),
# 773 Crispin (intro9, pic 1), 776/778 Madame Mushka and her crystal ball (77), 848/852 ice queen
# (92/93), 933/934/936 ending scenes (65/68/218). Where an EGA loop has fewer cels the scripts
# only cycle it (End/Beg/Fwd/RandCycle, cel 0 or NumCels).
OVERLAY_VIEWS = {844, 860, 894, 906,
                 298, 368, 761, 763, 773, 776, 778, 848, 852, 933, 934, 936}

# Views that fail ega_usable as a whole but where some loops match the Amiga ones (same cel count,
# sizes within the ega_usable tolerance): those loops take the EGA art, the rest stay converted.
# 354 = desert oasis (region script 15 `oasis`), loops 0-3 = sand cover (cel 0) and palms (cel 1)
# for pictures 15/16/210/other; the Amiga olive palms convert to grey/red. Loops 4-12 differ.
EGA_LOOPS = {354: {0, 1, 2, 3}}

# Views left out of the art set (no N.v32 written, a stale one removed). ScummVM determines the
# view format from the first view 0-999 that is not a patch file (engines/sci/resource/resource.cpp
# detectViewType) and refuses to start when every view is patched ("Unknown view type"). 947 is a
# DOS leftover in the Amiga release: DOS script 753 (help) shows it, the Amiga 753 uses 942
# instead, and no Amiga script pushes 947 or holds it in a property, so Prog never draws it.
UNPATCHED_VIEWS = {947}

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

# The game's Amiga palette file. Prog on the ST ignores its values (st/src/display.c always loads
# the EGA palette), but ScummVM colours Amiga KQ5 from it (engines/sci/graphics/palette16.cpp
# setAmiga): 32 big-endian 0RGB words. Colours 0-15 become the EGA palette, so the ST art set shows
# right there too; 16-31 stay Amiga (nothing in the art set uses them). Original:
# extracted/amiga_files/d0/spal.
EGA_SPAL = [0x000, 0x00a, 0x0a0, 0x0aa, 0xa00, 0xa0a, 0xa50, 0xaaa,
            0x555, 0x55f, 0x5f5, 0x5ff, 0xf55, 0xf5f, 0xff5, 0xfff]

def write_spal(out):
    orig = open(f'{R}/amiga_files/d0/spal', 'rb').read()
    data = b''.join(struct.pack('>H', c) for c in EGA_SPAL) + orig[32:]
    open(os.path.join(out, 'spal'), 'wb').write(data)

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
        if n in UNPATCHED_VIEWS:
            stale = os.path.join(out, f'{n}.v32')
            if os.path.exists(stale): os.remove(stale)
            rows.append(('view', n, 'unpatched', 0)); continue
        orig = open(f'{R}/res_amiga/view/{n}', 'rb').read()
        a = decode(orig, 'amiga')
        src = 'amiga-16'
        if os.path.exists(f'{R}/res_dos/view/{n}'):
            e = decode(open(f'{R}/res_dos/view/{n}', 'rb').read(), 'ega')
            if ega_usable(e, a) or (n in TALKER_VIEWS | OVERLAY_VIEWS and same_loops(e, a)): loops, src = ega_loops(e), 'ega'
            else:
                loops = converted_loops(a, pal, co, n)
                if n in EGA_LOOPS:
                    eg = ega_loops(e)
                    for l in EGA_LOOPS[n]: loops[l] = eg[l]
                    src = 'amiga-16+ega'
        else:
            loops = converted_loops(a, pal, co, n)
        data = build_view(orig, loops)
        open(os.path.join(out, f'{n}.v32'), 'wb').write(b'\x80\x00' + data)
        rows.append(('view', n, src, len(data)))
    write_spal(out)
    from collections import Counter
    print(Counter((r[0], r[2]) for r in rows))
    if report:
        open(report, 'w').write('type\tnum\tsource\tsize\n' + '\n'.join('\t'.join(map(str, r)) for r in rows) + '\n')

if __name__ == '__main__':
    main()
