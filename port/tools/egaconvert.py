"""Convert Amiga 32-colour view pixels to the 16 EGA colours, guided by Sierra's own EGA art.

Model (learned in colourmap.py from views present in both releases):
  P(ega | amiga) co-occurrence counts.
Per view:
  1. every Amiga colour starts on its best solid EGA colour (learned probability + RGB closeness);
  2. greedy de-collision: Amiga colours that are often neighbours in this view but land on the
     same output get split; the rarer colour moves to its next candidate, which may be an
     EGA checkerboard pair (a, b). Dithering is therefore only used to keep shades apart.
Output pixel for a pair (a, b) = a on even (x+y), b on odd.
"""
import json, os, math
from collections import Counter
from sciview import amiga_rgb, EGA_RGB

_R = os.path.join(os.path.dirname(__file__), '..', 'extracted')

def load_model(spal_path=f'{_R}/amiga_files/d0/spal', cmap_path=f'{_R}/colourmap.json'):
    spal = open(spal_path, 'rb').read(); pal = [amiga_rgb(spal[2*i:2*i+2]) for i in range(32)]
    co = {int(k): {int(a): b for a, b in v.items()} for k, v in json.load(open(cmap_path))['cooccurrence'].items()}
    return pal, co

def _dist(c1, c2): return math.sqrt(sum((c1[k] - c2[k]) ** 2 for k in range(3))) / 441.7

def candidates(i, pal, co, pairs=True):
    c = co.get(i, {}); t = sum(c.values()) or 1
    share = {e: c.get(e, 0) / t for e in range(16)}
    out = []
    for e in range(16):
        out.append(((e, e), share[e] - 0.6 * _dist(pal[i], EGA_RGB[e])))
    if pairs:
        for a in range(16):
            for b in range(a + 1, 16):
                if share[a] < 0.15 or share[b] < 0.15: continue
                mix = tuple((EGA_RGB[a][k] + EGA_RGB[b][k]) / 2 for k in range(3))
                if _dist(pal[i], mix) >= min(_dist(pal[i], EGA_RGB[a]), _dist(pal[i], EGA_RGB[b])): continue
                out.append(((a, b), share[a] + share[b] - 0.6 * _dist(pal[i], mix) - 0.15))
    return sorted(out, key=lambda x: -x[1])

def _rgb_of(choice):
    a, b = choice; return tuple((EGA_RGB[a][k] + EGA_RGB[b][k]) / 2 for k in range(3))

def plan_view(cels, pal, co, pairs=True, decollide=True):
    """cels: list of decoded cels (dict w,h,key,px). Returns {amiga_colour: (ega_a, ega_b)}."""
    use = Counter(); adj = Counter()
    for c in cels:
        w, px, key = c['w'], c['px'], c['key']
        for i, p in enumerate(px):
            if p == key: continue
            use[p] += 1
            for j in (i + 1, i + w):
                if (j < len(px)) and (j != i + 1 or j % w) and px[j] != key and px[j] != p:
                    adj[tuple(sorted((p, px[j])))] += 1
    cand = {i: candidates(i, pal, co, pairs) for i in use}
    choice = {i: next(ch for ch, _ in cand[i] if ch[0] == ch[1]) for i in use}
    if decollide:
        for _ in range(3):
            changed = False
            for (x, y), n in adj.most_common():
                if n < 8 or choice[x] != choice[y] or _dist(pal[x], pal[y]) < 0.12: continue
                lo = x if use[x] < use[y] else y  # move the rarer colour
                taken = choice[x]
                for ch, sc in cand[lo][1:]:
                    if ch != taken and _dist(_rgb_of(ch), _rgb_of(taken)) > 0.1:
                        choice[lo] = ch; changed = True; break
            if not changed: break
    return choice

def apply(cel, choice):
    """Return converted pixel bytes (EGA indices, transparent stays the cel's key)."""
    w, key = cel['w'], cel['key']; out = bytearray(len(cel['px']))
    for i, p in enumerate(cel['px']):
        if p == key: out[i] = key; continue
        a, b = choice[p]; out[i] = a if ((i % w) + (i // w)) & 1 == 0 else b
    return bytes(out)
