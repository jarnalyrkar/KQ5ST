import struct, random, sys
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import *
H56=open('work/prog/hunk56.bin','rb').read(); HOOK=open(sys.argv[1],'rb').read(); HOOKADDR=int(sys.argv[2],16)
B56, BH, A4, PLANES, PRI, SRC, STK, RET = 0x100000, 0x300000, 0x408000, 0x500000, 0x600000, 0x700000, 0x800000, 0x900000
def mk(patched):
    mu=Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_M68000)
    for b,sz in ((B56,0x10000),(BH,0x10000),(A4-0x8000,0x10000),(PLANES,0x10000),(PRI,0x10000),(SRC,0x10000),(STK,0x10000),(RET,0x1000)): mu.mem_map(b,sz)
    h=bytearray(H56)
    if patched: h[0x578:0x57e]=b'\x4e\xf9'+struct.pack('>I',HOOKADDR)
    mu.mem_write(B56,bytes(h)); mu.mem_write(BH,HOOK); mu.mem_write(RET,b'\x4e\x71'*8)
    def w(off,fmt,*v): mu.mem_write(A4+off, struct.pack(fmt,*v))
    w(-0x6624,'>200H',*[y*40 for y in range(200)])      # plane row offsets
    w(-0x67b4,'>200H',*[y*320 for y in range(200)])     # pri/ctl row offsets
    w(-0x647c,'>I',PLANES); w(-0x6478,'>I',PRI)
    w(-0x628e,'>32I',*[B56+0x5ba+0x14*c+4 for c in range(32)])
    return mu, w
M=[mk(False),mk(True)]
REGS=[UC_M68K_REG_D0+i for i in range(8)]+[UC_M68K_REG_A0+i for i in range(7)]
def run(mu,w,src,x,y,width,rows,d3,d6,d7,planes,pri):
    mu.mem_write(PLANES,planes); mu.mem_write(PRI,pri); mu.mem_write(SRC,src)
    w(-0x62b4,'>H',width); w(-0x62a4,'>H',y); w(-0x62a2,'>H',x); w(-0x62b2,'>H',rows)
    for r in REGS: mu.reg_write(r,0)
    mu.reg_write(UC_M68K_REG_D3,d3); mu.reg_write(UC_M68K_REG_D6,d6); mu.reg_write(UC_M68K_REG_D7,d7)
    mu.reg_write(UC_M68K_REG_A0,SRC); mu.reg_write(UC_M68K_REG_A4,A4)
    sp=STK+0x8000; mu.mem_write(sp,struct.pack('>II',0xdead0000,RET)); mu.reg_write(UC_M68K_REG_A7,sp)
    mu.emu_start(B56+0x4e0, RET, count=2000000)
    return bytes(mu.mem_read(PLANES,0xa000)), bytes(mu.mem_read(PRI,64000)), mu.reg_read(UC_M68K_REG_A0), [mu.reg_read(r) for r in (UC_M68K_REG_D3,UC_M68K_REG_D6,UC_M68K_REG_D7)]
random.seed(7); bad=0; N=int(sys.argv[3])
for k in range(N):
    width=random.randint(1,120); rows=random.randint(1,30); x=random.randint(0,319-width); y=random.randint(0,199-rows)
    src=bytearray()
    for r in range(rows):
        left=width
        while left:
            if random.random()<0.25:
                n=random.randint(1,min(31,left)); src.append(n<<3)            # transparent skip
            else:
                n=random.randint(1,min(7,left)); src.append((random.randint(0,31)<<3)|n)
            left-=n
    planes=bytes(random.getrandbits(8) for _ in range(0xa000)); pri=bytes(random.getrandbits(8) for _ in range(64000))
    d6=random.choice([0x00,0x40,0x80,0xff,random.randint(0,0xffff)]); d7=random.getrandbits(8); d3=random.getrandbits(8)
    a=run(*M[0],bytes(src),x,y,width,rows,d3,d6,d7,planes,pri); b=run(*M[1],bytes(src),x,y,width,rows,d3,d6,d7,planes,pri)
    if a!=b:
        bad+=1
        if bad<4: print('MISMATCH case',k,'planes',a[0]==b[0],'pri',a[1]==b[1],'a0',a[2]==b[2],'regs',a[3],b[3])
print(N,'cases,',bad,'mismatches')
