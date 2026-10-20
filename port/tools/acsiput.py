# Add a host folder as a subdirectory to the first Atari (BGM) partition of an ACSI image (FAT16),
# keeping what is there (the hard-disk driver). For real-GEMDOS tests (docs/WORKFLOW.md).
# usage: acsiput.py image.img hostdir DIRNAME
import os, struct, sys

img, src, dname = sys.argv[1], sys.argv[2], sys.argv[3]
f = open(img, 'r+b')
mbr = f.read(512)
start = struct.unpack('>I', mbr[0x1c6 + 4:0x1c6 + 8])[0] * 512     # first partition entry
f.seek(start); bs = bytearray(f.read(64))
bps, spc, res, nfats, rootents, total, spf = (struct.unpack('<H', bs[11:13])[0], bs[13],
    struct.unpack('<H', bs[14:16])[0], bs[16], struct.unpack('<H', bs[17:19])[0],
    struct.unpack('<H', bs[19:21])[0], struct.unpack('<H', bs[22:24])[0])
csize = bps * spc
fat_off = start + res * bps
root_off = fat_off + nfats * spf * bps
data_off = root_off + rootents * 32
nclus = (total * bps - (data_off - start)) // csize
print('bps', bps, 'spc', spc, 'clusters', nclus)
f.seek(fat_off); fb = f.read(spf * bps); fat = list(struct.unpack('<%dH' % (len(fb) // 2), fb))
nxt = [max(i for i, x in enumerate(fat) if x) + 1]
f.seek(root_off); oldroot = f.read(rootents * 32)
slot = next(i for i in range(rootents) if oldroot[i * 32] in (0, 0xe5))
data = {}

def alloc(blob):
    n = max(1, (len(blob) + csize - 1) // csize)
    first = nxt[0]
    for i in range(n):
        c = first + i
        fat[c] = c + 1 if i < n - 1 else 0xffff
        data[c] = blob[i * csize:(i + 1) * csize]
    nxt[0] += n
    assert nxt[0] < nclus + 2
    return first

def name83(n):
    b, _, e = n.upper().partition('.')
    return (b.ljust(8)[:8] + e.ljust(3)[:3]).encode()

def entry(n, attr, clus, size):
    return name83(n) + bytes([attr]) + bytes(10) + struct.pack('<HHHI', 0, 0x5521, clus, size)

# subdirectory: reserve its clusters first so we know its own cluster number
names = sorted(os.listdir(src))
nent = len(names) + 2
dclusters = (nent * 32 + csize - 1) // csize
dfirst = alloc(bytes(dclusters * csize))
ents = [b'.' + b' ' * 10 + bytes([0x10]) + bytes(10) + struct.pack('<HHHI', 0, 0x5521, dfirst, 0),
        b'..' + b' ' * 9 + bytes([0x10]) + bytes(10) + struct.pack('<HHHI', 0, 0x5521, 0, 0)]
for n in names:
    blob = open(os.path.join(src, n), 'rb').read()
    ents.append(entry(n, 0, alloc(blob) if blob else 0, len(blob)))
dblob = b''.join(ents).ljust(dclusters * csize, b'\0')
for i in range(dclusters): data[dfirst + i] = dblob[i * csize:(i + 1) * csize]
root = oldroot[:slot * 32] + entry(dname, 0x10, dfirst, 0) + oldroot[slot * 32 + 32:]

fatb = b''.join(struct.pack('<H', x) for x in fat)
for i in range(nfats): f.seek(fat_off + i * spf * bps); f.write(fatb)
f.seek(root_off); f.write(root)
for c, blob in data.items(): f.seek(data_off + (c - 2) * csize); f.write(blob.ljust(csize, b'\0'))
print('used clusters', nxt[0] - 2, 'files', len(names))
