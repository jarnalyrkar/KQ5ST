# Game-script patches (`tools/makescr.py` → `st/hd/N.SCR`)

Index: [`README.md`](README.md).

## Mechanism

Game scripts can be overridden by SCI patch files (`N.SCR`, header `$82 $00`); the Amiga release
itself ships `756.SCR`. `tools/makescr.py` holds tables of changes against the unpacked scripts
in `extracted/res_amiga/script` and writes the patch files (run `python3 -I tools/makescr.py
st/hd` after changing it):

- `PATCHES`: byte patches at an offset.
- `METHODS`: copies a method into a new code block appended to the script (before the relocation
  block), patches the class's method table to point at it, and replaces bytes in the copy with a
  `jmp` to a trampoline. Only relative branches are used; a copied method's `lofsa`/`call`
  operands would be wrong if they were absolute, so prefer `HOOKS` for methods that use them.
- `HOOKS`: in-place hook. Replaces the first bytes of a method with a `jmp` to a trampoline in a
  new code block; the trampoline runs the new code and the replaced bytes, then jumps back - the
  original method stays in place, so its `lofsa`/`call` operands are untouched.
- `MARKERS=1 makescr.py` plants `(Abs n)` probes in the trampolines (`with_markers`), which show
  up in the kernel trace (`KTRACE`, WORKFLOW.md).

Finding offsets: `tools/scidisasm.py extracted/res_amiga N [method]` prints objects, properties
and bytecode of a script (selector names from vocab 997, kernel names from vocab 999);
`@hex` as the filter disassembles code at any offset (`scidisasm.py res 996 @0894`), e.g. to
check a trampoline. To disassemble a generated `N.SCR`, strip the 2-byte header and symlink the
`vocab` folder next to a folder holding it. Its load/store opcode names were wrong before
2026-10-17 (`lsg` printed as `lagi`); fixed. The SCI `modifiers` word reaches scripts unmasked
(used by the double-click patch).

## Decompiled Amiga scripts

(2026-10-17) `amiga-decompiled/` in the project root (next to `port/`, not inside it) holds the
Amiga release's game scripts decompiled to SCI source by sluicebox: `X.sc` per script (class or
room name, e.g. `bakeShop.sc` = script 206, `rm001.sc`, `Motion.sc`, `Actor.sc`), plus `X.sco`
object files. The header line `(script# N)` gives the script number; message texts appear as
comments next to `PrintDC`. It matches the bytecode in `extracted/res_amiga` (checked on
script 206). Use it to see what a scene does and to find the object or state to patch:
`grep -il <word> amiga-decompiled/*.sc` finds the room, then `scidisasm.py` on that script and
method gives the offsets for `makescr.py`.

## NPC speeds

