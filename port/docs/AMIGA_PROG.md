# KQ5 Amiga interpreter (`Prog`) — reverse-engineering map

Index: [`README.md`](README.md). How the port runs this on TOS: ARCHITECTURE.md.

Interpreter version **1.004.018** (from the data hunk). Game data version 1.000.000.
Compiler: Manx Aztec C style — `link a5` stack frames, small-data globals via `A4`,
inter-hunk calls via absolute `jsr xxx.l` with RELOC32 entries.

## Why the Amiga scripts, not the DOS EGA ones

- DOS EGA (0.000.055, interpreter 1.000.058) is SCI1-early; the Amiga data (1.000.000) uses an
  SCI1-middle map (volume in the top 4 bits) and newer system scripts.
- None of the 150 shared scripts are identical; the Amiga set has ~40 extra system scripts.
- Kernel table: Amiga = DOS's 117 entries + DoAudio, DoSync, AvoidPath, Sort, ATan.
- Selectors: DOS 392, Amiga 549; 30 selectors used by the kernel are renumbered (init, dispose,
  new, top/left/bottom/right, ...). The interpreter hard-codes selector numbers, so it only runs
  its own scripts. Hence: Amiga interpreter + Amiga scripts, EGA art substituted.
- Fonts identical; cursors 48/49 identical; sounds still contain Tandy (device $13) tracks.

## Load structure

- `kq5` (7.7 KB, "Pixie 1.0"): loader. Opens dos/intuition/graphics/icon libraries,
  reads `resource.cfg`, loads `amigasnd.drv` and `9.pat`, creates a public message
  port **`SCIport`** and then runs `Prog`.
- `Prog` (156 KB): 63 hunks = 61 CODE + 1 DATA (hunk 1, 8292 bytes) + 1 BSS (hunk 2, 4 bytes).
  Entry: hunk 0 `jmp H62_1e` (C startup in hunk 62) → `main` at `H0_6`.
  `main` calls FindPort("SCIport") and copies a parameter block from the loader
  (fields +$14…+$3e: driver pointers, patch data, config) into A4 globals.

The TOS `.PRG` format also uses absolute 32-bit relocation, so the hunks can be
concatenated into TEXT/DATA/BSS with a merged fixup table.

## Data hunk landmarks (hunk 1)

| Offset | Contents |
|---|---|
| `0x0000` | 192 × `JMP abs.l` (6-byte) entry vectors into the code hunks |
| `0x07e8` | **Kernel function table**: 124 longword pointers, index = `vocab.999` order (122 named + 2 unnamed) |
| `0x184a` | Row-offset table, 200 words (filled at runtime) |
| `0x19da` | Row-offset table, 200 words (filled at runtime) |
| `0x1bcc` | Picture opcode handlers (hunk 55): entries 0–14 = opcodes `F0`–`FE`, 15–19 = `FE` sub-ops 0–4 (palette entries [skipped], **embedded cel** `H55_2f4`, set palette, priority table eq-dist, priority table explicit) |
| `0x1d70` | 32 per-colour pixel plot routines (hunk 56): set/clear bit `d5` in 5 planes at `(a3)+0/$1f40/$3e80/$5dc0/$7d00` |

Kernel → hunk highlights: most kernel glue is in **hunk 17**; MapKeyToDir/Joystick 14;
AddMenu/GetMenu/SetMenu 25; RestartGame 27; DoSound 31; motion (BaseSetter, DirLoop,
Bresen, Avoider) 32; Save/Restore 34; GetFarText 38; CheckFreeSpace/ValidPath/DeviceInfo 39;
DoAudio 43; Palette 53; **Graph 55**; debug functions 61. Run `tools/hunkmap.py` for the full table.

## OS library bases (A4 globals)

| Global | Library | Hunks | Calls seen (LVO) |
|---|---|---|---|
| `-$4e9a(a4)`, `$4.w` | exec | 29, 40, 52, 55, 62 | AllocMem/FreeMem/AvailMem, Forbid/Permit, Disable/Enable, AddIntServer/RemIntServer, FindTask, Wait, Alloc/FreeSignal, Add/RemPort, GetMsg/ReplyMsg/WaitPort, FindPort, Open/CloseDevice, DoIO, OpenLibrary/CloseLibrary |
| `-$4e96(a4)` | dos | 62 only | Open/Close/Read/Write/Input/Output/Seek/DeleteFile/Lock/UnLock/DupLock/Examine/ExNext/Info/CurrentDir/IoErr/LoadSeg/UnLoadSeg/Delay/ParentDir/IsInteractive |
| `-$4ebe(a4)` | intuition | 52, 62 | OpenScreen/OpenWindow/Close*, ShowTitle, SetPointer/ClearPointer, ViewAddress, ViewPortAddress |
| `-$68b6(a4)` | graphics | 52, 55 | LoadRGB4, InitRastPort, MrgCop, MakeVPort, LoadView, WaitTOF, InitBitMap, WaitBOVP, OwnBlitter/DisownBlitter |
| `-$4e78(a4)` | unknown | 62 | LVOs -78, -90, -96 |

## Direct hardware access

| Hunk | Hardware | Purpose |
|---|---|---|
| 16 | `$dff00c` JOY0DAT, `$bfe001` CIA-A PRA | mouse/joystick counters and fire buttons |
| 52 | `$dff000` blitter (5-plane loops, WaitBOVP per column) | ShiftScreen / scrolling picture transitions |
| 55 | `$dff000` blitter (BLTCON0 `$3ca`, modulo 320−w) | rectangle fill of the priority/control map |

## Screen buffers

Moved to GRAPHICS.md "Screen formats" (visual screen 5 separate planes, chunky priority/control map).

## Platform layer to replace for TOS (all done in the shim, see ARCHITECTURE.md)

