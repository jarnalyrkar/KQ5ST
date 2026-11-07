# Hand-off: where the KQ5 Atari ST port stands (2026-11-07)

Read this first, then the area file you need (index: [`README.md`](README.md)). This file holds
state only; how things work is in the area files.

## State

- **Runs**: the Amiga KQ5 interpreter (`Prog`) runs on an emulated Atari STE (Hatari 2.6.1, TOS
  1.62, 4 MB) through a TOS shim that stands in for AmigaOS; built from `port/st/` with
  `st/build.sh` (`WORKFLOW.md`, `ARCHITECTURE.md`).
- **Play-tested by the user**: intro, cartoon, first rooms, Crispin's house, the snake warning,
  the town, the bakery, the bear, the ants, the desert, the oasis, the temple and the
  bandits' tent (2026-10-18); walking, icon bar, settings panel, talking, depth sorting (behind/in front of a
  tree), save and restore.
- **Art** (`GRAPHICS.md`): EGA backgrounds embedded in the Amiga pictures (110), EGA views where
  structurally safe (253), Amiga views reduced to 16 colours (217); fixed EGA palette; delivered
  as patch files (`N.p32`, `N.v32`) by `tools/makest.py`.
- **Speed** (`GRAPHICS.md` "Performance", `SCRIPTS.md`): walking benchmark 7.3 game cycles/s on
  the STE (328 cycles in 45 s; the older 8.2 figure predates the current art and sound). The
  Speed slider default is patched to the top so Graham steps every cycle (`0.SCR`).
- **Sound** (`SOUND.md`): `st/src/ym.c`, a YM2149 driver with the `amiga3v.drv` interface. Music
  and effects play for the sounds with a device-`$13` track (212 with the DOS additions); 33 stay
  silent on the YM. Alternative MT-32 driver since 2026-11-07 (below).
  User confirmed title music and intro cartoon sound right. Sierra fanfare (sound 500) on 3
  voices: `st/hd/500.snd` keeps channels 3, 4, 1 of the `$13` track (chosen by the user from
  `work/sound/amiga500_*.wav`). The user found it choppy (2026-10-17 evening): the track's
  programs 6 and 8 are one-tick clicks in patch 101, so the trill, the chord hits and two long
  notes were blips. `makesnd.py` now remaps them to the programs the track itself selects first
  (17, 18); the hits, the final chord and channel 3's long note are held (SOUND.md "Patched
  sounds"). Renderings: `work/sound/st500_18_t13_mix.wav` (result), `st500alt_18_t13_mix.wav`
  (crisper-trill alternative). Not yet heard by the user in Hatari; not re-run headless.
- **Desert ambience silenced** (2026-10-17, `SOUND.md` "Patched sounds"): sound 3, the looped
  desert chirp (region script 15), was a fast high chatter on the YM; `st/hd/3.snd` drops its
  `$13` track (a first try on sound 16 was the bees of room 11, undone). **Not
  yet checked by the user** in the desert.
- **Double-click walk skip removed** (2026-10-20, user request: caused bugs, and the game is
  about the journey). Shim no longer flags double-clicks; `996.SCR` keeps only the title-skip
  hook (`INPUT.md`, `SCRIPTS.md`). Released as v0.1.4 (pre-release, 2026-10-20); restoring saves made with
  v0.1.3 or earlier not tested.
- **Keypad as in the manual** (`INPUT.md`, `SCRIPTS.md`): the shim posts PC keypad key codes and
  the original game logic does the rest (digits move the pointer or, with the walk cursor, walk
  Graham; 5 cycles the cursors; keypad 0 = Insert toggles walk/last cursor; keypad . = Delete
  opens the icon bar; Enter executes). User-tested: 5, 0, ., Enter and pointer movement. **Not
  yet tried by the user**: the walk-cursor patch (`kQPMouse` → plain super call) that makes the
  digits walk Graham.
- **Title skips** (`SCRIPTS.md`, `INPUT.md`): Esc, or both mouse buttons held together, skips the
  Sierra fanfare and, pressed again, the title song. Verified headless (`tests/title_skip*.txt`);
  **not yet tried by the user**.