(2026-10-17) `moveSpeed: N` / `cycleSpeed: N` make an actor step / animate every N+1 cycles;
`Actor` defaults are 0, `xStep 3 yStep 2` (`Actor.sc`). Everything already runs about 2.4x slower
than the PC game (8.2 cycles/s against 20 with the rooms' 3-tick `Wait`), so a speed of 2 to 4 on
a long scripted walk becomes a wait of tens of seconds. The castle henchman copies ego's speed
(`castle.sc` ~1217), so the speed-default patch also makes him faster, as with the PC slider at
the top. Survey of the explicit settings of 2 or more on long walks (estimates at 8.2 cycles/s;
only 206 patched):

| Script | Who / what | Setting | Estimate |
|---|---|---|---|
| 206 `bakeShop` | woman + boy leave | 4/4 | ~25 s, **patched to 0** |
| 39 `rm039` | Graham (view 564) walks in from the west, then the owl leaves (cartoon) | 3/3, step 2x1 | ~50 s, owl ~25 s |
| 89 `rm089` | boat approaching (`boat` state 0) | 2, step 1x1 | ~18 s |
| 89 `rm089` | `getEaten`: Graham sinks (death) | 4, step 1x1 | ~8 s |
| 81 `rm081` | Graham (view 792) walks in, 20 -> 115 | 2 | ~12 s |
| 83 `rm083` | Graham (view 796) climbs, step 1x2 | 2 | ~10 s |
| 109 `intro10` | Crispin walks to 145,126 (intro) | 3 | not measured |
| 102 `intro3`, 101 `intro2` | Graham in the intro | 2 | not measured |
| 123 `ending4` | family walks off (ending) | 2 | not measured |

Short moves (battle 124, castle cat, rm067 at 1037, spiderRegion) are left alone. Settings of 1
(rm004, rm009, rm010, rm047, ...) are probably fine but double the time.

## The patches

- **Speed default** - script 0 `+$8e4`: `KQ5::init` sets `egoMoveSpeed: 2`; patched to 0. The
  Speed slider of the settings panel (`speedSlider` in script 755, 0 = top .. 15 = bottom) does
  **not** change the `Wait` throttle (global 3, `Game::setSpeed`, which rooms set to 3 ticks): it
  stores its value in `egoMoveSpeed` and in ego's `moveSpeed`/`cycleSpeed`, and every room copies
  `egoMoveSpeed` into ego. With the default 2 Graham only stepped every third game cycle, which at
  8 cycles/s is a crawl; 0 (slider at the top, "100 %") makes him step every cycle. Saved games
  carry their own value; the default applies to new and restarted games.
- **Double-click skips the walk** - script 996 `Ego::handleEvent` (`METHODS`). The shim sets
  modifier bit `$80` (unused by SCI) on the second left-button press within 25 VBLs and 4 pixels
  of the previous one (`input.c`, `DBLCLICK`, INPUT.md). The patched handler, after the normal
  `self setMotion: PolyPath x y`, runs `(self doit)` in a loop until `mover` is 0 (at most 1000
  iterations), so Graham arrives in one game cycle; obstacles are honoured because it is the
  ordinary mover that runs. A double-click at a screen edge therefore changes room at once
  (`Ego::doit` sets `edgeHit`, `Rm::doit` calls `newRoom`). 7 bytes after the `setMotion` send
  are replaced by the `jmp` to the trampoline. User-tested.
- **Title skips** - script 996 `User::handleEvent` (`HOOKS`): Esc skips the Sierra fanfare and the
  title song. The game starts in room 99 (a one-second speed test, `fred` = view 99), then room
  119 (`kq5Title`, script `animScript`): states 0-7 play sound 500 (the fanfare), draw pic 106
  (the logo) and wait for the sound's cue signals 5/20/30/255; state 8 draws pic 107 (the title)
  and plays sound 72 (the song), 9-10 wait for its end, 11 waits 2 s, 12 shows the "Have you
  previously played King's Quest V?" box (`Print` with a 15 s timeout, default No), 13 → room 1
  (Yes) or 100 (the intro cartoon). `User::handleEvent` is hooked at its start (it runs before
  the icon bar, which otherwise opens on Esc): a keyDown 27 in room 119 moves `(curRoom script)`
  to state 7 (if its state < 8) or 11 (if < 11), stops global 397 (the title music object),
  disposes the cast (the logo twinkle / title glint Props, whose End cyclers would otherwise cue
  the script late) and cues it, i.e. `changeState 8` or `12`, then claims the event. The hook
  replaces 7 bytes at the start of the method (`link 2; pushi 4; push0; lap 1`). The shim turns
  both mouse buttons held together into Esc (`input.c mouse_buttons_changed`), so the mouse alone
  can skip too (in the game that opens the icon bar, as Esc does). Verified headless
  (`tests/title_skip*.txt`: pic 107 drawn 2 VBLs after the press, dialog in the screenshot); the
  GetEvent mask fix in INPUT.md was needed for it. Not yet tried by the user.
- **Keypad walks with the walk cursor** - script 0 `+$1a58` `kQPMouse::handleEvent` →
  `(super handleEvent: event)` (10 bytes: `pushi handleEvent; push1; lsp 1; super PseudoMouse 6;
  ret`). KQ5 Amiga's override saved the current icon's verb, forced it to 0, called
  `PseudoMouse::handleEvent` (script 933) and restored it, so the stock walk-cursor exception
  (verb 1 → return 0 = not claimed) never applied and the keypad only ever moved the pointer. The
  DOS game has no kQPMouse (and no script 933) at all: its direction keys always reach
  `Ego::handleEvent`. With the plain super call the walk cursor walks Graham and the other
  cursors move the pointer, which is what the manual describes (INPUT.md "What the game does").
  (First attempt, same day: `ldi 0; ret`, i.e. never a pointer move - replaced.) Not yet tried by
  the user.
- **Bakery customers walk faster** - script 206 (`bakeShop.sc`) `doWinners::changeState`
  (2026-10-17, user report: the woman and boy took "a very, very long time" to leave before the
  baker's line). States 18 (boy) and 19 (woman) set `cycleSpeed: 4 moveSpeed: 4`; `pushi 4` ->
  `pushi 0` at `+$5a7` and `+$5e5` (7-byte match covers both values). About 40 steps each: was
  ~25 s at 8.2 cycles/s, now ~5 s. The talk states before it already advance on a click
  (`doWinners::doit`).
- **Cedric lands faster** - script 202 (`owl.sc`, the owl region of the rooms Cedric follows
  Graham through) `stdWalkIn::changeState` state 0 (2026-10-17, user report: his landing holds up
  movement). On every room entry the script calls `HandsOff`, walks Graham in from the edge and
  plays Cedric's landing loop (view 138/140 loops 0-3, 9-14 cels) with `cycleSpeed: 3`, then
  `rotate` turns him (speed 0) and `HandsOn` waits until both Graham's walk-in and the landing are
  done: ~5-7 s at 8.2 cycles/s. `pushi 3` -> `pushi 0` at `+$4f9` (9-byte match from `+$4f6`):
  ~1-2 s, so Graham's own walk-in is now the limit. Not changed: the idle head-turn in `rotate`
  (speed 3, not under HandsOff) and `stdWalkOut` (take-off, speeds 0/1, ~2 s). The alternative,
  `HandsOn` at the start of the walk-in, was not taken: the room's exits and the owl's
  `stdWalkOut` would then race the still-running `stdWalkIn`.
- **Copy protection off** - scripts 22, 30, 216, 220 (2026-10-17), as in the CD release. KQ5's
  manual check is `CPCheck::doit` in script 754 (text 754 = "Incorrect, please try again."): it
  shows the room's prompt ("The door to the witch's house has an enchantment on it ... Use
  Crispin's wand to break the spell." / "Graham's aim is not very good ..." / "There is a bandit
  inside the smaller tent ..." / "Graham's energy has suddenly run out ...") with a word written
  in the manual's symbol alphabet (manual p. 29, "King's Quest V Symbols"), takes three tries and
  returns 0 on failure (death in 22/30, flag 92 in 216, flag 94 + a script in 220). The four
  callers are `getSmall::changeState` (22, `+$46b`), `rock::handleEvent` (30, `+$f92`),
  `rm216::doit` (216, `+$403`) and `leave::changeState` (220, `+$9fb`); each call is guarded by
  flag tests, `global 100 == 0` (the debug switch, set when the version string starts with "x")
  and, in 22/30/216, `Random(1,4) == 1`; the boat (220) asked whenever flag 93 (any check passed)
  was still clear, so the floppy game always asked at least once. The patch turns the last
  guarding `bnt` into a `jmp` (opcode `$30` → `$32`, one byte per script), i.e. the game always
  takes the path it took when the Random draw failed. The CD version has no callers of its
  (rewritten, `CPCheckD`) script 754 at all. The spell-book picture 219 in Mordack's library
  (room 64) also uses the symbol alphabet but is only flavour text; the spell icons (view 712
  loop 2) and the "Select spell to cast" logic (room 124) are identical in the CD version and
  untouched. Not play-tested (the rooms are far into the game).
