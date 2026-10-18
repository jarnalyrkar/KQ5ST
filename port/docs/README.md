# KQ5 Atari ST port — documentation index

Start here in every new session. The documentation is split by area; each file is the single
place for its area, so read the one for what you are about to touch and add what you learn
there (date your additions). `HANDOFF.md` is the only file that tracks *state*; the others
describe how things work.

| File | Covers | Read it when |
|---|---|---|
| [`HANDOFF.md`](HANDOFF.md) | Current state per area, what the user has and has not tested, known gaps, next steps | First thing in a new session; update it when something is finished or learned |
| [`WORKFLOW.md`](WORKFLOW.md) | Build, run, headless test runs and autoplay scripts, debugging aids (crash dumps, unimplemented-call messages, `KTRACE`, `YM_TRACE`, script markers), profiling, Hatari configuration and the known headless-run problems | Before building, testing or debugging anything |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | How the Amiga interpreter runs on TOS: the shim's pieces, Prog byte patches, the loader message, discovered interfaces, memory, general lessons about the interpreter | Touching `st/src/*`, `st/patches/prog.patch`, adding an AmigaOS call, chasing a bus error |
| [`GRAPHICS.md`](GRAPHICS.md) | Art pipeline (EGA art inside Amiga resources, colour conversion, `makest.py`), screen formats, display/blitter code, performance work | Pictures, views, palette, `display.c` / `blit.c` / `blitter.c`, game speed |
| [`INPUT.md`](INPUT.md) | Mouse, keyboard and keypad (the IKBD decoder, key codes), what the game does with them, GetEvent and the event ring, double-click, both-buttons Esc | `input.c`, key codes, the pointer, anything the player presses |
| [`SCRIPTS.md`](SCRIPTS.md) | Game-script patches delivered as `N.SCR` files by `makescr.py` (speed default, double-click walk, title skips, keypad `kQPMouse`, copy protection) and how to find offsets with `scidisasm.py` | Changing game behaviour in SCI bytecode |
| [`SOUND.md`](SOUND.md) | The YM2149 driver (`ym.c`), the `amiga3v.drv` interface and Prog's sound code, patch 101, voices, which sounds play, listening tools (`sndvoices.py`), patched sounds (`makesnd.py`), tempo | `ym.c`, sound resources, music that sounds wrong |
| [`AMIGA_PROG.md`](AMIGA_PROG.md) | Reverse-engineering map of the Amiga interpreter `Prog`: hunks, data-hunk landmarks, OS library bases, direct hardware access, why the Amiga scripts are used with EGA art | Reading `work/prog/disasm/hunkNN.s`, locating a function or global in Prog |

## Which file for a task

- Something crashed or an AmigaOS call is missing → `WORKFLOW.md` (reading the log) then `ARCHITECTURE.md`.
- A room looks wrong → `GRAPHICS.md`; a key or click does the wrong thing → `INPUT.md`; the
  game should behave differently → `SCRIPTS.md`; music or an effect sounds wrong → `SOUND.md`.
- Where is X inside Prog → `AMIGA_PROG.md` (hunk table, kernel → hunk list, data landmarks).
- Tools are listed in [`../README.md`](../README.md) (one line each); the area files say how to use them.
- What a room or object script does → read its decompiled source first, in `../../amiga-decompiled/`
  (the Amiga game scripts as SCI source; see `SCRIPTS.md` "Decompiled Amiga scripts"), then get
  byte offsets with `scidisasm.py`.

## Conventions

- Dates are ISO (`2026-10-18`). "User-tested" means the user tried it in Hatari; "verified
  headless" means a `run.sh` run with a log/screenshot/trace, which is weaker (see the headless
  problems in `WORKFLOW.md`).
- Addresses: `hunk NN +$off` is an offset in a Prog hunk (`work/prog/disasm/hunkNN.s`),
  `-$xxxx(a4)` is a Prog global, `script N +$off` is an offset in an unpacked SCI script.
- The game folder is `st/hd/` (the emulated hard disk): `KQ5ST.PRG`, the resources, the
  generated patch files (`N.p32`, `N.v32`, `N.SCR`, `N.snd`) and the flag files `NOSND`,
  `NOBLIT`, `KTRACE`.
