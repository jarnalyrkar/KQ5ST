#!/bin/sh
# Build KQ5ST.PRG: Amiga Prog (converted) + TOS shim. Run from anywhere.
set -e
cd "$(dirname "$0")"
. "$HOME/.local/opt/m68k-gcc/env.sh"
T=../tools; B=build; mkdir -p $B hd
# stubs: every stub_<name> used by the C sources or by JMP: patches gets a register-saving wrapper
{ grep -ohE "stub_[A-Za-z0-9_]+" src/*.c; grep -ohE "JMP:stub_[A-Za-z0-9_]+" patches/prog.patch | sed 's/JMP://'; } \
    | sed 's/stub_//' | sort -u | awk '{print "\tLVO " $1}' > src/lvos.inc
python3 -I $T/hunk2gas.py ../work/prog ../extracted/amiga_files/d0/Prog $B/prog.s patches/prog.patch
python3 -I - <<'PY'
import json, struct
d = open('../extracted/amiga_files/d0/Prog', 'rb').read(); L = lambda o: struct.unpack('>I', d[o:o+4])[0]
p = 4
while L(p): p += 4
p += 4; first, last = L(p + 4), L(p + 8); p += 12
alloc = [(L(p + 4 * i) & 0x3fffffff) * 4 for i in range(last - first + 1)]
offs, o = [], 0
for a in alloc: o = (o + 3) & ~3; offs.append(o); o += a
open('build/hunkstarts.inc', 'w').write('static const u32 hunk_off[] = {' + ','.join(map(str, offs)) + '};\nstatic const int hunk_count = %d;\n' % len(offs))
PY
CFLAGS="-m68000 -mstrict-align -fno-store-merging -O2 -ffreestanding -fno-builtin -nostdlib -fomit-frame-pointer -fno-pic -Wall -Wno-unused-function -Isrc -I$B"
for f in shim exec dos memory display blit blitter input ym; do m68k-linux-gnu-gcc-15 $CFLAGS -c src/$f.c -o $B/$f.o; done
for f in glue gemdos libgcc68k; do m68k-linux-gnu-gcc-15 $CFLAGS -c src/$f.S -o $B/$f.o; done
m68k-linux-gnu-as -m68000 $B/prog.s -o $B/prog.o
python3 -I $T/elf2prg.py hd/KQ5ST.PRG m68k-linux-gnu-ld -T src/tos.ld -o @OUT@ \
    $B/glue.o $B/shim.o $B/exec.o $B/dos.o $B/memory.o $B/display.o $B/blit.o $B/blitter.o $B/input.o $B/ym.o $B/gemdos.o $B/libgcc68k.o $B/prog.o
