# Minimal AmigaDOS OFS/FFS extractor: adf.py image.adf outdir
import sys, os, struct
img = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
B = 512
def blk(n): return img[n*B:(n+1)*B]
def L(b, off): return struct.unpack('>I', b[off:off+4])[0]
def Ls(b, off): return struct.unpack('>i', b[off:off+4])[0]
dostype = img[0:4]
ffs = dostype[3] & 1
print('dostype', dostype, 'FFS' if ffs else 'OFS')
def name(b): n = b[B-80]; return b[B-79:B-79+n].decode('latin1')
def readfile(hdr):
    b = blk(hdr); size = L(b, B-188); data = bytearray()
    if ffs:
        while True:
            n = L(b, 8)
            ptrs = [L(b, 24 + 4*i) for i in range(72)][::-1][:n]
            for p in ptrs: data += blk(p)
            ext = L(b, B-8)
            if not ext: break
            b = blk(ext)
        return bytes(data[:size])
    p = L(b, 16)  # first data block
    while p:
        d = blk(p); n = L(d, 12); data += d[24:24+n]; p = L(d, 16)
    return bytes(data[:size])
def walk(dirblk, path):
    b = blk(dirblk)
    for i in range(72):
        h = L(b, 24 + 4*i)
        while h:
            e = blk(h); st = Ls(e, B-4); nm = name(e)
            p = os.path.join(path, nm)
            if st == 2: os.makedirs(p, exist_ok=True); walk(h, p)
            elif st == -3: open(p, 'wb').write(readfile(h))
            h = L(e, B-16)
os.makedirs(out, exist_ok=True)
walk(880, out)
