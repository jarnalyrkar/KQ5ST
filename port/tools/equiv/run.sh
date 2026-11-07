#!/bin/sh
# Equivalence tests for Prog code replaced in glue.S (docs/WORKFLOW.md "Equivalence tests"):
# run Prog's original routine and the replacement on a 68000 model (Python unicorn, user site,
# so no -I) with random and edge-case inputs and compare every output. Run from port/.
set -e
. "$HOME/.local/opt/m68k-gcc/env.sh"
T=$(mktemp -d)
awk '/^\| Polygon geometry helpers/,/^\| Cel drawing/' st/src/glue.S | grep -v "^| Cel drawing" > $T/geo.S
m68k-linux-gnu-as -m68000 $T/geo.S -o $T/geo.o && m68k-linux-gnu-objcopy -O binary -j .text $T/geo.o $T/geo.bin
python3 tools/equiv/geotest.py $T/geo.bin
{ echo '.set hunk56, 0x100000'; awk '/^\| Cel drawing, opaque run/,/^\| IsObject/' st/src/glue.S | grep -v "^| IsObject"; } > $T/cel.S
m68k-linux-gnu-as -m68000 $T/cel.S -o $T/cel.o && m68k-linux-gnu-ld -Ttext=0x300000 -o $T/cel.elf $T/cel.o 2>/dev/null
m68k-linux-gnu-objcopy -O binary $T/cel.elf $T/cel.bin
python3 tools/equiv/celtest.py $T/cel.bin $(m68k-linux-gnu-nm $T/cel.elf | awk '/hook_celrun/{print $1}') ${1:-200}
python3 -I tools/equiv/tabproof.py
{ echo '.set hunk23, 0x200000'; echo '.set tabcache, 0x380000'; echo '.set propcache, 0x388000'
  awk '/^\| ---- selector-table lookup cache/,/^\t.bss/' st/src/pmachine.S | grep -v "^	.bss"
  awk '/^\| tabfind \(the fingerprinted/,/^3:\tjmp\thunk23\+0x232/' st/src/glue.S; } > $T/tab.S
m68k-linux-gnu-as -m68000 $T/tab.S -o $T/tab.o && m68k-linux-gnu-ld -Ttext=0x300000 -o $T/tab.elf $T/tab.o 2>/dev/null
m68k-linux-gnu-objcopy -O binary $T/tab.elf $T/tab.bin
python3 tools/equiv/sendtest.py $T/tab.bin $(m68k-linux-gnu-nm $T/tab.elf | awk '/hook_proplookup/{print $1}') ${2:-20000}
# the rewritten bytecode interpreter and send (st/src/pmachine.S) against Prog's hunks 4 and 23
python3 tools/equiv/pmtest.py $(tools/equiv/pmbuild.sh $T/pm) ${3:-150} 1
rm -rf $T
