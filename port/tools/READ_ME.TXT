KING'S QUEST V - ATARI ST          unofficial fan port, version @VERSION@
=====================================================================

Sierra announced an Atari ST version of King's Quest V for spring 1991 and
cancelled it. This is a fan reconstruction: the Amiga version's interpreter
running on TOS through a small AmigaOS stand-in, with the PC EGA artwork and
YM2149 sound. It is a work in progress (see "Known problems").

Project page and source: https://github.com/jarnalyrkar/KQ5ST


REQUIREMENTS
------------
- Atari STE recommended (uses the blitter); a plain ST works, a bit slower.
- 4 MB RAM (the only size tested so far).
- Colour monitor, low resolution.
- A hard disk, or a GEMDOS hard-disk folder in an emulator. About 15 MB.
  There is no floppy version yet.
- Tested on TOS 1.62 in Hatari. Other TOS versions and EmuTOS untested.


INSTALLING
----------
Copy the KQ5ST folder anywhere on a hard-disk partition and run KQ5ST.PRG.
The game finds its files in the folder it was started from.

Hatari (tested):
  hatari --machine ste --memsize 4 --tos <your TOS 1.62 image> \
         --harddrive KQ5ST --auto 'C:\KQ5ST.PRG'
  Or in the GUI: System = STE, Memory = 4 MB, Hard disks -> GEMDOS drive =
  the KQ5ST folder, then double-click KQ5ST.PRG on drive C.
  Turn off Hatari's joystick emulation with keys, or keypad 8/5/4/6 won't
  reach the game.

Steem SSE (untested): STE, 4 MB, Disk Manager -> Hard Drives -> map C: to
  the KQ5ST folder, then run KQ5ST.PRG from drive C.

Real hardware (untested): copy the KQ5ST folder to your hard disk (ACSI, SD
  adapter such as UltraSatan / ACSI2STM, or similar) and run KQ5ST.PRG.


CONTROLS
--------
Mouse as on the Amiga/PC: left button acts with the current cursor, right
button cycles the cursors, move to the top of the screen for the icon bar.
- Double-click: Graham walks there at once (at a screen edge: next room).
- Esc, or both mouse buttons: skip the Sierra logo / title; in the game
  Esc opens the icon bar.
- Keypad as in the PC manual: digits move the pointer (or walk Graham with
  the walk cursor), 5 cycles cursors, 0 = Insert, . = Delete (icon bar),
  Enter = act.
- Saved games are written to the game folder (KQ5sg.*).


KNOWN PROBLEMS
--------------
- Play-tested through the opening and the town. Later rooms may crash.
- Music runs at 50 Hz (about 17% slow); no percussion; some sounds silent.
- Rooms that scroll sideways would crash (not met yet).
- Copy protection is removed, as in the later CD release.
Please report problems on the project page.


COPYRIGHT
---------
King's Quest V (c) 1990 Sierra On-Line, Inc. The game data, the artwork
and the interpreter inside KQ5ST.PRG are Sierra's; the rights now belong to
Activision (Microsoft). This is a non-commercial fan project, not affiliated
with or endorsed by them. If you enjoy it, buy King's Quest V (GOG, Steam).
The port's own code is GPL-3.0-or-later; source on the project page.
