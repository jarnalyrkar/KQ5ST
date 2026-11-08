#!/usr/bin/env python3
"""Make a test copy of the game folder that starts in Dink's labyrinth square:  mkdinktest.py OUTDIR
Copies st/hd (no saves, no flag files), turns the debug keys on (0.SCR version check 'x' -> '1',
WORKFLOW.md "Jumping to any room") and applies test-only patches to 55.SCR so that a debug
teleport to room 55 reaches the tambourine scene without inventory or maze walking:
  * rm055::init drops Graham into square (3,1), one of the four Dink squares, instead of (3,5);
  * `(Load VIEW 874 1060)` in init becomes `(gEgo get: 34)` (the tambourine);
  * the hug rectangle of mainDinkScript::doit starts at x 250 instead of 150 (the drop-in lands
    Graham inside it; a normal entry from a neighbouring square does not);
  * dink::handleEvent runs the tambourine branch on the Talk verb (keypad 5 three times, then a
    click on Dink), since the inventory cursor cannot be selected headless.
Run with st/tests/dink_leave.txt (player report 2026-11-08: leaving the square without the
hairpin soft-locked the game). Never ship this folder."""
import os, shutil, sys
HD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'st', 'hd')
SKIP = ('KQ5sg.', 'SHOT', 'AUTO.TXT', 'HELLO.PRG', 'KQ5ST.sym', 'NOSND', 'NOBLIT', 'KTRACE', 'YM_TRACE', 'MT32')

def patch(d, off, old, new):
    o = off + 2                                         # 2-byte patch-file header
    assert d[o:o+len(old)] == old, '+%x: expected %s, found %s' % (off, old.hex(), d[o:o+len(old)].hex())
    assert len(new) == len(old); d[o:o+len(new)] = new

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    for f in os.listdir(HD):
        if not f.startswith(SKIP): shutil.copy(os.path.join(HD, f), out)
    p = os.path.join(out, '0.SCR'); d = bytearray(open(p, 'rb').read())
    i = d.find(bytes.fromhex('3635781a300700')); assert i > 0
    d[i + 2] = 0x31; open(p, 'wb').write(d)
    p = os.path.join(out, '55.SCR'); d = bytearray(open(p, 'rb').read())
    patch(d, 0x016a, b'\x35\x05', b'\x35\x01')                                   # (= global385 1)
    patch(d, 0x004e, bytes.fromhex('3903388000386a0338240443 0006'.replace(' ', '')),
          bytes.fromhex('38440178392281004a06 32010000'.replace(' ', '')))        # (gEgo get: 34); jmp +1
    patch(d, 0x0cca, b'\x38\x96\x00', b'\x38\xfa\x00')                           # inRect x 150 -> 250
    patch(d, 0x25f7, b'\x35\x04', b'\x35\x05')                                   # verb 4 -> 5 (Talk)
    patch(d, 0x260f, b'\x35\x22\x1a', b'\x35\x00\x0c')                           # ldi 34; eq? -> ldi 0; not
    open(p, 'wb').write(d); print('wrote', out)

if __name__ == '__main__': main()
