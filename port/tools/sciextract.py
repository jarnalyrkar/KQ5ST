# Dump SCI0/SCI1-early/SCI1-late (6-byte map) resources: sciextract.py <dir with RESOURCE.MAP + vols (any subdir)> <outdir>
import sys, os, struct, glob, json
TYPES = ['view','pic','script','text','sound','memory','vocab','font','cursor','patch','bitmap','palette','cdaudio','audio','sync','message','map','heap']
src, out = sys.argv[1], sys.argv[2]
files = {}
for p in glob.glob(os.path.join(src, '**', '*'), recursive=True):
    if os.path.isfile(p): files[os.path.basename(p).lower()] = p
mapd = open(files['resource.map'], 'rb').read()
vols = {}
def vol(n):
    if n not in vols:
        p = files.get('resource.%03d' % n)
        vols[n] = open(p, 'rb').read() if p else None
    return vols[n]

class Bits:
    def __init__(s, d, pos): s.d, s.p, s.n, s.b = d, pos, 0, 0
    def byte(s):
        v = s.d[s.p] if s.p < len(s.d) else 0; s.p += 1; return v
    def msb(s, n):
        while s.n < n: s.b = (s.b << 8) | s.byte(); s.n += 8
        s.n -= n; v = (s.b >> s.n) & ((1 << n) - 1); return v

def huffman(d, usz):
    numnodes, term = d[0], d[1] | 0x100
    nodes = d[2:2 + numnodes * 2]; bits = Bits(d, 2 + numnodes * 2); outb = bytearray()
    while len(outb) < usz:
        i = 0
        while nodes[i + 1]:
            if bits.msb(1):
                nx = nodes[i + 1] & 0xF
                if nx == 0: c = bits.msb(8) | 0x100; break
            else: nx = nodes[i + 1] >> 4
            i += nx * 2
        else: c = nodes[i] | (nodes[i + 1] << 8)
        if c == term: break
        outb.append(c & 0xFF)
    return bytes(outb)

def lzw1(d, usz):
    bits = Bits(d, 0); outb = bytearray(); cbl, ts, lim = 9, 258, 511
    offs, lens = [0] * 4096, [0] * 4096
    while len(outb) < usz:
        code = bits.msb(cbl)
        if code >= ts or code == 257: break
        if code == 256: cbl, ts, lim = 9, 258, 511; continue
        ns = len(outb)
        if code <= 255: outb.append(code)
        else:
            for i in range(lens[code]): outb.append(outb[offs[code] + i])
        if ts >= 4096: continue
        if ts == lim and cbl < 12: cbl += 1; lim = (1 << cbl) - 1
        offs[ts], lens[ts] = ns, len(outb) - ns + 1; ts += 1
    return bytes(outb)

def decomp(method, data, usz):
    if method == 0: return data
    if method == 1: return huffman(data, usz)   # SCI1: 1 = Huffman
    if method == 2: return lzw1(data, usz)      # SCI1: 2 = LZW1
    return None  # 3/4: LZW1 view/pic reorder - kept raw

def parse_map(shift):
    ents = []
    for i in range(0, len(mapd) - 5, 6):
        rid, off = struct.unpack('<HI', mapd[i:i + 6])
        if off == 0xFFFFFFFF: break
        ents.append((rid >> 11, rid & 0x7FF, off >> shift, off & ((1 << shift) - 1)))
    return ents

def hdr(v, o, bytetype):
    if bytetype:
        t = v[o] & 0x7F; n, p, u, m = struct.unpack('<HHHH', v[o + 1:o + 9]); return t, n, p - 4, u, m, o + 9
    w, p, u, m = struct.unpack('<HHHH', v[o:o + 8]); return w >> 11, w & 0x7FF, p - 4, u, m, o + 8

# detect map shift + volume header style by validating headers
best = None
for shift in (26, 28):
    for bt in (False, True):
        ents = parse_map(shift); ok = 0
        for t, n, vn, off in ents:
            v = vol(vn)
            if not v or off + 9 > len(v): continue
            try:
                ht, hn, _, _, _, _ = hdr(v, off, bt)
                ok += (ht == t and hn == n)
            except Exception: pass
        if not best or ok > best[0]: best = (ok, shift, bt)
_, shift, bt = best
print('map shift', shift, 'byte-type vol headers' if bt else 'word-id vol headers')
index = {}
seen = set()
for t, n, vn, off in parse_map(shift):
    if (t, n) in seen: continue
    seen.add((t, n)); v = vol(vn)
    if not v: continue
    ht, hn, psz, usz, m, start = hdr(v, off, bt)
    data = decomp(m, v[start:start + psz], usz)
    tn = TYPES[t] if t < len(TYPES) else 't%d' % t
    os.makedirs(os.path.join(out, tn), exist_ok=True)
    ext = '' if data is not None else '.m%d' % m
    if data is None: data = v[start:start + psz]
    elif len(data) != usz: print('size mismatch', tn, n, m, len(data), usz)
    open(os.path.join(out, tn, '%d%s' % (n, ext)), 'wb').write(data)
    index['%s.%d' % (tn, n)] = {'vol': vn, 'method': m, 'packed': psz, 'unpacked': usz}
# patch files (e.g. SCRIPT.120 / 756.SCR) override volume resources
pnames = {'view':['v56'], 'pic':['p56'], 'script':['scr'], 'text':['tex'], 'sound':['snd'], 'vocab':['voc'], 'font':['fon'], 'cursor':['cur'], 'patch':['pat']}
for fn, p in files.items():
    b, _, e = fn.partition('.')
    for tn, exts in pnames.items():
        hit = (b == tn and e.isdigit()) or (e in exts and b.isdigit())
        if hit:
            n = int(e if b == tn else b); d = open(p, 'rb').read()
            body = d[2 + d[1]:] if d[0] & 0x80 else d
            os.makedirs(os.path.join(out, tn), exist_ok=True)
            open(os.path.join(out, tn, '%d' % n), 'wb').write(body)
            index['%s.%d' % (tn, n)] = {'patchfile': os.path.basename(p)}
json.dump(index, open(os.path.join(out, 'index.json'), 'w'), indent=1)
from collections import Counter
print(Counter(k.split('.')[0] for k in index))
print('methods', Counter(v.get('method', 'patch') for v in index.values()))
