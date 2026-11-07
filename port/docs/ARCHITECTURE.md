# Architecture: the Amiga interpreter on TOS

Index: [`README.md`](README.md). Interpreter internals: [`AMIGA_PROG.md`](AMIGA_PROG.md).

The Amiga KQ5 interpreter `Prog` (1.004.018) is converted hunk by hunk into a TOS program
together with a shim that stands in for the parts of AmigaOS it uses (exec, dos, graphics,
intuition) and for the hardware it touches (blitter, mouse/joystick registers). The game runs
with the Amiga scripts (the interpreter hard-codes their selector numbers, AMIGA_PROG.md) and
EGA art substituted through SCI patch files (GRAPHICS.md). Prog runs in supervisor mode.

## Pieces

| File | Role |
|---|---|
| `tools/hunk2gas.py` | Prog hunks → GNU as source; relocations become symbol references; applies `st/patches/prog.patch` |
| `tools/elf2prg.py` | links twice (base 0 / base $1000000), diffs to find fixups, writes the TOS PRG and a symbol file; also copies the fixup table into `.data` (`reloc_copy`) |
| `st/src/glue.S` | entry, `run_prog` (Super mode, AmigaDOS-style start), LVO stub macro, trap #5, VBL dispatch, IKBD byte entry (`ikbd_handler`) and mouse packet handler, silent sound driver (`NOSND` file), `HOOK` macro |
| `st/src/shim.c` | hooks into Prog (kernel trace, GetEvent poll, ...) |
| `st/src/exec.c` | exec.library: libraries with real jump tables, process "SCI", ports, signals, interrupts, tasks (recorded, not run) |
| `st/src/dos.c` | dos.library on GEMDOS; AmigaDOS paths resolved against the start directory; cache of the game folder (names, attributes, sizes; files written are re-asked from GEMDOS) and 6 kept-open read-only handles, for real-disk speed |
| `st/src/display.c` | graphics/intuition stand-ins; Amiga 5-plane bitmap → ST 4-plane screen conversion; pointer; screenshots (GRAPHICS.md) |
| `st/src/blit.c` | rectangle engine and Graph priority/control fill: STE blitter or CPU (GRAPHICS.md) |
| `st/src/blitter.c` | STE blitter access (detected with Blitmode, shared-bus restart loop) |
| `st/src/input.c` | ST mouse/keyboard → SCI events, IKBD decoder, event ring, autoplay script (INPUT.md) |
| `st/src/memory.c` | AllocMem/FreeMem on one big GEMDOS block |
| `st/src/ym.c` | SCI sound driver for the YM2149 with the `amiga3v.drv` interface (SOUND.md) |
| `st/src/mt32.c` | SCI sound driver for a Roland MT-32 on the MIDI port, picked by a file `MT32` in the game folder (SOUND.md "MT-32") |

The TOS `.PRG` format also uses absolute 32-bit relocation, so the hunks are concatenated into
TEXT/DATA/BSS with a merged fixup table. GCC's m68k ABI returns pointers in a0 (all TOS wrappers
copy d0 to a0).

