# pmtest.py PMBIN PMENTRY [N] [SEED]: the rewritten bytecode interpreter (st/src/pmachine.S) against
# Prog's hunk 4 loop, on random worlds of scripts, classes, instances and bytecode, run on a 68000
# model (unicorn). Both run with Prog's real hunk 23 (send) and the same stand-ins for the kernel
# functions, the script loader and PError (python hooks on "rts" stubs); the stand-ins clobber every
# register they may, return pseudo-random results in acc and move every script's code now and then
# (the PC must survive as an offset). Compared after each world: every variable, stack, object and
# interpreter global, the kernel-call log, the error (if any) and a0/a2/d2.w at the final ret.
import struct, random, sys, os, json
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UcError
from unicorn.m68k_const import *

H4 = open('work/prog/hunk04.bin', 'rb').read()
H23 = open('work/prog/hunk23.bin', 'rb').read()
H1 = open('work/prog/hunk01.bin', 'rb').read()
PM = open(sys.argv[1], 'rb').read(); PMENTRY = int(sys.argv[2], 16)
N = int(sys.argv[3]) if len(sys.argv) > 3 else 300
SEED = int(sys.argv[4]) if len(sys.argv) > 4 else 1
TRACE = int(sys.argv[5]) if len(sys.argv) > 5 else None      # world number to trace opcode by opcode
def entry_is_orig(run): return run.orig

BO, B23, BH, KSTUB, DATA = 0x100000, 0x200000, 0x300000, 0x380000, 0x400000
LOCR, GLOBR, STKR, HEAP, CODE, SSTK = 0x500000, 0x580000, 0x600000, 0x700000, 0x800000, 0x900000
H1B = DATA + 0x100; A4 = H1B + 0x7ffe
GLOB = GLOBR + 0x10000; STK = STKR + 0x20000; SSP = SSTK + 0xf000
OBJS, STRUCTS, CLASSTBL, HANDLES = HEAP + 0x1000, HEAP + 0x8000, HEAP + 0xc000, HEAP + 0xd000
V_LOADSCRIPT, V_LOADCLASS, V_ERROR, TRAP, RET = KSTUB + 0x200, KSTUB + 0x202, KSTUB + 0x204, KSTUB + 0x300, KSTUB + 0x400
G = dict(ACC=-0x7134, SUPER=-0x7132, CALLKPC=-0x7144, SCRIPTNUM=-0x7148, SCRIPT=-0x7150, CLASSTBL=-0x715c,
         OBJ=-0x7160, REST=-0x7164, PARAMS=-0x7168, TEMPS=-0x716c, LOCALS=-0x7170, GLOBALS=-0x7174,
         STKLIM=-0x7178, STKBASE=-0x717c, STKSAVE=-0x7180, PCSAVE=-0x7184, DBGSTK=-0x726a, HEAP=-0x5912)
REGS = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]
near = lambda a: a - HEAP
be16 = lambda v: struct.pack('>H', v & 0xffff)
le16 = lambda v: struct.pack('<H', v & 0xffff)

# ---- the world: scripts, objects, bytecode -----------------------------------------------
PROPSEL = list(range(0x100, 0x110)); METHSEL = list(range(0x200, 0x210))
SEL_SPECIES, SEL_SUPER = 0x1000, 0x1001
OPS = dict(bnot=0, add=1, sub=2, mul=3, div=4, mod=5, shr=6, shl=7, xor=8, and_=9, or_=10, neg=11, not_=12,
           eq=13, ne=14, gt=15, ge=16, lt=17, le=18, ugt=19, uge=20, ult=21, ule=22, bt=23, bnt=24, jmp=25,
           ldi=26, push=27, pushi=28, toss=29, dup=30, link=31, call=32, callk=33, callb=34, calle=35, ret=36,
           send=37, class_=40, self_=42, super_=43, rest=44, lea=45, selfid=46, pprev=48, ptoa=49, atop=50,
           ptos=51, stop=52, iptoa=53, dptoa=54, iptos=55, dptos=56, lofsa=57, lofss=58, push0=59, push1=60,
           push2=61, pushself=62)
VKIND = dict(l=0, s=1, i=2, d=3); VTYPE = dict(g=0, l=1, t=2, p=3)

class Body:
    def __init__(self, script, kind): self.script, self.kind, self.code, self.fix, self.off = script, kind, bytearray(), [], None

class Obj:
    def __init__(self, script, isclass): self.script, self.isclass, self.props, self.methods, self.super, self.addr, self.clsid = script, isclass, [], {}, None, None, None

