# Learn Amiga colour -> EGA colour correspondence from views present in both versions (same-size cels only).
# colourmap.py DOSDUMP AMIGADUMP SPAL
import os, sys, json
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from sciview import decode, amiga_rgb, EGA_RGB
D, A, spal = sys.argv[1], sys.argv[2], open(sys.argv[3], 'rb').read()
pal = [amiga_rgb(spal[2*i:2*i+2]) for i in range(32)]
co = defaultdict(Counter); used = Counter(); pairs = 0; views = 0
common = sorted({int(f) for f in os.listdir(f'{D}/view') if f.isdigit()} & {int(f) for f in os.listdir(f'{A}/view') if f.isdigit()})
for n in common:
    try:
        e = decode(open(f'{D}/view/{n}', 'rb').read(), 'ega'); a = decode(open(f'{A}/view/{n}', 'rb').read(), 'amiga')
    except Exception as ex:
        print('decode error', n, ex); continue
    got = False
    for le, la in zip(e, a):
        if le['mirror'] or la['mirror']: continue
        for ce, ca in zip(le['cels'], la['cels']):
            if (ce['w'], ce['h']) != (ca['w'], ca['h']): continue
            got = True
            for pe, pa in zip(ce['px'], ca['px']):
                if pe == ce['key'] or pa == ca['key']: continue
                co[pa][pe] += 1; pairs += 1
    views += got
    for la in a:
        for ca in la['cels']:
            for pa in ca['px']:
                if pa != ca['key']: used[pa] += 1
print(f'{views} views / {pairs} opaque pixel pairs used')
tot = sum(used.values())
print('Amiga colour usage in views: 0-15 = %.1f%%, 16-31 = %.1f%%' % (100*sum(used[i] for i in range(16))/tot, 100*sum(used[i] for i in range(16, 32))/tot))
mapping = {}
print(' idx  spal RGB        usage   best EGA (share)  runner-up')
for i in range(32):
    c = co[i]; t = sum(c.values())
    if not t: print(f'  {i:2d}  {pal[i]}  {used[i]:7d}   (no data)'); continue
    (b1, n1), *rest = c.most_common(3)
    mapping[i] = b1
    ru = ', '.join(f'{k}:{100*v/t:.0f}%' for k, v in rest)
    print(f'  {i:2d}  {str(pal[i]):14} {used[i]:7d}   {b1:2d} {str(EGA_RGB[b1]):15} {100*n1/t:4.0f}%   {ru}')
json.dump({'mapping': mapping, 'cooccurrence': {k: dict(v) for k, v in co.items()}}, open(os.path.join(os.path.dirname(A), 'colourmap.json'), 'w'), indent=1)
