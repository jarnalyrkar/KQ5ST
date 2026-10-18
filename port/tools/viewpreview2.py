# Contact sheet: Amiga original | global mapping | dithered + per-view contrast | real EGA (if any)
# viewpreview2.py OUT.png VIEW [VIEW...]
import sys, os
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(__file__))
from sciview import decode, EGA_RGB
import egaconvert as ec
R = os.path.join(os.path.dirname(__file__), '..', 'extracted')
pal, co = ec.load_model()
S, BG = 3, (60, 60, 70)
def img(w, h, px, key, colour):
    im = Image.new('RGB', (w, h), BG); p = im.load()
    for i, c in enumerate(px):
        if c != key: p[i % w, i // w] = colour(c)
    return im.resize((w * S, h * S), Image.NEAREST)
rows = []
for n in map(int, sys.argv[2:]):
    a = decode(open(f'{R}/res_amiga/view/{n}', 'rb').read(), 'amiga')
    e = decode(open(f'{R}/res_dos/view/{n}', 'rb').read(), 'ega') if os.path.exists(f'{R}/res_dos/view/{n}') else None
    cels = [c for l in a for c in l['cels']]
    glob = ec.plan_view(cels, pal, co, pairs=False, decollide=False)
    full = ec.plan_view(cels, pal, co)
    for li, l in enumerate(a[:4]):
        if l['mirror'] or not l['cels']: continue
        c = l['cels'][0]
        if c['w'] * c['h'] < 30: continue
        t = [img(c['w'], c['h'], c['px'], c['key'], lambda x: pal[x]),
             img(c['w'], c['h'], ec.apply(c, glob), c['key'], lambda x: EGA_RGB[x]),
             img(c['w'], c['h'], ec.apply(c, full), c['key'], lambda x: EGA_RGB[x])]
        if e and li < len(e) and e[li]['cels']:
            ce = e[li]['cels'][0]; t.append(img(ce['w'], ce['h'], ce['px'], ce['key'], lambda x: EGA_RGB[x]))
        rows.append((f'view {n} loop {li}', t))
W = 1100; y = 0; lay = []
for lab, t in rows:
    lay.append((y, lab, t)); y += max(x.height for x in t) + 22
sh = Image.new('RGB', (W, y + 20), (30, 30, 34)); dr = ImageDraw.Draw(sh)
dr.text((4, y + 4), 'columns: Amiga original | global mapping | dithered + per-view contrast | real EGA art', fill=(200, 200, 200))
for yy, lab, t in lay:
    dr.text((4, yy), lab, fill=(220, 220, 220)); x = 4
    for im in t:
        if x + im.width > W: break
        sh.paste(im, (x, yy + 14)); x += max(im.width, 60) + 12
sh.save(sys.argv[1]); print('wrote', sys.argv[1], sh.size)