1. Loader (`kq5`) and C runtime/OS wrappers (hunk 62): GEMDOS file I/O, memory, timer.
2. Display setup (hunk 52): ST video base/palette instead of View/ViewPort/copper.
3. Blitter users (hunks 52, 55): CPU versions (or the STE blitter).
4. Input (hunk 16 + IDCMP message handling): IKBD mouse/keyboard/joystick.
5. Interrupts (hunk 29, AddIntServer): ST VBL / Timer C.
6. Sound (hunk 31 + `amigasnd.drv`): YM2149 driver playing the Tandy (0x13) tracks (done, `st/src/ym.c`).
7. Serial debug (hunk 30, "open AmigaDOS AUX:"): can be stubbed.

## Open questions

- Library at `-$4e78(a4)`.
- How 32-colour art should become 16 colours: offline remap of views/pics/palette, or remap at draw time.

## Hunk table

| Hunk | Size | JMP vectors | Kernel functions | OS libs | Hardware | Strings |
|---|---|---|---|---|---|---|
| 0 | 604 | 3 |  |  |  |  |
| 3 | 772 | 0 |  |  |  |  |
| 4 | 8512 | 1 |  |  |  |  |
| 5 | 872 | 1 |  |  |  |  |
| 6 | 3420 | 6 |  |  |  |  |
| 7 | 1960 | 5 |  |  |  |  |
| 8 | 1300 | 5 | SetSynonyms |  |  |  |
| 9 | 1560 | 0 |  |  |  |  |
| 10 | 1084 | 0 |  |  |  |  |
| 11 | 0 | 0 |  |  |  |  |
| 12 | 3664 | 1 |  |  |  |  |
| 13 | 800 | 0 |  |  |  |  |
| 14 | 1020 | 3 | MapKeyToDir, Joystick |  |  |  |
| 15 | 1088 | 0 |  |  |  |  |
| 16 | 724 | 1 |  |  | CIA, custom |  |
| 17 | 11336 | 91 | Load, UnLoad, ScriptID, DisposeScript, Clone, DisposeClone, IsObject, RespondsTo, DrawPic, Show, PicNotValid, Animate … |  |  |  |
| 18 | 2960 | 2 |  |  |  |  |
| 19 | 1824 | 4 |  |  |  |  |
| 20 | 1356 | 0 |  |  |  |  |
| 21 | 4116 | 1 |  |  |  |  |
| 22 | 56 | 0 |  |  |  |  |
| 23 | 3544 | 4 |  |  |  |  |
| 24 | 212 | 0 |  |  |  |  |
| 25 | 5500 | 3 | AddMenu, GetMenu, SetMenu |  |  |  |
| 26 | 184 | 0 |  |  |  |  |
| 27 | 152 | 2 | RestartGame, GameIsRestarting |  |  |  |
| 28 | 36 | 1 |  |  |  |  |
| 29 | 584 | 0 |  | exec |  |  |
| 30 | 1124 | 0 |  |  |  | 'open AmigaDOS AUX:' |
| 31 | 4844 | 1 | DoSound |  |  | 'iga3v.drv'; 'O @?(' |
| 32 | 2560 | 6 | BaseSetter, DirLoop, InitBresen, DoBresen, DoAvoider, SetJump |  |  |  |
| 33 | 300 | 0 |  |  |  |  |
| 34 | 3024 | 5 | SaveGame, RestoreGame, GetSaveFiles, GetSaveDir, CheckSaveGame |  |  |  |
| 35 | 720 | 4 |  |  |  |  |
| 36 | 11824 | 0 |  |  |  |  |
| 37 | 8604 | 0 |  |  |  |  |
| 38 | 444 | 1 | GetFarText |  |  |  |
| 39 | 2264 | 3 | CheckFreeSpace, ValidPath, DeviceInfo |  |  |  |
| 40 | 184 | 1 |  | exec? |  |  |
| 41 | 900 | 0 |  |  |  |  |
| 42 | 48 | 0 |  |  |  |  |
| 43 | 1608 | 1 | DoAudio |  |  | ' audio hardware.' |
| 44 | 352 | 0 |  |  |  |  |
| 45 | 48 | 0 |  |  |  | ' there is no parser' |
| 46 | 48 | 0 |  |  |  | 'there is no parser' |
| 47 | 8 | 0 |  |  |  |  |
| 48 | 3496 | 0 |  |  |  | "in '%s'\n" |
| 49 | 2176 | 0 |  |  |  |  |
| 50 | 1876 | 0 |  |  |  | 'ation file: %s\nPlease run the Install program.\n' |
| 51 | 364 | 0 |  |  |  |  |
| 52 | 3184 | 2 |  | exec, graphics, intuition | custom |  |
| 53 | 1028 | 3 | Palette |  |  |  |
| 54 | 1524 | 5 |  |  |  |  |
| 55 | 8084 | 8 | Graph | exec, graphics | custom |  |
| 56 | 2108 | 1 |  |  |  |  |
| 57 | 20 | 0 |  |  |  |  |
| 58 | 2964 | 0 |  |  |  |  |
| 59 | 3268 | 6 |  |  |  | " D'h" |
| 60 | 156 | 0 |  |  |  |  |
| 61 | 752 | 9 | SetDebug, InspectObj, ShowSends, ShowFree, StackUsage, Profiler |  |  |  |
| 62 | 4732 | 2 |  | dos, exec, intuition, lib@-4e78 |  |  |
## Moved sections

- "Using DOS EGA art with the Amiga interpreter", "Colour conversion for Amiga-only art" and
  "EGA backgrounds in Amiga pictures" → GRAPHICS.md.
- "Sound driver interface (hunks 31, 37)" and the `amiga3v.drv` layout → SOUND.md.