- **Copy protection removed** (`SCRIPTS.md`): rooms 22, 30, 216, 220 never call `CPCheck`
  (one `bnt` → `jmp` each), as in the CD release. **Not play-tested** (the rooms are far in).

- **v0.1.0 bombed outside Hatari** (2026-10-19, user + a real-STE/Steem tester): unguarded
  NatFeats opcode at start-up → 4 bombs. Fixed (WORKFLOW.md "Reading the log"); with NatFeats off the
  user saw the game start; console debug text then silenced. User confirmed clean; released as v0.1.1 (pre-release, 2026-10-19).
- **v0.1.1 crashed on real hardware and Steem** (2026-10-20): black screen with pointer, then
  "Illegal instruction at $000030". Cause: TOS loaded the program at 2 mod 4, BPTRs broke
  (ARCHITECTURE.md "Longword alignment"). Fixed in `_start` + `elf2prg.py`; reproduced and
  verified with an AHDI image in Hatari (title screen reached), GEMDOS-drive run unchanged.
  Released as v0.1.2 (pre-release, 2026-10-20); **not yet tried by the user/tester** on real hardware or Steem.

- **Two player bug reports fixed** (2026-10-21): (1) restoring a save in the
  bee/bear room (room 11) locked up: bus error in the handle-flag routines DoSound calls on a purged
  sound handle, now guarded (ARCHITECTURE.md "Prog patches"). Not a version mismatch: the fault is in
  Prog, so any build would hit it. Verified headless with the player's save (`tests/restore.txt`).
  (2) Quit (game-over box or settings panel) crashed on real hardware: the shim left its vectors
  installed at Pterm; now it restores everything (ARCHITECTURE.md "Interrupts and timing").
  Verified with `--natfeats no`: desktop reached and stable. Released as v0.1.5 (pre-release,
  2026-10-21; zip checked from an AHDI image with NatFeats off). **Confirmed working by the
  reporting player (zkogur), 2026-10-21.**

## Work of 2026-11-07 (released as v0.2.0)

Everything below is committed and released as **v0.2.0** (2026-11-07). Release checks: rebuild
byte-identical, `tools/equiv/run.sh` passes, the unpacked zip run with `--natfeats no` on the
GEMDOS drive (to the settings panel) and from an AHDI ACSI image (to the cartoon warning).
`mkrelease.sh` now also leaves out the `MT32` flag file.

- **Player report from zkogur** (photos in `../zkogur-feedback/`):
  - Fixed in the art set (`makest.py st/hd`, GRAPHICS.md "Overlay faces..." and "Picture 55"):
    harpy faces (view 844), Cassima/Graham close-up faces (860), the blue beast changing colour
    when it slips (894/906), and the white labyrinth background (new `55.p32`, the only
    picture drawn with fills only, which the plane-4 skip broke). The labyrinth and the harpy
    close-up were checked in Hatari with `--natfeats no` (debug teleport, WORKFLOW.md); the
    other faces only as `tools/piccomp.py` composites.
  - Face/head overlay sweep (GRAPHICS.md "Sweep"): 12 more views now EGA (queen bee, horses,
    intro Graham/Cedric, Crispin, Madame Mushka and crystal ball, ice queen, ending scenes);
    176, 178, 624, 688, 806, 824, 840 left as conversions (positions set at run time).
  - "Something missing" near Mordack's castle (`library.jpeg` = room 56): the fire only appears
    at detail level 3, and the ST start-up speed test sets detail 1 (SCRIPTS.md "Detail level").
    Not changed; the player can raise the Detail slider.
  - Room 40 (mountain path before the roc): **soft lock not reproduced** (ledge jumps, fall,
    death box, Restart all work headless). Needs the player's save or exact steps.
- **Roland MT-32 support** (SOUND.md "MT-32 driver"): `st/src/mt32.c`, chosen by a file `MT32`
  next to `KQ5ST.PRG`. Uploads patch 1 as SysEx (73 messages, ~6-8 s at start-up), sends the
  MT-32 tracks to the MIDI ACIA; Init reports channels 1-8 (fixed the silent town). Sounds 16 and
  811 get the DOS MT-32 track (`makesnd.py from_dos`). Music coverage against the user's 63-song
  list: complete on the MT-32 (699 is replaced by 799 when 32 voices are reported). **The user
  plays it through Munt** (`st/play.sh --munt ROMDIR`, `tools/mt32bridge/`, ROMs from the user's
  ScummVM folders; WORKFLOW.md "MT-32 in Hatari"); confirmed working, then reported the town
  and bee-hive silence (fixed, verified by MIDI capture from restored saves; **user to
  re-listen**). Not tried on real hardware: the user's D-50 is not MT-32 compatible.
  `play.sh --mt32 DEVICE` sends the MIDI to a real port.
