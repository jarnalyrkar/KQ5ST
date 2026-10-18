"""Link an ELF image twice (base 0 and base DELTA) and turn it into a TOS PRG with fixups.

    elf2prg.py OUT.PRG LD_COMMAND...      (LD_COMMAND must contain the literal token @OUT@)
Also writes OUT.sym (nm-style symbols, text-relative) for the Hatari debugger.
"""
import os, subprocess, struct, sys
DELTA = 0x01000000
out, ldcmd = sys.argv[1], sys.argv[2:]
tmp = out + '.tmp'
def link(base, name):
    cmd = [a.replace('@OUT@', name) for a in ldcmd] + [f'-Ttext={base:#x}']
    subprocess.run(cmd, check=True)
    subprocess.run(['m68k-linux-gnu-objcopy', '-O', 'binary', '-j', '.text', '-j', '.data', name, name + '.bin'], check=True)
    syms = {}
    for line in subprocess.run(['m68k-linux-gnu-nm', '-n', name], check=True, capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 3: syms[p[2]] = (int(p[0], 16), p[1])
    return open(name + '.bin', 'rb').read(), syms
a, sa = link(0, tmp + '0.elf'); b, sb = link(DELTA, tmp + '1.elf')
assert len(a) == len(b)
tsize = sa['__data_start'][0]; dsize = len(a) - tsize
bsize = sa['__bss_end'][0] - sa['__bss_start'][0]
assert sa['__bss_start'][0] == len(a), (hex(sa['__bss_start'][0]), hex(len(a)))
relocs = []; off = 0
while off + 4 <= len(a):
    x, y = struct.unpack('>I', a[off:off+4])[0], struct.unpack('>I', b[off:off+4])[0]
    if (y - x) & 0xffffffff == DELTA: relocs.append(off); off += 4
    else: off += 2
fix = bytearray()
if relocs:
    fix += struct.pack('>I', relocs[0])
    for p, q in zip(relocs, relocs[1:]):
        d = q - p
        while d > 254: fix.append(1); d -= 254
        fix.append(d)
    fix.append(0)
else:
    fix += b'\0\0\0\0'
hdr = struct.pack('>HIIIIIIH', 0x601a, tsize, dsize, bsize, 0, 0, 0, 0)
open(out, 'wb').write(hdr + a + fix)
with open(os.path.splitext(out)[0] + '.sym', 'w') as f:
    for n, (v, t) in sorted(sa.items(), key=lambda x: x[1][0]):
        if t.upper() in 'TDB': f.write(f'{v:08x} {t.upper()} {n}\n')
for e in ('0.elf', '1.elf', '0.elf.bin', '1.elf.bin'): os.remove(tmp + e)
print(f'{out}: text {tsize} data {dsize} bss {bsize}, {len(relocs)} relocations')
