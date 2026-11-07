import struct, random, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import *
H36=open('work/prog/hunk36.bin','rb').read(); H62=open('work/prog/hunk62.bin','rb').read()
G=open(sys.argv[1],'rb').read()
B36, B62, BG, DATA, STK, RET = 0x100000, 0x200000, 0x300000, 0x400000, 0x500000, 0x600000
h36=bytearray(H36)
# relocate "jsr $398.l" (-> H62_398) inside the distance routine
for off in range(0x2dbc, 0x2e30, 2):
    if h36[off:off+2]==b'\x4e\xb9' and struct.unpack('>I',h36[off+2:off+6])[0]==0x398:
        h36[off+2:off+6]=struct.pack('>I', B62+0x398)
mu=Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_M68000)
for b,sz in ((B36,0x10000),(B62,0x10000),(BG,0x1000),(DATA,0x1000),(STK,0x10000),(RET,0x1000)): mu.mem_map(b,sz)
mu.mem_write(B36,bytes(h36)); mu.mem_write(B62,H62); mu.mem_write(BG,G); mu.mem_write(RET,b'\x4e\x71'*8)
REGS=[UC_M68K_REG_D0+i for i in range(8)]+[UC_M68K_REG_A0+i for i in range(7)]
def run(entry, pts, nargs):
    mu.mem_write(DATA, b''.join(struct.pack('>hh',*p) for p in pts))
    for i,r in enumerate(REGS): mu.reg_write(r, 0x11110000+i)
    mu.reg_write(UC_M68K_REG_A5, 0x11115555)
    sp=STK+0x8000; args=[DATA+4*i for i in range(nargs)]
    mem=struct.pack('>I',RET)+b''.join(struct.pack('>I',a) for a in args)
    mu.mem_write(sp, mem); mu.reg_write(UC_M68K_REG_A7, sp)
    mu.emu_start(entry, RET, count=2000)
    out=bytes(mu.mem_read(DATA,16)); regs={r:mu.reg_read(r) for r in REGS}
    return regs[UC_M68K_REG_D0] & 0xffffffff, out, regs, mu.reg_read(UC_M68K_REG_A7)
F=[('sub',0x2cf2,0x00,3),('add',0x2d24,0x20,3),('dot',0x2d56,0x40,2),('cross',0x2d7c,0x58,2),('dist2',0x2dbc,0x7a,2)]
ORIG_CLOB={'sub':{0,8,9,14},'add':{0,8,9,14},'dot':{0,1,8,9},'cross':{0,1,8,9},'dist2':{0,1,2,8}}
edge=[-32768,-32767,-1000,-1,0,1,1000,32766,32767]
random.seed(1); bad=0
for name,o,g,n in F:
    for k in range(20000):
        if k<len(edge)**2: pts=[(edge[k%9],edge[k//9]),(edge[(k*7)%9],edge[(k*5)%9]),(0,0)]
        else:
            rng = 400 if k%2 else 32768
            pts=[(random.randint(-rng,rng-1),random.randint(-rng,rng-1)) for _ in range(3)]
        if k%5==0 and n==3: pts[2]=pts[0]          # aliasing: result over an input
        d0a,ma,ra,spa=run(B36+o,pts,n); d0b,mb,rb,spb=run(BG+g,pts,n)
        okregs=all(rb[r]==0x11110000+i for i,r in enumerate(REGS) if i not in ORIG_CLOB[name] and r!=UC_M68K_REG_A5)
        if d0a!=d0b and name not in('sub','add') or ma!=mb or spa!=spb or not okregs:
            bad+=1
            if bad<5: print('MISMATCH',name,pts,hex(d0a),hex(d0b),ma.hex(),mb.hex(),okregs)
    print(name,'ok' if not bad else 'bad=%d'%bad)
