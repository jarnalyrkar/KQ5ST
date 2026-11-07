#!/bin/sh
# Assemble st/src/pmachine.S with test stand-ins at 0x300000 for pmtest.py; prints "BIN ENTRY".
set -e
. "$HOME/.local/opt/m68k-gcc/env.sh"
T=${1:-/tmp/pmtest}; mkdir -p $T
m68k-linux-gnu-gcc-15 -m68000 -c st/src/pmachine.S -o $T/pm.o
m68k-linux-gnu-as -m68000 tools/equiv/pmtstub.S -o $T/stub.o
m68k-linux-gnu-ld -Ttext=0x300000 --defsym hunk1=0x400100 -o $T/pm.elf $T/pm.o $T/stub.o 2>&1 | grep -v "RWX permissions\|_start" >&2 || true
m68k-linux-gnu-objcopy -O binary $T/pm.elf $T/pm.bin
echo $T/pm.bin $(m68k-linux-gnu-nm $T/pm.elf | awk '/ pm_entry$/{print $1}')
