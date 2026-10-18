# Convert SHOTnn.ST dumps (32-byte STE palette + 32000-byte low-res screen) to PNG.  st2png.py FILE... -> FILE.png
import sys
from PIL import Image
for path in sys.argv[1:]:
    d = open(path, 'rb').read(); pal = []
    for i in range(16):
        w = (d[2*i] << 8) | d[2*i+1]
        ste = lambda v: ((v & 7) << 1) | ((v >> 3) & 1)
        pal.append(tuple(ste((w >> s) & 15) * 17 for s in (8, 4, 0)))
    scr = d[32:]; im = Image.new('RGB', (320, 200)); px = im.load()
    for y in range(200):
        for g in range(20):
            o = y * 160 + g * 8; pl = [(scr[o + 2*k] << 8) | scr[o + 2*k + 1] for k in range(4)]
            for b in range(16):
                c = sum(((pl[k] >> (15 - b)) & 1) << k for k in range(4))
                px[g * 16 + b, y] = pal[c]
    im.resize((640, 400), Image.NEAREST).save(path + '.png'); print('wrote', path + '.png')
