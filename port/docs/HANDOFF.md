# Hand-off: where the KQ5 Atari ST port stands (2026-10-17, afternoon)

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
- **Speed** (`GRAPHICS.md` "Performance", `SCRIPTS.md`): 8.2 game cycles/s with the STE blitter,
  7.1 on a plain ST, Graham walking. The Speed slider default is patched to the top so he steps
  every cycle (`0.SCR`).
- **Sound** (`SOUND.md`): `st/src/ym.c`, a YM2149 driver with the `amiga3v.drv` interface. Music
  and effects play for the 208 sounds with a device-`$13` track; 36 (e.g. 799) stay silent.
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

## Known gaps / risks

0. Start-up from a real hard disk was slow (~94 s black screen in Hatari's ACSI emulation);
   the directory cache and kept-open handles in `dos.c` (2026-10-20) cut it to ~19 s, lookup
   results identical. User tested save, restore, overwrite and restore again in `play.sh`
   (2026-10-20). Released as v0.1.3 (pre-release, 2026-10-20); not yet tried on real hardware.

1. Sound (`SOUND.md`): tempo runs at the VBL rate (50 Hz PAL vs the expected 60 Hz, music 17 %
   slow); no noise/percussion; sounds without a `$13` track are silent.
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

0. Slow scripted walks (2026-10-17): bakery customers patched to speed 0 (script 206, SCRIPTS.md
   "Bakery customers walk faster") and Cedric's landing on room entry patched to speed 0
   (script 202, "Cedric lands faster"); **user to test both**. The other slow walks are listed in
   SCRIPTS.md "NPC speeds" (rm039 ~50 s, rm089 boat, rm081, rm083, intro/ending) - not patched,
   awaiting the user's choice.

1. User to test: re-instrumented fanfare (`500.snd`; alternative trill in
   `work/sound/st500alt_18_t13_mix.wav`), keypad walking with the walk cursor, title skips, desert now silent (`3.snd`, after restarting the game).
2. Play-test further rooms (scripted), fix crashes as they appear (NULL reads like IsObject).
3. ShiftScreen (hunk 52 `+$3e8`) on the CPU; faster display updates; 1 MB memory target.
4. Sound: 60 Hz tick (tempo), noise channel for percussion, sounds without a `$13` track.
5. Floppy distribution (resource compression, disk images).
6. Dialog boxes and close-ups (2026-10-17, GRAPHICS.md "Dialog box colours and close-up views"):
   Prog now answers 16 colours (`prog.patch` hunk 55 `+$1a9c`), so the scripts pick the EGA box
   colours (black text, grey box, red frame) everywhere; Cedric (view 75) and five other close-ups
   now use the EGA art (`TALKER_VIEWS` in `makest.py`). Built and art set regenerated; **not yet
   seen by the user** (headless runs stalled at start-up).
7. Desert oasis palms (2026-10-18, GRAPHICS.md "Partly EGA views"): view 354 loops 0-3 now EGA
   (green palms instead of grey/red); art set regenerated, **not yet seen by the user**.
