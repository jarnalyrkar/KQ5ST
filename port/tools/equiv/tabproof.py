# tabproof.py: every property/method selector table of every KQ5 script (Amiga resources, with the
# port's .SCR patches); checks that tables sharing (count, first, middle, last) are identical,
# which makes the fingerprinted lookup cache (glue.S tabfind) exact. Run from port/ with python3 -I.
import os, struct, sys
from collections import defaultdict
R='extracted/res_amiga/script'
def words(b): return [struct.unpack('<H', b[i:i+2])[0] for i in range(0, len(b)-1, 2)]
def tables(d):
    out=[]; p=0
    while p+4<=len(d):
        t,sz=struct.unpack('<HH',d[p:p+4])
        if t==0: break
        off=p+4
        if t in (1,6):
            magic,locofs,fsel=struct.unpack('<HHH',d[off:off+6]); nvars=struct.unpack('<H',d[off+6:off+8])[0]
            if t==6: out.append(('prop',tuple(words(d[off+8+nvars*2:off+8+nvars*4]))))
            q=off+6+fsel; n=struct.unpack('<H',d[q:q+2])[0]
            out.append(('meth',tuple(words(d[q+2:q+2+n*2]))))
        p+=sz
    return out
allt=[]; nscripts=0
for f in sorted(os.listdir(R), key=int):
    p=f'st/hd/{f}.SCR'
    d=open(p,'rb').read()[2:] if os.path.exists(p) else open(f'{R}/{f}','rb').read()
    nscripts+=1
    for kind,t in tables(d): allt.append((f,kind,t))
fp=lambda t: (len(t), t[0], t[len(t)//2], t[-1]) if t else (0,)
groups=defaultdict(set)
for f,k,t in allt: groups[fp(t)].add(t)
coll=[(k,v) for k,v in groups.items() if len(v)>1]
print(nscripts,'scripts,',len(allt),'tables,',len(set(t for _,_,t in allt)),'distinct,',len(coll),'fingerprint collisions')
for k,v in coll[:5]: print(' ',k,[len(x) for x in v])
print('max table length', max(len(t) for _,_,t in allt), '| counts > 1 and len<3:', sum(1 for _,_,t in allt if 0<len(t)<3))