class World:
    def __init__(self, rng):
        self.rng = rng
        self.nscripts = rng.randint(1, 3)
        self.scripts = [dict(bodies=[], procs=[], classes=[], objects=[], code=None, exports=[]) for _ in range(self.nscripts)]
        self.bodies = []; self.classes = []; self.objects = []
        # procedures (exports)
        for s in range(self.nscripts):
            for _ in range(rng.randint(1, 3)):
                b = Body(s, 'proc'); self.scripts[s]['procs'].append(b); self.bodies.append(b)
        # classes with a chain of superclasses, each with some methods
        for s in range(self.nscripts):
            for _ in range(rng.randint(0, 2)):
                c = Obj(s, True); c.clsid = len(self.classes); self.classes.append(c); self.scripts[s]['classes'].append(c)
                if self.classes[:-1] and rng.random() < 0.7: c.super = rng.choice(self.classes[:-1])
                nprops = rng.randint(2, 6)
                c.props = [(SEL_SPECIES, 0), (SEL_SUPER, 0)] + [(sel, rng.getrandbits(16)) for sel in rng.sample(PROPSEL, nprops)]
                for sel in rng.sample(METHSEL, rng.randint(1, 3)):
                    b = Body(s, 'method'); b.cls = c; c.methods[sel] = b; self.bodies.append(b)
        if not self.classes:
            c = Obj(0, True); c.clsid = 0; self.classes.append(c); self.scripts[0]['classes'].append(c)
            c.props = [(SEL_SPECIES, 0), (SEL_SUPER, 0), (PROPSEL[0], 7)]
            b = Body(0, 'method'); b.cls = c; c.methods[METHSEL[0]] = b; self.bodies.append(b)
        # instances
        for s in range(self.nscripts):
            for _ in range(rng.randint(0, 2)):
                o = Obj(s, False); o.super = rng.choice(self.classes)
                o.props = [(sel, rng.getrandbits(16)) for sel, _ in o.super.props]
                self.objects.append(o)
        self.objects = self.classes + self.objects
        # body order: main first, the rest shuffled; a body only calls later bodies
        main = self.scripts[0]['procs'][0]
        rest = [b for b in self.bodies if b is not main]; rng.shuffle(rest)
        self.bodies = [main] + rest
        for i, b in enumerate(self.bodies): b.index = i
        # addresses: objects, structs, handles, code slots
        a = OBJS
        for o in self.objects:
            o.addr = a + 10; a += 10 + 2 * len(o.props) + 6; a = (a + 1) & ~1
        for i, b in enumerate(self.bodies): self.gen_body(b)
        for s in range(self.nscripts): self.layout(s)

    # selector resolution as hunk 23 does it: properties of the object, then method dicts up the chain
    def resolve(self, o, sel):
        for i, (ps, _) in enumerate(o.props):
            if ps == sel: return ('prop', i)
        c = o
        while c is not None:
            if sel in c.methods: return ('method', c.methods[sel])
            c = c.super
        return None

    def min_body(self, sel):      # smallest body index any object resolves sel to (None = never a method)
        m = None
        for o in self.objects:
            r = self.resolve(o, sel)
            if r and r[0] == 'method': m = r[1].index if m is None else min(m, r[1].index)
        return m

    # ---- bytecode --------------------------------------------------------------------
    def op(self, b, name, size=1, *args):
        b.code.append(OPS[name] * 2 + size)
        for a in args: b.code += (bytes([a & 0xff]) if size else le16(a))
    def vop(self, b, kind, idx, stk, typ, size, n):
        b.code.append(0x80 | (VKIND[kind] << 5) | (idx << 4) | (stk << 3) | (VTYPE[typ] << 1) | size)
        b.code += bytes([n & 0xff]) if size else le16(n)
    def imm(self, b, size, v): b.code += bytes([v & 0xff]) if size else le16(v)

    def gen_body(self, b):
        rng = self.rng; self.cur = b; self.depth = 0
        if rng.random() < 0.6: self.op(b, 'link', rng.choice([1, 0]), rng.randint(1, 8))
        for _ in range(rng.randint(1, 5)): self.stmt(b)
        if rng.random() < 0.7: self.expr(b)
        nxt = [x for x in self.bodies if x.index > b.index and x.script == b.script]
        if nxt and rng.random() < 0.4:      # byte-form call: only to the body laid out right after this one
            argc = rng.randint(0, 2); self.args(b, argc)
            b.code.append(OPS['call'] * 2 + 1); pos = len(b.code); b.code.append(0); b.code.append(2 * argc)
            b.fix.append((pos, 1, nxt[0], len(b.code)))
        self.op(b, 'ret')

    def varidx(self, rng, size):
        if size: return rng.choice([0, 1, 2, 3, 5, 8, rng.randint(0, 255)])
        return rng.choice([0, 1, 7, 100, 0x7fff, 0x8000, 0xffff, rng.getrandbits(16)])

    def expr(self, b):
        rng = self.rng; self.depth += 1
        deep = self.depth > 3
        k = rng.random()
        size = rng.choice([1, 0])
        if deep or k < 0.25:
            c = rng.random()
            if c < 0.3: self.op(b, 'ldi', size, rng.getrandbits(8) if size else rng.getrandbits(16))
            elif c < 0.6: self.vop(b, 'l', 0, 0, rng.choice('gltp'), size, self.varidx(rng, size))
            elif c < 0.75: self.op(b, 'ptoa', size, self.propoff(rng, size))
            elif c < 0.85: self.op(b, 'selfid')
            elif c < 0.95: self.op(b, 'lofsa', 0, rng.getrandbits(16))
            else: self.op(b, 'class_', size, rng.randint(0, 255) if size else rng.choice([rng.randint(0, 15), rng.getrandbits(16)]))
        elif k < 0.45:                      # binary
            self.expr(b); self.op(b, 'push'); self.expr(b)
            self.op(b, rng.choice(['add', 'sub', 'mul', 'div', 'mod', 'shr', 'shl', 'xor', 'and_', 'or_', 'eq', 'ne', 'gt', 'ge', 'lt', 'le', 'ugt', 'uge', 'ult', 'ule']))
        elif k < 0.52: self.expr(b); self.op(b, rng.choice(['bnot', 'neg', 'not_']))
        elif k < 0.6: self.expr(b); self.vop(b, 'l', 1, 0, rng.choice('gltp'), size, self.varidx(rng, size))
        elif k < 0.66: self.vop(b, rng.choice('id'), 0, 0, rng.choice('gltp'), size, self.varidx(rng, size))
        elif k < 0.7: self.expr(b); self.vop(b, rng.choice('id'), 1, 0, rng.choice('gltp'), size, self.varidx(rng, size))
        elif k < 0.74: self.op(b, rng.choice(['iptoa', 'dptoa']), size, self.propoff(rng, size, write=True))
        elif k < 0.8:                       # lea
            t = rng.randint(0, 3) | (0x10 if rng.random() < 0.5 else 0)
            if t & 0x10: self.expr(b)
            self.op(b, 'lea', size, t, self.varidx(rng, size))
        elif k < 0.86: self.callk(b)
        elif k < 0.92: self.call(b)
        elif k < 0.97: self.send(b)
        else:                               # n-ary comparison with pprev
            self.expr(b); self.op(b, 'push'); self.expr(b); self.op(b, 'lt')
            self.op(b, 'bnt', 1, 0); fix = len(b.code) - 1
            self.op(b, 'pprev'); self.expr(b); self.op(b, 'lt')
            b.code[fix] = len(b.code) - fix - 1
        self.depth -= 1

    def propoff(self, rng, size, write=False):
        o = self.cur.cls if self.cur.kind == 'method' else self.classes[0]
        n = len(o.props)
        lo = 2 if write else 0
        if rng.random() < 0.9 or size == 0: return 2 * rng.randint(lo, n - 1)
        return rng.choice([2 * (n + 1), 2 * (n + 4)])

    def stmt(self, b):
        rng = self.rng; k = rng.random(); size = rng.choice([1, 0])
        if k < 0.3:                          # stores
            c = rng.random(); typ = rng.choice('gltp'); n = self.varidx(rng, size)
            if c < 0.25: self.expr(b); self.vop(b, 's', 0, 0, typ, size, n)
            elif c < 0.5: self.expr(b); self.op(b, 'push'); self.vop(b, 's', 0, 1, typ, size, n)
            elif c < 0.75: self.expr(b); self.op(b, 'push'); self.expr(b); self.vop(b, 's', 1, 0, typ, size, n)
            else: self.expr(b); self.op(b, 'push'); self.expr(b); self.vop(b, 's', 1, 1, typ, size, n)
        elif k < 0.45:                       # property stores
            c = rng.random(); n = self.propoff(rng, size, write=True)
            if c < 0.4: self.expr(b); self.op(b, 'atop', size, n)
            elif c < 0.8: self.expr(b); self.op(b, 'push'); self.op(b, 'stop', size, n)
            else: self.op(b, rng.choice(['iptos', 'dptos']), size, n); self.op(b, 'toss')
        elif k < 0.6:                        # if: the block is generated apart, then the branch size chosen
            self.expr(b); blk = Body(b.script, b.kind); blk.index = b.index; blk.cls = getattr(b, 'cls', None)
            save = self.cur; self.cur = blk
            for _ in range(rng.randint(1, 3)): self.stmt(blk)
            self.cur = save
            if len(blk.code) > 120: size = 0
            self.op(b, rng.choice(['bnt', 'bt']), size, len(blk.code))
            base = len(b.code); b.code += blk.code
            for pos, sz, tgt, end in blk.fix: b.fix.append((base + pos, sz, tgt, base + end))
        elif k < 0.68:                       # jmp over junk
            self.op(b, 'jmp', size, 0); fix = len(b.code) - (1 if size else 2)
            b.code += bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 4)))
            d = len(b.code) - fix - (1 if size else 2)
            b.code[fix:fix + (1 if size else 2)] = bytes([d]) if size else le16(d)
        elif k < 0.75:                       # stack fiddling
            self.expr(b); self.op(b, 'push'); self.op(b, 'dup'); self.op(b, rng.choice(['add', 'xor', 'eq'])); self.op(b, 'toss')
        elif k < 0.8: self.pushconst(b)
        elif k < 0.85: self.vop(b, rng.choice('id'), 0, 1, rng.choice('gltp'), size, self.varidx(rng, size)); self.op(b, 'toss')
        else: self.expr(b)

    def pushconst(self, b):
        rng = self.rng; c = rng.choice(['push0', 'push1', 'push2', 'pushself', 'lofss', 'pushi', 'ptos', 'ls'])
        if c == 'lofss': self.op(b, 'lofss', 0, rng.getrandbits(16))
        elif c == 'pushi': s = rng.choice([1, 0]); self.op(b, 'pushi', s, rng.getrandbits(8) if s else rng.getrandbits(16))
        elif c == 'ptos': s = rng.choice([1, 0]); self.op(b, 'ptos', s, self.propoff(rng, s))
        elif c == 'ls': s = rng.choice([1, 0]); self.vop(b, 'l', rng.choice([0, 1]), 1, rng.choice('gltp'), s, self.varidx(rng, s))
        else: self.op(b, c)
        self.op(b, 'toss')

    def args(self, b, argc):
        self.op(b, 'pushi', 1, argc)
        for _ in range(argc): self.expr(b); self.op(b, 'push')

    def callk(self, b):
        rng = self.rng; argc = rng.randint(0, 3); self.args(b, argc)
        rest = rng.random() < 0.2
        if rest: self.op(b, 'rest', 1, rng.randint(0, 4))
        n = rng.choice([rng.randint(0, 123), rng.randint(0, 123), 124, 200]) if rng.random() < 0.03 else rng.randint(0, 123)
        size = rng.choice([1, 0]); b.code.append(OPS['callk'] * 2 + size); self.imm(b, size, n); b.code.append(2 * argc)

    def call(self, b):
        rng = self.rng; cur = self.cur
        later = [x for x in self.bodies if x.index > cur.index]
        argc = rng.randint(0, 3); self.args(b, argc)
        if rng.random() < 0.2: self.op(b, 'rest', 1, rng.randint(0, 4))
        c = rng.random()
        same = [x for x in later if x.script == cur.script]
        if c < 0.4 and same:                 # call: relative, same script (word form; byte form: gen_body)
            t = rng.choice(same); size = 0
            b.code.append(OPS['call'] * 2 + size); pos = len(b.code); self.imm(b, size, 0); b.code.append(2 * argc)
            b.fix.append((pos, size, t, len(b.code)))
        else:                                # calle / callb: exported procedure of a script
            procs = [x for x in later if x.kind == 'proc']
            if not procs: self.op(b, 'toss'); [self.op(b, 'toss') for _ in range(argc)]; return
            t = rng.choice(procs); s = t.script; e = self.scripts[s]['procs'].index(t)
            if rng.random() < 0.03: e = len(self.scripts[s]['procs']) + rng.randint(0, 3)      # bad export -> error 0
            if s == 0 and rng.random() < 0.5: self.op(b, 'callb', rng.choice([1, 0]), e, 2 * argc)
            else:
                size = rng.choice([1, 0]); b.code.append(OPS['calle'] * 2 + size); self.imm(b, size, s); self.imm(b, size, e); b.code.append(2 * argc)

    def send(self, b):
        rng = self.rng; cur = self.cur
        form = rng.choice(['send', 'send', 'self', 'super', 'class'])
        if form == 'super' and (cur.kind != 'method' or cur.cls.super is None): form = 'send'
        if form == 'self' and cur.kind != 'method': form = 'send'
        if form == 'send': o = rng.choice(self.objects)
        elif form == 'class': o = rng.choice(self.classes)
        elif form == 'self': o = cur.cls
        else: o = cur.cls.super
        # selectors: properties (read or write) or methods resolving to later bodies, 1-3 of them
        sels = []
        for _ in range(rng.randint(1, 3)):
            props = [s for s, _ in o.props[2:]] + ([SEL_SPECIES, SEL_SUPER] if rng.random() < 0.1 else [])
            cands = [('p', s) for s in props]
            for s in METHSEL:
                m = self.min_body(s)
                r = self.resolve(o, s)
                if r and r[0] == 'method' and m is not None and m > cur.index and (form != 'self' or m > cur.index): cands.append(('m', s))
            if form == 'self':   # self: the actual object may be any object whose chain holds cur.cls
                cands = [c for c in cands if c[0] == 'p' or self.min_body(c[1]) > cur.index]
            if rng.random() < 0.02: cands.append(('x', rng.choice([0x300, 0x3ff])))   # unknown -> error 5
            if not cands: continue
            sels.append(rng.choice(cands))
        if not sels: sels = [('p', o.props[2][0] if len(o.props) > 2 else SEL_SPECIES)]
        if form == 'send' or form == 'class':
            if form == 'class' or rng.random() < 0.7:
                if form == 'class' or rng.random() < 0.5: self.op(b, 'class_', rng.choice([1, 0]), o.clsid if o.isclass else o.super.clsid)
                else: self.op(b, 'lofsa', 0, near(o.addr))
            else: self.op(b, 'lofsa', 0, near(o.addr))
            if form == 'class' and not o.isclass: pass
        total = 0
        for kind, sel in sels:
            size = rng.choice([1, 0])
            if kind == 'p' and sel not in (SEL_SPECIES, SEL_SUPER) and rng.random() < 0.5:
                self.op(b, 'pushi', 0, sel); self.op(b, 'pushi', 1, 1); self.expr(b); self.op(b, 'push'); total += 6
            else:
                argc = rng.randint(0, 2) if kind == 'm' else 0
                self.op(b, 'pushi', 0, sel); self.op(b, 'pushi', 1, argc)
                for _ in range(argc): self.expr(b); self.op(b, 'push')
                total += 4 + 2 * argc
        if rng.random() < 0.15 and self.cur.kind == 'method': self.op(b, 'rest', 1, rng.randint(0, 3))
        if form == 'send' or form == 'class': self.op(b, 'send', 1, total)
        elif form == 'self': self.op(b, 'self_', 1, total)
        else: size = rng.choice([1, 0]); b.code.append(OPS['super_'] * 2 + size); self.imm(b, size, o.clsid); b.code.append(total)

    # ---- layout of a script's code block ----------------------------------------------
    # tables (selectors, method dicts, exports) are big-endian: the loader swaps them; operands stay little-endian
    def layout(self, s):
        sc = self.scripts[s]; code = bytearray(b'\0' * 16)
        for o in [x for x in self.objects if x.script == s]:
            if o.isclass:
                o.sellist = len(code)
                for sel, _ in o.props: code += be16(sel)
            o.methoff = len(code) + 2
            code += be16(len(o.methods))
            for sel in o.methods: code += be16(sel)
            code += be16(0)
            o.methfix = len(code)
            for sel in o.methods: code += be16(0)
        if len(code) & 1: code.append(0)
        sc['exportoff'] = len(code)
        code += be16(len(sc['procs']))
        for p in sc['procs']: code += be16(0) + be16(0xeeee)     # entry: offset, then a word Prog ignores
        for b in [x for x in self.bodies if x.script == s]:
            b.off = len(code); code += b.code
            if len(code) & 1: code.append(0)
        for b in [x for x in self.bodies if x.script == s]:
            for pos, size, t, end in b.fix:
                d = t.off - (b.off + end)
                code[b.off + pos:b.off + pos + (1 if size else 2)] = bytes([d & 0xff]) if size else le16(d)
                assert size == 0 or -128 <= d < 128, 'call too far'
        for i, p in enumerate(sc['procs']): code[sc['exportoff'] + 2 + 4 * i:sc['exportoff'] + 2 + 4 * i + 2] = be16(p.off)
        for o in [x for x in self.objects if x.script == s]:
            for i, sel in enumerate(o.methods): code[o.methfix + 2 * i:o.methfix + 2 * i + 2] = be16(o.methods[sel].off)
        assert len(code) < 0x8000
        sc['code'] = bytes(code)

    # ---- memory image (identical for both interpreters except vector 3) ----------------
    def image(self, mu, entry):
        w = mu.mem_write
        h1 = bytearray(H1) + bytes(0x31ac - len(H1))
        for i in range(192): h1[6 * i:6 * i + 6] = b'\x4e\xf9' + struct.pack('>I', TRAP)
        for i, t in ((3, entry), (16, V_LOADSCRIPT), (17, V_LOADCLASS), (124, B23 + 0x152), (125, B23 + 0x312), (126, B23 + 0x324), (189, V_ERROR)):
            h1[6 * i + 2:6 * i + 6] = struct.pack('>I', t)
        for n in range(124): h1[0x7e8 + 4 * n:0x7e8 + 4 * n + 4] = struct.pack('>I', KSTUB + 2 * n)
        def g(name, fmt, v): off = 0x7ffe + G[name]; h1[off:off + struct.calcsize(fmt)] = struct.pack(fmt, v)
        g('ACC', '>H', self.rng.getrandbits(16)); g('SUPER', '>H', 0); g('REST', '>H', 0); g('SCRIPTNUM', '>H', 0)
        g('GLOBALS', '>I', GLOB); g('LOCALS', '>I', self.locals(0)); g('PARAMS', '>I', STK); g('TEMPS', '>I', STK + 2)
        g('STKBASE', '>I', STK); g('STKLIM', '>I', STK + 0x1000); g('STKSAVE', '>I', STK); g('PCSAVE', '>I', 0); g('CALLKPC', '>I', 0)
        g('SCRIPT', '>I', HANDLES + 4 * 0); g('OBJ', '>I', self.objects[0].addr); g('CLASSTBL', '>I', CLASSTBL)
        g('HEAP', '>I', HEAP); g('DBGSTK', '>I', H1B + 0xd40 - 4)
        w(H1B, bytes(h1))
        h23 = bytearray(H23)
        for off in (0x17a, 0x1e0, 0xdd2): h23[off:off + 4] = struct.pack('>I', H1B + struct.unpack('>I', h23[off:off + 4])[0])
        w(B23, bytes(h23)); w(BO, H4); w(BH, PM)
        w(KSTUB, b'\x4e\x75' * 0x180); w(TRAP, b'\x4a\xfc' * 8); w(RET, b'\x4e\x71' * 4)
        # objects
        for o in self.objects:
            cls = o if o.isclass else o.super
            hdr = be16(0x1234) + be16(near(STRUCTS + 0x20 * o.script)) + be16(o.methoff) + be16(near(STRUCTS + 0x20 * cls.script)) + be16(len(o.props))
            vals = [cls.sellist, near(o.super.addr) if o.super else 0] + [v for _, v in o.props[2:]]
            w(o.addr - 10, hdr + b''.join(be16(v) for v in vals))
        # class table, script structs, handles, code, locals
        for c in self.classes: w(CLASSTBL + 4 * c.clsid, be16(0 if self.unloaded(c) else near(c.addr)) + be16(c.script))
        for s in range(self.nscripts):
            w(STRUCTS + 0x20 * s, bytes(10) + struct.pack('>I', HANDLES + 4 * s) + be16(self.scripts[s]['exportoff']) + struct.pack('>I', self.locals(s)))
            w(HANDLES + 4 * s, struct.pack('>I', self.codeaddr(s, 0)))
            w(self.codeaddr(s, 0), self.scripts[s]['code'])
            w(self.locals(s), self.rng.randbytes(512))
        w(GLOB - 0x8000, self.rng.randbytes(0x10000))
        w(STKR, self.rng.randbytes(0x40000))
        w(STK, be16(0))
    def unloaded(self, c): return hash((self.seed, c.clsid)) % 3 == 0
    def locals(self, s): return LOCR + 0x20000 + 0x1000 * s
    def codeaddr(self, s, slot): return CODE + 0x80000 * slot + 0x8000 * s