**Longword alignment (v0.1.1 crash on real hardware/Steem, fixed 2026-10-20).** AmigaDOS BPTRs
(address >> 2: `LoadSeg`'s seglist, locks, file handles) need longword-aligned objects, and the
static ones (`ym_seg`, `silent_seg`, `con_in`/`con_out`) sit in the image. TOS only word-aligns
the program: Hatari's GEMDOS drive happened to give 0 mod 4 (`$1ac40`), TOS's own GEMDOS on an
AHDI disk gave 2 mod 4 (`$1e542`). Prog then called the sound driver 2 bytes off, re-ran its own
start-up a few times (repeated "SCIport created") and ended in a jump to 0, where the ROM's
`bra.s $30` gives "illegal instruction at $000030". `_start` (glue.S) now moves the image up 2
bytes when needed and re-applies the fixups from `reloc_copy` (mover runs on the stack). Reproduce
with `tools/acsiput.py` (WORKFLOW.md "Real hard-disk test").

## Prog patches (`st/patches/prog.patch`)

Byte patches, `JMP:symbol` redirections and `RELADD` entries applied by `hunk2gas.py`; hooks that
resume mid-function use the `HOOK` macro in `glue.S`.

- ExecBase reads from address 4 (`movea.l $4.w,a6`, `movea.l #4,a0; movea.l (a0),a6`) → `trap #5`.
- Blitter users → CPU/STE-blitter code: hunk 52 `+$872` (rectangle engine), hunk 55 `+$128`
  (pri/ctl fill). Still Amiga: ShiftScreen, hunk 52 `+$3e8` (GRAPHICS.md).
- Joystick poll hunk 16 `+$160` → `c_input_poll` (INPUT.md).
- `IsObject` (hunk 23 `+$534`): NULL check before reading the magic word.
- Handle header flags (hunk 59 `+$9ea`, `+$a0c`, called in pairs by DoSound, hunk 31): skipped when
  `*handle` is NULL (purged). Restoring a save in room 11 (bees, bear) hit `-2(NULL)` → bus error at
  `H59_a1e`, seen by players as a lock-up (2026-10-21).
- kSetCursor with a position (hunk 17 `+$aa`): moved the pointer via input.device on the Amiga; hooked.
- Bytecode interpreter: hunk 4 `+$402` (vector 3, the interpreter loop) → `pm_entry` in
  `st/src/pmachine.S`, which also replaces `send` (below) and carries the `KTRACE` kernel-call
  trace that was a hook at `+$9ee` before.
- Speed: next-fit free-handle search (hunk 59 `+$c16`), verified property-lookup cache in send
  (hunk 23 `+$22c`, used by the C-level Send only now), plane 4 skipped in blits and pixel plots
  (GRAPHICS.md "Performance").

## Bytecode interpreter (`st/src/pmachine.S`, 2026-11-07)

The SCI "PMachine" of Prog is hunk 4 (opcode dispatch loop `+$402`, ~100 handlers, call frame
`+$308`, calle helper `+$2a8`) and hunk 23 (`send` `+$152`/`+$312`, the C-callable Send `+$324`,
the script loader's relocation). Both were rewritten for the ST; what follows is what they do,
since the rewrite keeps every observable effect (checked with `tools/equiv/pmtest.py`,
WORKFLOW.md "Equivalence tests").

- **Entry.** Hunk 23's send runs a method with `jsr -$7fec(a4)` (vector 3 = hunk 4 `+$402`):
  a0 = code, a2 = SCI stack; the method's `ret` is an `rts`. Only sends made by bytecode go
  through `pmachine.S`'s own send; the C-level Send (hunk 23 `+$324`, used by a few kernel
  functions) keeps Prog's code and enters the loop through `pm_entry`.
- **Registers while bytecode runs.** Prog: a0 = PC, a2 = SCI stack top (the top word; push =
  `addq #2,a2` then store), a6 = dispatch table, d2 = `prev` (the acc of the last comparison,
  pushed by `pprev`), acc and all base pointers in A4 globals. `pmachine.S` adds a3 = globals
  base, a5 = self and d7 = acc, written back to the globals before every call out of the loop
  and reloaded after it (kernel functions return their result by writing `-$7134`).
- **Globals** (A4-relative): `-$7134` acc, `-$7164` rest (bytes pushed by `&rest`, added to the
  next call frame's argc), `-$7168` params (→ argc word of the frame), `-$716c` temps, `-$7170`
  locals, `-$7174` globals (script 0 locals), `-$7150` script handle (`*handle` = code base),
  `-$7148` script number, `-$7160` self, `-$715c` class table (per class: near pointer of the
  class object or 0, script number), `-$5912` heap base (SCI "near" pointers are word offsets
  from it, 0 = NULL), `-$717c`/`-$7178` stack base/limit, `-$7180` saved stack top, `-$7184`
  PC at the last kernel call, `-$7144` PC of the last `callk`, `-$7626` highest kernel number,
  `-$7816` kernel table. Debug only (not maintained by `pmachine.S`): the send stack `-$726a`
  (entries at hunk 1 `+$d3c..$d90`), `-$7132` (superclass of the object being sent to), `-$4f3e`.
- **Operands** are little-endian in the bytecode (read byte-wise, `movep`); the tables the
  loader byte-swaps in place (selector lists, method dictionaries, export tables) are big-endian.
- **Scripts can move.** A kernel call or a script load may move any script's code, so across
  such calls the PC is kept as an offset from the current script's code base and rebased after
  (or, if the handle is NULL by then, the old absolute PC is used). `calle`/`callb` switch script
  handle, script number and locals for the callee; `call` keeps them.
- **Objects.** At `obj-10` the magic `$1234`, `-8` near pointer of the object's script struct
  (`+$a` handle, `+$e` export table offset, `+$10` locals), `-6` offset of its method dictionary
  in that script's code, `-4` script struct of the class whose selector list it uses, `-2`
  property count; property 0 = offset of that selector list, property 1 = near pointer of the
  superclass. A method dictionary is `count` at `-2`, `count` selectors, a word, then the method
  offsets. An export table is `count`, then 4-byte entries whose first word is the offset.
- **send** (frame on the SCI stack: selector, argc, args, repeated; the frame byte is the frame
  size, `&rest` bytes are added): for each selector the class's selector list is searched
  (cached, `tabfind`); found → with argc 0 acc = the property, otherwise the property = the first
  argument. Otherwise the method dictionaries of the object, then of each superclass (property 1)
  are scanned; found → the method runs with params = this selector's argc word, the script
  handle of that class's script and its locals, temps saved; not found → PError 5. After the
  send a2 = the stack top before the frame. `self` sends to self with self unchanged, `super n`
  to class n with self unchanged, `send` makes the object self for the call.
- **Errors** go to PError (vector 189, hunk 61 `+$98`, prints the box and exits): 0 export out of
  range, 1 unknown opcode, 2 kernel number out of range, 3 class not loaded, 4 not an object,
  5 selector not found, 7 divide by zero, 8 stack overflow (`link`).
- **Kept from Prog on purpose**: `div`/`mod` by `divs`, `mod` results 0 .. |acc|-1; `shr`/`shl`
  by acc mod 64; `callk`'s saved a2/a0 and the argc fix-up by `&rest`; the stale a0 (the method
  dictionary) that PError 4/5 get from inside the class chain.

## AmigaOS calls

New calls show up as `FATAL: unimplemented <lib> LVO -n called from H..` in the log; add a
`c_<Name>` function and a `set_lvo` entry (the stub list `src/lvos.inc` is generated by
`build.sh` from every `stub_<Name>` referenced). Library bases and the calls Prog makes per
library are listed in AMIGA_PROG.md "OS library bases".

## Loader message (what the Amiga `kq5` loader sent to "SCIport")

`+$14` seglist, `+$18` game-directory lock, `+$1c` loader splash screen (closed by Prog),
`+$20/+$24` sound data, `+$28` block freed with fixed size `$2f9b8`, `+$2c/+$30` heap reservation
(`$36da6`), `+$34` PAL flag (0 = 200 lines, which the ST needs).

## Interfaces discovered

- Video driver (hunk 52) function table at `+0`: `$04` init, `$08` shutdown, `$0c` clear,
  `$10/$14` cursor counter, `$1c` set pointer, `$20` shake, `$24` ShiftScreen (blitter, not yet replaced).
- Sound driver (`*.drv`, entry = seglist+4, `d7` = function 0–17, arguments d0/d1/a0, results
  d0/d1): SOUND.md. `LoadSeg("amigasnd.drv")` returns the shim's YM driver segment.
- SCI event: type.w, message.w, modifiers.w, time.l, y.w, x.w; post = hunk 14 `+$1a4`; GetEvent
  = hunk 14 `+$58`; queue head/tail at `-$71cc`/`-$71c8(a4)`, 14-byte entries (INPUT.md).
- Input task "FerretTask" (hunk 15) is not run; the shim posts events itself.
- Mouse globals read by SCI's button tracking: `-$6e60` button, `-$6e62/-$6e64` position,
  window `+$c/+$e` (INPUT.md).
- Resources: Prog looks for loose patch files in the game directory (`N.p32`, `N.v32`, `N.SCR`,
  `N.snd`, ...) before the resource volumes; the port delivers all its changes that way.

## Memory

`AllocMem`/`FreeMem` run on one big GEMDOS block; SCI takes the largest free block as its heap.
Only tested with 4 MB (1 MB untested, HANDOFF gap 4).

## Supervisor mode and NULL reads

Amiga code often reads through NULL pointers (harmless on the Amiga); on the ST low memory is
readable in supervisor mode, so most of these are harmless here too. Reads of `-n(NULL)` (top
of the address space) fault and need individual patches like `IsObject` (a bus error at
`$fffffff6` or similar).

## Interrupts and timing

- Exit (2026-10-21): when Prog returns (Quit, incl. the game-over box), `shim_main` puts back the
  `$70` vector, Timer A (if the profiler ran), the exception vectors and trap #5, silences the YM,
  restores the IKBD vectors, screen, palette and resolution, then Pterm. Before this a real ST (or
  Hatari with `--natfeats no`) halted with a double bus error right after Quit; with NatFeats the
  emulator exits first, which hid it. Code that touches hardware or SR at exit needs `Supexec`
  (the shim is back in user mode after `run_prog`).
- The TOS VBL queue stopped calling our entry after a while; the shim runs the SCI tick server
  (Prog's VERTB server, registered through AddIntServer) from its own level-4 vector wrapper
  (`pcsample_entry`), which also samples PCs for the profiler.
- The tick was therefore the VBL: 50 Hz on a PAL ST where the Amiga NTSC interpreter expected
  60 (game and music 17 % slow). Since 2026-11-07 the AddIntServer servers run on MFP Timer B at
  59.94 Hz (`glue.S tick_dispatch`, `exec.c start_tick`); the VBL wrapper still runs the shim's
  own input/display work and stops calling the servers once the timer runs (SOUND.md "Tick rate").
- Software key repeat and the mouse globals are updated at interrupt time (INPUT.md).

## Distribution (open)

Resources are loose patch files on a hard-disk folder; floppies would need the resource volumes
rebuilt (and compression). Not started.
