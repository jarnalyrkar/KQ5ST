#!/bin/sh
# Assemble st/src/pmachine.S with test stand-ins at 0x300000 for pmtest.py; prints "BIN ENTRY".
# pmbuild.sh DIR [safe]: "safe" tests the movep-free copy (-DPM_SAFE, entry pm_entry_safe; 68060).
set -e
. "$HOME/.local/opt/m68k-gcc/env.sh"
T=${1:-/tmp/pmtest}; mkdir -p $T
ENTRY=pm_entry; SAFE=
m68k-linux-gnu-gcc-15 -m68000 -c st/src/pmachine.S -o $T/pm.o
if [ "$2" = safe ]; then
    m68k-linux-gnu-gcc-15 -m68000 -DPM_SAFE -c st/src/pmachine.S -o $T/pm_safe.o
    SAFE=$T/pm_safe.o; ENTRY=pm_entry_safe
fi
m68k-linux-gnu-as -m68000 tools/equiv/pmtstub.S -o $T/stub.o
m68k-linux-gnu-ld -Ttext=0x300000 --defsym hunk1=0x400100 -o $T/pm.elf $T/pm.o $SAFE $T/stub.o 2>&1 | grep -v "RWX permissions\|_start" >&2 || true
m68k-linux-gnu-objcopy -O binary $T/pm.elf $T/pm.bin
echo $T/pm.bin $(m68k-linux-gnu-nm $T/pm.elf | awk -v e=$ENTRY '$3 == e {print $1}')
