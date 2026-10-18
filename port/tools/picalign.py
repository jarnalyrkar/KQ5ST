# Render EGA and Amiga versions of every shared picture and measure how well their
# priority/control maps agree; write a preview sheet for selected pictures.
# picalign.py [--sheet OUT.png PIC...]
import os, sys, time
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import scipic
from sciview import amiga_rgb, EGA_RGB
R = os.path.join(os.path.dirname(__file__), '..', 'extracted')
spal = open(f'{R}/amiga_files/d0/spal', 'rb').read()
CTL_RGB = [(0, 0, 0)] + [tuple(int(v) for v in ((i * 97) % 255, (i * 53 + 80) % 255, (i * 191 + 40) % 255)) for i in range(1, 16)]

def amiga_palette(pic):
    pal = [amiga_rgb(spal[2*i:2*i+2]) for i in range(32)]
    for blk in pic.palette_ops:
        for i in range(16): pal[i] = amiga_rgb(blk[2*i:2*i+2])
    return pal

def compare(e, a):
    n = scipic.W * scipic.H
    ctl = sum(1 for i in range(n) if e.ctl[i] == a.ctl[i]) / n
    pri = sum(1 for i in range(n) if e.pri[i] == a.pri[i]) / n
    # walkable/blocked agreement on pixels where either has a control line
    used = [i for i in range(n) if e.ctl[i] or a.ctl[i]]
    ctl_used = sum(1 for i in used if e.ctl[i] == a.ctl[i]) / len(used) if used else 1.0
    return ctl, ctl_used, pri

def sheet(out, nums):
    from PIL import Image, ImageDraw
    S = 2; W, H = scipic.W, scipic.H
    tiles = []
    for n in nums:
        e = scipic.render(open(f'{R}/res_dos/pic/{n}', 'rb').read(), True)
        a = scipic.render(open(f'{R}/res_amiga/pic/{n}', 'rb').read(), False)
        apal = amiga_palette(a)
        ims = []
        for name, fn in (('EGA visual', lambda i: EGA_RGB[e.vis[i]]),
                         ('Amiga visual', lambda i: apal[a.vis[i]] if a.vis[i] < 32 else (255, 255, 255)),
                         ('EGA control', lambda i: CTL_RGB[e.ctl[i]]),
                         ('Amiga control', lambda i: CTL_RGB[a.ctl[i]]),
                         ('EGA visual + Amiga control', lambda i: tuple((EGA_RGB[e.vis[i]][k] + 2 * CTL_RGB[a.ctl[i]][k]) // 3 for k in range(3)) if a.ctl[i] else EGA_RGB[e.vis[i]]),
                         ('EGA visual + Amiga priority', lambda i: tuple((EGA_RGB[e.vis[i]][k] + CTL_RGB[a.pri[i]][k]) // 2 for k in range(3)))):
            im = Image.new('RGB', (W, H)); im.putdata([fn(i) for i in range(W * H)])
            ims.append((name, im.resize((W * S, H * S), Image.NEAREST)))
        tiles.append((n, ims, compare(e, a)))
    cols = 2; tw, th = W * S + 10, H * S + 18
    sh = Image.new('RGB', (cols * tw, len(tiles) * 3 * th + 10), (30, 30, 34)); dr = ImageDraw.Draw(sh)
    for r, (n, ims, (c, cu, p)) in enumerate(tiles):
        for j, (name, im) in enumerate(ims):
            x, y = (j % cols) * tw, (r * 3 + j // cols) * th
            dr.text((x + 4, y + 2), f'pic {n}: {name}' + (f'   control agree {100*cu:.1f}% / priority {100*p:.1f}%' if j == 0 else ''), fill=(220, 220, 220))
            sh.paste(im, (x + 4, y + 16))
    sh.save(out); print('wrote', out, sh.size)

if __name__ == '__main__':
    if '--sheet' in sys.argv:
        i = sys.argv.index('--sheet'); sheet(sys.argv[i + 1], [int(x) for x in sys.argv[i + 2:]]); sys.exit()
    common = sorted({int(f) for f in os.listdir(f'{R}/res_dos/pic')} & {int(f) for f in os.listdir(f'{R}/res_amiga/pic')})
    t0 = time.time(); rows = []; ops = Counter(); errors = []
    for n in common:
        try:
            e = scipic.render(open(f'{R}/res_dos/pic/{n}', 'rb').read(), True)
            a = scipic.render(open(f'{R}/res_amiga/pic/{n}', 'rb').read(), False)
        except Exception as ex:
            errors.append((n, repr(ex))); continue
        ops.update({f'{k:#x}': v for k, v in a.ops.items() if k >= 0xFE00})
        c, cu, p = compare(e, a); rows.append((n, c, cu, p, len(a.palette_ops), len(a.embedded)))
    print(f'rendered {len(rows)} picture pairs in {time.time() - t0:.0f}s; errors: {errors}')
    print('Amiga FE sub-op usage:', dict(ops))
    import statistics as st
    print('control map agreement (all pixels): median %.1f%%' % (100 * st.median(r[1] for r in rows)))
    print('control agreement on control-line pixels: median %.1f%%, worst 10: %s' % (100 * st.median(r[2] for r in rows), [(r[0], round(100 * r[2])) for r in sorted(rows, key=lambda r: r[2])[:10]]))
    print('priority map agreement: median %.1f%%, worst 10: %s' % (100 * st.median(r[3] for r in rows), [(r[0], round(100 * r[3])) for r in sorted(rows, key=lambda r: r[3])[:10]]))
    print('pictures with Amiga palette blocks:', sum(1 for r in rows if r[4]), '| with embedded cels:', sum(1 for r in rows if r[5]))
    open(os.path.join(R, 'picalign.tsv'), 'w').write('pic\tctl_all\tctl_lines\tpri\tamiga_palettes\tamiga_embedded\n' + '\n'.join('\t'.join(str(round(v, 4)) if isinstance(v, float) else str(v) for v in r) for r in rows) + '\n')
