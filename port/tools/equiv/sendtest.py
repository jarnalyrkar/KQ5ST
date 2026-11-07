# sendtest.py TABBIN PROPADDR [N]: send's property lookup (hunk 23 +$22c), original vs glue.S
# hook_proplookup (index hint + fingerprinted tabfind cache), on real KQ5 selector tables
# (tabproof.py) placed at reused addresses, sometimes replaced by another table at the same
# address. Compares the end address (+$23c found / +$25e absent) and all 15 registers.
import struct, random, sys, os
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import *
sys.path.insert(0, os.path.dirname(__file__))
import tabproof
H23=open('work/prog/hunk23.bin','rb').read(); HOOK=open(sys.argv[1],'rb').read()
PROP=int(sys.argv[2],16); N=int(sys.argv[3]) if len(sys.argv)>3 else 20000
BO, BP, BH, CACHE, TAB, OBJ, STK = 0x100000, 0x200000, 0x300000, 0x380000, 0x500000, 0x600000, 0x700000
mu=Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_M68000)
for b,sz in ((BO,0x10000),(BP,0x10000),(BH,0x10000),(CACHE,0x10000),(TAB,0x10000),(OBJ,0x1000),(STK,0x10000)): mu.mem_map(b,sz)
p=bytearray(H23); p[0x22c:0x232]=b'\x4e\xf9'+struct.pack('>I',PROP)
mu.mem_write(BO,H23); mu.mem_write(BP,bytes(p)); mu.mem_write(BH,HOOK)
tabs=sorted(set(t for _,_,t in tabproof.allt if t))
REGS=[UC_M68K_REG_D0+i for i in range(8)]+[UC_M68K_REG_A0+i for i in range(7)]
def run(base, regs):
    for r,v in zip(REGS,regs): mu.reg_write(r,v)
    mu.reg_write(UC_M68K_REG_A7, STK+0x8000); hit=[None]
    h=mu.hook_add(UC_HOOK_CODE, lambda uc,a,s,u: (hit.__setitem__(0,a), uc.emu_stop()) if a-base in (0x23c,0x25e) else None)
    mu.emu_start(base+0x22c, 0, count=200000); mu.hook_del(h)
    return (hit[0]-base if hit[0] else None), [mu.reg_read(r) for r in REGS]
random.seed(3); slots=[TAB+0x100*(i+1) for i in range(16)]; content={}; bad=0
for k in range(N):
    slot=random.choice(slots)
    if slot not in content or random.random()<0.05:
        t=random.choice(tabs); content[slot]=t
        mu.mem_write(slot-2, struct.pack('>H',len(t))+b''.join(struct.pack('>H',x) for x in t))
    t=content[slot]
    sel=random.choice(t) if random.random()<0.5 else random.choice([random.choice(random.choice(tabs)), random.randint(0,0xffff)])
    regs=[random.getrandbits(32) for _ in REGS]
    regs[4]=(regs[4]&0xffff0000)|sel; regs[9]=slot; regs[11]=OBJ+0x100
    mu.mem_write(OBJ+0x100-2, struct.pack('>H',len(t)))
    a=run(BO,regs); b=run(BP,regs)
    if a!=b:
        bad+=1
        if bad<4: print('MISMATCH', k, a[0], b[0], [hex(x^y) for x,y in zip(a[1],b[1]) if x!=y])
print(N,'lookups,',bad,'mismatches')
