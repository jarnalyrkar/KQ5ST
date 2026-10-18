# Contact sheet: Amiga original | learned EGA mapping | nearest-RGB mapping | real EGA (if any). First cel of each loop.
# viewpreview.py OUT.png VIEW [VIEW...]
import sys, os, json
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(__file__))
from sciview import decode, amiga_rgb, EGA_RGB
R = os.path.join(os.path.dirname(__file__), '..', 'extracted')
spal = open(f'{R}/amiga_files/d0/spal', 'rb').read(); pal = [amiga_rgb(spal[2*i:2*i+2]) for i in range(32)]
learned = {int(k): v for k, v in json.load(open(f'{R}/colourmap.json'))['mapping'].items()}
near = {i: min(range(16), key=lambda e: sum((pal[i][k]-EGA_RGB[e][k])**2 for k in range(3))) for i in range(32)}
S, BG = 3, (60, 60, 70)
def img(cel, colour):
    im = Image.new('RGB', (cel['w'], cel['h']), BG); p = im.load()
    for i, c in enumerate(cel['px']):
        if c != cel['key']: p[i % cel['w'], i // cel['w']] = colour(c)
    return im.resize((cel['w']*S, cel['h']*S), Image.NEAREST)
rows = []
for n in map(int, sys.argv[2:]):
    a = decode(open(f'{R}/res_amiga/view/{n}', 'rb').read(), 'amiga')
    e = decode(open(f'{R}/res_dos/view/{n}', 'rb').read(), 'ega') if os.path.exists(f'{R}/res_dos/view/{n}') else None
    for li, l in enumerate(a[:4]):
        if l['mirror'] or not l['cels']: continue
        c = l['cels'][0]
        tiles = [img(c, lambda x: pal[x]), img(c, lambda x: EGA_RGB[learned.get(x, near[x])]), img(c, lambda x: EGA_RGB[near[x]])]
        if e and li < len(e) and e[li]['cels']: tiles.append(img(e[li]['cels'][0], lambda x: EGA_RGB[x]))
        rows.append((f'view {n} loop {li}', tiles))
        if len(rows) > 400: break
W = 1100; y = 0; layout = []
for label, tiles in rows:
    h = max(t.height for t in tiles) + 16; layout.append((y, label, tiles)); y += h + 6
sheet = Image.new('RGB', (W, y + 20), (30, 30, 34)); dr = ImageDraw.Draw(sheet)
dr.text((4, y + 4), 'columns: Amiga original | learned EGA mapping | nearest RGB | real EGA art', fill=(200, 200, 200))
for yy, label, tiles in layout:
    dr.text((4, yy), label, fill=(220, 220, 220)); x = 4
    for t in tiles:
        if x + t.width > W: break
        sheet.paste(t, (x, yy + 14)); x += max(t.width, 60) + 12
sheet.save(sys.argv[1]); print('wrote', sys.argv[1], sheet.size)
