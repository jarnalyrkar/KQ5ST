"""Decode SCI1 EGA and Amiga (ECS, 32-colour) views into per-cel pixel arrays."""
import struct

def _u16(d, o): return struct.unpack('<H', d[o:o+2])[0]

def decode(data, kind):
    """kind: 'ega' or 'amiga'. Returns list of loops; each loop = dict(mirror, cels=[dict(w,h,dx,dy,key,px)])."""
    nloops = data[0]; mirror = _u16(data, 2); loops = []
    for l in range(nloops):
        lo = _u16(data, 8 + 2*l); cels = []
        for c in range(_u16(data, lo)):
            co = _u16(data, lo + 4 + 2*c)
            w, h = _u16(data, co), _u16(data, co + 2)
            dx, dy, key = struct.unpack('b', data[co+4:co+5])[0], data[co+5], data[co+6]
            n = w * h; px = bytearray([key]) * n; i = 0
            if kind == 'ega':
                p = co + 7
                while i < n:
                    b = data[p]; p += 1; r = b >> 4; px[i:i+r] = bytes([b & 15]) * min(r, n - i); i += r
            else:
                p = co + 8
                while i < n:
                    b = data[p]; p += 1
                    if b & 7: r = b & 7; px[i:i+r] = bytes([b >> 3]) * min(r, n - i)
                    else: r = b >> 3
                    i += r
            cels.append(dict(w=w, h=h, dx=dx, dy=dy, key=key, px=bytes(px[:n])))
        loops.append(dict(mirror=(mirror >> l) & 1, cels=cels))
    return loops

def encode_amiga_rle(px, key, w):
    """Encode one cel's pixels in Amiga RLE (colour<<3 | run 1..7, transparent = run<<3).
    Runs never cross row ends: the Amiga interpreter decodes row by row."""
    out = bytearray()
    for y in range(0, len(px), w):
        row = px[y:y + w]; i = 0
        while i < len(row):
            c = row[i]; j = i; lim = 31 if c == key else 7
            while j < len(row) and row[j] == c and j - i < lim: j += 1
            out.append((j - i) << 3 if c == key else (c << 3) | (j - i)); i = j
    return bytes(out)

def amiga_rgb(two):
    """Amiga 12-bit colour word (0RGB, 4 bits each) -> (r, g, b) 0..255."""
    return ((two[0] & 15) * 17, (two[1] >> 4) * 17, (two[1] & 15) * 17)

EGA_RGB = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),
           (85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]