# ---- running one interpreter --------------------------------------------------------------
class Run:
    def __init__(self, world, entry):
        self.w = world; self.log = []; self.error = None; self.slot = 0; self.calls = 0; self.fault = None; self.orig = entry == BO + 0x402
        mu = self.mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_M68000)
        for b, sz in ((BO, 0x10000), (B23, 0x10000), (BH, 0x10000), (KSTUB, 0x10000), (DATA, 0x10000), (LOCR, 0x40000),
                      (GLOBR, 0x20000), (STKR, 0x40000), (HEAP, 0x10000), (CODE, 0x100000), (SSTK, 0x10000)): mu.mem_map(b, sz)
        world.image(mu, entry)
        mu.hook_add(UC_HOOK_CODE, self.stub, begin=KSTUB, end=KSTUB + 0x300)
        self.trace = []
        if TRACE is not None: mu.hook_add(UC_HOOK_CODE, self.tracer, begin=BO if entry == BO + 0x402 else BH, end=(BO if entry == BO + 0x402 else BH) + 0x10000)
    def tracer(self, mu, addr, size, ud):
        if self.rd(addr, 4) == b'\x12\x18\xd2\x41':          # the dispatch fetch, not an operand fetch
            a0 = mu.reg_read(UC_M68K_REG_A0)
            self.trace.append((a0, self.rd(a0, 1)[0], mu.reg_read(UC_M68K_REG_A2), struct.unpack('>H', self.rd(A4 + G['ACC'], 2))[0] if entry_is_orig(self) else mu.reg_read(UC_M68K_REG_D7) & 0xffff, mu.reg_read(UC_M68K_REG_D2) & 0xffff))
    def rd(self, a, n): return bytes(self.mu.mem_read(a, n))
    def gl(self, name, fmt): return struct.unpack(fmt, self.rd(A4 + G[name], struct.calcsize(fmt)))[0]
    def stub(self, mu, addr, size, ud):
        sp = mu.reg_read(UC_M68K_REG_A7)
        if addr < KSTUB + 0x200:                                # kernel function n
            n = (addr - KSTUB) // 2
            args = struct.unpack('>I', self.rd(sp + 4, 4))[0]
            argc = struct.unpack('>h', self.rd(args, 2))[0]
            vals = list(struct.unpack('>%dh' % max(0, min(argc, 8)), self.rd(args + 2, 2 * max(0, min(argc, 8)))))
            self.log.append(('k', n, argc, vals))
            acc = (n * 7919 + sum(vals) * 31 + len(self.log)) & 0xffff
            mu.mem_write(A4 + G['ACC'], be16(acc))
            self.calls += 1
            if self.calls % 3 == 0: self.move()
            self.clobber(mu)
        elif addr == V_LOADSCRIPT:
            n = struct.unpack('>h', self.rd(sp + 4, 2))[0]
            self.log.append(('ls', n)); self.calls += 1
            if self.calls % 2 == 0: self.move()
            a2 = mu.reg_read(UC_M68K_REG_A2); self.clobber(mu); mu.reg_write(UC_M68K_REG_A2, a2)   # Prog relies on this one keeping a2
            mu.reg_write(UC_M68K_REG_D0, STRUCTS + 0x20 * (n if 0 <= n < self.w.nscripts else 0))
        elif addr == V_LOADCLASS:
            n = struct.unpack('>h', self.rd(sp + 4, 2))[0]
            self.log.append(('lc', n))
            for c in self.w.classes:
                if c.script == n: mu.mem_write(CLASSTBL + 4 * c.clsid, be16(near(c.addr)))
            self.move(); self.clobber(mu)
        elif addr == V_ERROR:
            pc, st, code, extra = struct.unpack('>IIHH', self.rd(sp + 4, 12))
            self.error = (pc, st, code, extra if code in (0, 2, 3, 4, 5) else None); mu.emu_stop()   # 1/7/8 push no extra word
    def clobber(self, mu):
        for i, r in enumerate(REGS):
            if r != UC_M68K_REG_A4 and r != UC_M68K_REG_A5: mu.reg_write(r, 0xdead0000 + i * 0x11111 + self.calls)
    def move(self):                                             # every script's code to the other slot
        new = self.slot ^ 1
        for s in range(self.w.nscripts):
            old = struct.unpack('>I', self.rd(HANDLES + 4 * s, 4))[0]
            assert old == self.w.codeaddr(s, self.slot)
            self.mu.mem_write(self.w.codeaddr(s, new), self.rd(old, len(self.w.scripts[s]['code'])))
            self.mu.mem_write(HANDLES + 4 * s, struct.pack('>I', self.w.codeaddr(s, new)))
        self.slot = new
    def go(self):
        mu = self.mu
        for i, r in enumerate(REGS): mu.reg_write(r, 0x11110000 + i)
        mu.reg_write(UC_M68K_REG_A4, A4); mu.reg_write(UC_M68K_REG_A5, 0x11115555)
        mu.reg_write(UC_M68K_REG_A0, self.w.codeaddr(0, 0) + self.w.bodies[0].off); mu.reg_write(UC_M68K_REG_A2, STK)
        mu.mem_write(SSP, struct.pack('>I', RET)); mu.reg_write(UC_M68K_REG_A7, SSP)
        try: mu.emu_start(H1B + 6 * 3, RET, count=3000000)
        except UcError as e: self.fault = str(e)
        self.pc = mu.reg_read(UC_M68K_REG_PC)
        self.timeout = not self.fault and not self.error and self.pc != RET
    def state(self):
        mu = self.mu
        regs = {r: mu.reg_read(r) for r in REGS}
        if self.fault and not self.orig: mu.mem_write(A4 + G['ACC'], be16(regs[UC_M68K_REG_D7]))   # acc lives in d7 until a call-out
        h1 = bytearray(self.rd(H1B, 0x31ac)); h1[18:24] = bytes(6)                 # vector 3 differs by design
        for lo, hi in ((0xd3c, 0xd90), (0xd94, 0xd98), (0xecc, 0xece), (0x30c0, 0x30c4)):  # debug send stack and its pointer,
            h1[lo:hi] = bytes(hi - lo)                                                  # SUPER, -$4f3e: not kept by pmachine.S
        return dict(regs=(regs[UC_M68K_REG_A0], regs[UC_M68K_REG_A2]),      # d2 (prev): pm_entry restores the caller's; checked by the trace
                    h1=bytes(h1), heap=self.rd(HEAP, 0x10000), stk=self.rd(STKR, 0x40000), loc=self.rd(LOCR, 0x40000),
                    glob=self.rd(GLOBR, 0x20000), code=self.rd(CODE, 0x100000), log=self.log, error=self.error, fault=self.fault,
                    slot=self.slot, pc=self.pc if self.error else None)