- **Music tempo** (SOUND.md "Tick rate"): the SCI tick runs at 59.94 Hz on MFP Timer B instead of
  the 50 Hz VBL; music and timed waits were 17 % slow (the user noticed with the MT-32).
  Verified: 599 ticks per 500 VBLs, Quit to a stable desktop with `--natfeats no`.
- **YM sound**: DOS `$13` tracks added for 50 (labyrinth music), 51, 785, 787; 33 sounds have no
  YM-playable track in either version (SOUND.md "Which sounds play").
- **Performance** (GRAPHICS.md "Performance pass", "Selector lookups in send"): +6-9 % over three
  scenes (`tools/bench3.py`: walk 302 -> 328, town 358 -> 381, bakery 1537 -> 1647). Kept: hunk 36
  geometry helpers, per-colour cel run loops, fingerprinted property-miss cache in `send`. All
  replacements proven equal to Prog's code in a 68000 emulator (`tools/equiv/run.sh`).
- **Bytecode interpreter rewritten** (later on 2026-11-07, GRAPHICS.md "Bytecode interpreter
  rewrite", ARCHITECTURE.md "Bytecode interpreter"): `st/src/pmachine.S` replaces hunk 4's
  opcode loop and hunk 23's `send` for bytecode (patch: hunk 4 `+$402` → `pm_entry`; the old
  `KTRACE` hook at `+$9ee` is inside it now). Another +8.5 %: walk 328 -> 345, town 381 -> 420,
  bakery 1647 -> 1791 (sum 2356 -> 2556; from the start of the day +14-17 %). Proven equal to
  Prog's interpreter by a new fuzzer, `tools/equiv/pmtest.py` (900 random worlds, every opcode,
  sends, errors, scripts moving under the code; part of `run.sh`). Headless: the walk completes
  and the restored town/bakery saves run (bench3); a `--natfeats no` walk run (walk_shots)
  ended with Graham at the destination. **Not yet play-tested by the user.** Differences from Prog on purpose: the
  write-only debug send stack, `-$7132` and `-$4f3e` are not maintained (the SCI debugger's
  ShowSends would show nothing); an unknown opcode's PError reports the opcode instead of a
  table offset. The C-level Send used by kernel functions still runs Prog's hunk 23 code.
- **Pause panel colours** (GRAPHICS.md "Pause panel colours", user request): view 946's yellow
  (Amiga gold 13) now brown 6 via `COLOUR_OVERRIDES` in `makest.py`; the four titles redrawn as
  black font-69 capitals (`TEXT_CELS`), DETAIL/SPEED re-centred by a script 755 patch
  (`755.SCR`, SCRIPTS.md). Checked in a headless `--natfeats no` run; not yet seen by the user.
- **ScummVM** (GRAPHICS.md "The game folder in ScummVM"): detected as `sci:kq5` (Amiga/English),
  loads our `.v32`/`.p32`/`.SCR` patches. Made to work: view 947 left unpatched (ScummVM needs one
  original view to detect the format), `spal` carries the EGA colours (ST ignores it), script 0
  stores colour count 16. Seen in `/usr/games/scummvm`: intro and cartoon warning with the ST
  colours. ST checked unchanged (headless panel run). User played it in ScummVM: everything
  looks good and it runs at the original's speed.
- **Tools added**: `piccomp.py`, `midicheck.py`, `hprofmap.py`, `bench3.py`, `equiv/`,
  `mt32bridge/`; `play.sh --mt32` / `--munt`; `makesnd.py from_dos`; debug teleport recipe and
  save-restore testing in WORKFLOW.md.
- **`READ_ME.TXT`**: MT-32 section; stale double-click line and "music 17 % slow" removed.

## Known gaps / risks

