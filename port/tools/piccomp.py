#!/usr/bin/env python3
"""Overlay check: piccomp.py OUT.png PIC VIEW:LOOP:CEL:X:Y ...
Renders the DOS EGA picture PIC twice and draws each cel at the prop position (x, y as in the
room script): left with the DOS EGA view, right with the current ST art (st/hd/VIEW.v32).
Shows whether EGA cels line up with the EGA picture (GRAPHICS.md "Overlay faces"). Priority is
ignored. Run from port/."""
import sys, os
sys.path.insert(0, 'tools')
from sciview import decode, EGA_RGB
import scipic
from PIL import Image
R='extracted'
out, pic = sys.argv[1], int(sys.argv[2])
P = scipic.render(open(f'{R}/res_dos/pic/{pic}','rb').read(), True)
vis = P.vis
def panel(kind):
    im = Image.new('RGB', (320,190))
    im.putdata([EGA_RGB[c & 15] for c in vis[:320*190]])
    for spec in sys.argv[3:]:
        v,l,c,x,y = map(int, spec.split(':'))
        if kind=='ega': vw = decode(open(f'{R}/res_dos/view/{v}','rb').read(),'ega')
        else: vw = decode(open(f'st/hd/{v}.v32','rb').read()[2:],'amiga')
        ce = vw[l]['cels'][min(c, len(vw[l]['cels'])-1)]
        left = x - ce['w']//2 + ce['dx']; top = y - ce['h'] + 1 + ce['dy']
        for j in range(ce['h']):
            for i in range(ce['w']):
                p = ce['px'][j*ce['w']+i]
                if p == ce['key'] or p==255: continue
                X,Y=left+i, top+j
                if 0<=X<320 and 0<=Y<190: im.putpixel((X,Y), EGA_RGB[p & 15])
    return im
a,b = panel('ega'), panel('st')
o = Image.new('RGB',(640,190)); o.paste(a,(0,0)); o.paste(b,(320,0))
o.resize((1280,380), Image.NEAREST).save(out)