bad = 0; stats = dict(ok=0, err=0, fault=0, loops=0)
for k in ([TRACE] if TRACE is not None else range(N)):
    rng = random.Random(SEED * 100003 + k); w = World(rng); w.seed = SEED * 100003 + k
    w.rng = random.Random(w.seed + 7)       # image randomness, identical for both runs
    ra = Run(w, BO + 0x402); ra.go(); w.rng = random.Random(w.seed + 7)
    rb = Run(w, PMENTRY); rb.go()
    sa, sb = ra.state(), rb.state()
    if ra.timeout or rb.timeout: stats['loops'] += 1; continue       # ran into the instruction limit (bad export etc.)
    if sa['error']: stats['err'] += 1
    elif sa['fault']: stats['fault'] += 1
    else: stats['ok'] += 1
    diff = [n for n in sa if sa[n] != sb[n]]
    if TRACE is not None:
        ta, tb = ra.trace, rb.trace
        print('trace lengths', len(ta), len(tb), 'diff', diff)
        blocks = [(w.codeaddr(s, sl), w.codeaddr(s, sl) + len(w.scripts[s]['code'])) for s in range(w.nscripts) for sl in (0, 1)]
        out = [i for i, x in enumerate(ta) if not any(lo <= x[0] < hi for lo, hi in blocks)]
        if out:
            i = out[0]; print('PC leaves the script code at step', i)
            for j in range(max(0, i - 14), min(i + 2, len(ta), len(tb))): print('  %5d  orig pc=%x op=%02x a2=%x acc=%04x d2=%04x | new pc=%x op=%02x a2=%x acc=%04x d2=%04x' % ((j,) + ta[j] + tb[j]))
            print('  bytes at', hex(ta[max(0, i-1)][0]), ra.rd(ta[max(0, i-1)][0], 12).hex())
        for i in range(min(len(ta), len(tb))):
            if ta[i] != tb[i] or i > len(ta) - 3:
                for j in range(max(0, i - 12), min(i + 3, len(ta), len(tb))): print('  %5d  orig pc=%x op=%02x a2=%x acc=%04x d2=%04x | new pc=%x op=%02x a2=%x acc=%04x d2=%04x' % ((j,) + ta[j] + tb[j]))
                break
    if diff:
        bad += 1
        if bad <= 5:
            print('MISMATCH world', k, 'in', diff, 'errors', sa['error'], sb['error'], 'faults', sa['fault'], sb['fault'], 'pc', hex(sa['pc'] or 0), hex(sb['pc'] or 0))
            if 'regs' in diff: print('  regs', [hex(x) for x in sa['regs']], [hex(x) for x in sb['regs']])
            if 'log' in diff: print('  log', len(sa['log']), len(sb['log']), sa['log'][:6], sb['log'][:6])
            for n in diff:
                if isinstance(sa[n], bytes):
                    d = [i for i in range(len(sa[n])) if sa[n][i] != sb[n][i]]
                    print('  %s: %d bytes differ, first at +%x: %s vs %s' % (n, len(d), d[0], sa[n][d[0]:d[0]+8].hex(), sb[n][d[0]:d[0]+8].hex()))
print(N, 'worlds:', stats, '-', bad, 'mismatches')