0. Start-up from a real hard disk was slow (~94 s black screen in Hatari's ACSI emulation);
   the directory cache and kept-open handles in `dos.c` (2026-10-20) cut it to ~19 s, lookup
   results identical. User tested save, restore, overwrite and restore again in `play.sh`
   (2026-10-20). Released as v0.1.3 (pre-release, 2026-10-20); not yet tried on real hardware.

1. Sound (`SOUND.md`): YM has no noise/percussion; 33 sounds have no YM-playable track (silent on the YM, fine on the MT-32).
2. ShiftScreen (video driver hunk 52 `+$3e8`) still uses the Amiga blitter: a room that scrolls
   between screens would bus-error at `$dff000`. Not hit yet (`GRAPHICS.md`).
3. Amiga NULL-pointer reads of `-n(NULL)` fault on the ST (fixed so far: IsObject). A new bus
   error at an address like `$fffffff6` is this kind (`ARCHITECTURE.md`).
4. Memory: only tested with 4 MB; SCI takes the largest free block as heap. 1 MB untested.
5. Distribution: resources are loose patch files on a hard-disk folder; floppies would need the
   resource volumes rebuilt (and compression).
6. The pointer show/hide counter of the video driver is ignored (pointer always drawn).
7. Headless runs (`run.sh`) are flaky: most stop logging during start-up (VBL ~430, CPU in TOS's
   floppy wait loop) or stall at Crispin's house (~VBL 4500) so later autoplay commands do
   nothing; retry, or run without `--run-vbls`. The settings panel ignores autoplay
   `press`/`click`. Interactive `play.sh` is unaffected. Details: `WORKFLOW.md` "Headless-run problems".
8. Headless runs with Hatari sound on (needed for an AVI/wav capture) stall right after
   `AddIntServer`; a windowed run with sound is fine. Details: `WORKFLOW.md`.
9. Hatari's keyboard-joystick emulation swallows keypad 8/5/4/6; the user has turned it off.
   IKBD joystick reporting cannot be used (disables the mouse). `INPUT.md`, `WORKFLOW.md`.
10. The keypad cannot type digits in the game (use the number row) (`INPUT.md`).

## Next

- zkogur to try v0.2.0 (art fixes, MT-32, tempo, speed, interpreter rewrite).
- User to re-listen with Munt: town and bee-hive music, overall tempo vs the original.
- Room 40 soft lock: get zkogur's save or steps.
- Overlay views left as conversions (GRAPHICS.md "Sweep") need a game run to check.

0. Slow scripted walks (2026-10-17): bakery customers patched to speed 0 (script 206, SCRIPTS.md
   "Bakery customers walk faster") and Cedric's landing on room entry patched to speed 0
   (script 202, "Cedric lands faster"); **user to test both**. The other slow walks are listed in
   SCRIPTS.md "NPC speeds" (rm039 ~50 s, rm089 boat, rm081, rm083, intro/ending) - not patched,
   awaiting the user's choice.

1. User to test: re-instrumented fanfare (`500.snd`; alternative trill in
   `work/sound/st500alt_18_t13_mix.wav`), keypad walking with the walk cursor, title skips, desert now silent (`3.snd`, after restarting the game).
2. Play-test further rooms (scripted), fix crashes as they appear (NULL reads like IsObject).
3. ShiftScreen (hunk 52 `+$3e8`) on the CPU; faster display updates; 1 MB memory target.
4. Sound: noise channel for percussion, sounds without a `$13` track.
5. Floppy distribution (resource compression, disk images).
6. Dialog boxes and close-ups (2026-10-17, GRAPHICS.md "Dialog box colours and close-up views"):
   Prog now answers 16 colours (`prog.patch` hunk 55 `+$1a9c`), so the scripts pick the EGA box
   colours (black text, grey box, red frame) everywhere; Cedric (view 75) and five other close-ups
   now use the EGA art (`TALKER_VIEWS` in `makest.py`). Built and art set regenerated; **not yet
   seen by the user** (headless runs stalled at start-up).
7. Desert oasis palms (2026-10-18, GRAPHICS.md "Partly EGA views"): view 354 loops 0-3 now EGA
   (green palms instead of grey/red); art set regenerated, **not yet seen by the user**.
