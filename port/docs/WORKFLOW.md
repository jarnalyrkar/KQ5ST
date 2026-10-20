# Workflow: build, run, test, debug

Index: [`README.md`](README.md). State: [`HANDOFF.md`](HANDOFF.md).

## Build and run

    st/build.sh          # -> st/hd/KQ5ST.PRG (+ KQ5ST.sym)
    st/play.sh           # play in a Hatari window (log: st/play.log); passes --sound 44100 itself
    st/run.sh [vbls] [script] [hatari args]   # headless test run; log st/run.log, screenshots st/hd/SHOTnn.ST
    python3 -I tools/st2png.py st/hd/SHOT*.ST
    python3 -I tools/makest.py st/hd   # ST art set as patch files (N.p32 / N.v32), see GRAPHICS.md
    python3 -I tools/makescr.py st/hd  # patched game scripts as patch files (N.SCR), see SCRIPTS.md
    python3 -I tools/makesnd.py st/hd  # patched sound resources as patch files (N.snd), see SOUND.md
    python3 -I tools/scidisasm.py extracted/res_amiga 755 [method]   # SCI script disassembler

`build.sh` converts Prog's hunks to GNU as source (`tools/hunk2gas.py`, applying
`st/patches/prog.patch`), compiles the shim (`st/src/*.c`, `*.S`), links twice and diffs to find
the fixups (`tools/elf2prg.py`) and writes the TOS program. The LVO stub list (`src/lvos.inc`)
is generated from every `stub_<Name>` used in the C sources or in `JMP:` patches.

Toolchain: m68k-linux-gnu GCC 15 unpacked (no root) in `~/.local/opt/m68k-gcc`
(`source ~/.local/opt/m68k-gcc/env.sh`; build.sh sources it). Flags: `-m68000 -mstrict-align
-fno-store-merging` (store merging otherwise produces odd-address word writes).

Flag files in the game folder `st/hd/`: `NOSND` = silent sound driver, `NOBLIT` = CPU path
instead of the STE blitter, `KTRACE` = kernel-call trace (below).

Hatari: STE, TOS 1.62, 4 MB, hard disk = `st/hd`. The user's `~/.config/hatari/hatari.cfg` once
had `bEnableSound = FALSE` (saved when the keyboard-joystick emulation was switched off), which
silenced the game; it is TRUE again and `play.sh` passes `--sound 44100` anyway. Keyboard
joystick emulation (`[Joystick1] nJoystickMode = 2`, keypad keys) must be off, otherwise it
swallows keypad 8/5/4/6 before they reach the ST (see INPUT.md).

## Test automation (autoplay scripts)

A script passed to `run.sh` (copied to `st/hd/AUTO.TXT`) has one command per line, time in
VBLs since start-up: `click x y`, `rclick x y`, `dclick x y` (double-click), `press x y`,
`release`, `move x y`, `key code`, `dir n` (direction event), `ikbd byte` (raw IKBD byte through
the keyboard decoder, e.g. `$68`/`$e8` = keypad 8 down/up), `shot`, `quit`, `profreset`, `prof`
(PC-sample profile + game cycles/s). Example (skip the cartoon, walk, open the icon bar):

    4000 press 256 129
    4010 release
    6100 click 120 170
    6800 move 160 3
    6900 shot

Scripts in `st/tests/`: `skip_walk.txt`, `settings.txt` (opens the settings panel), `numpad.txt`
(keypad key codes through the IKBD decoder), `numpad_walk.txt`, `walk_shots.txt` (walk to a point,
5 timed shots: compare Graham's position between builds), `walk_long.txt`, `walk_prof.txt`,
`bench_walk.txt` (speed benchmark), `dclick.txt`, `intro_sound.txt` (12000 VBLs, shots during
the intro), `title_skip.txt` / `title_skip_mouse.txt` (Esc / both mouse buttons skip the Sierra
logo and the title song; run with 3100 VBLs, expect `DrawPic 107` right after the first press and
the "played before?" box in the shot after the second).

The commands are executed by the shim's input code (`c_input_poll`, hooked into Prog's GetEvent,
see INPUT.md), so they only work while the game polls for events.

## Reading the log

- The log goes through Hatari NatFeats (`--natfeats yes`; the user's config has `bNatFeats = TRUE`).
  Without NatFeats (real ST, Steem, Hatari default) `nf_init` catches the illegal `$7300` opcode
  (`nf_illegal` in glue.S) and the log is silent, except crash reports (`c_exception`, `fatal`),
  which go to the screen via Cconws. v0.1.0 lacked this and gave 4 bombs at start (2026-10-19).
  **Test release builds with `--natfeats no` too.**
- Crashes print `*** bus error at H<hunk>_<offset>` with registers and stack; the disassembly is
  in `work/prog/disasm/hunkNN.s`; `tools/sym.py` resolves shim addresses (`st/hd/KQ5ST.sym`).
- New AmigaOS calls show up as `FATAL: unimplemented <lib> LVO -n called from H..`; add a
  `c_<Name>` function and `set_lvo` entry (ARCHITECTURE.md).
- A bus error at an address like `$fffffff6` is an Amiga `-n(NULL)` read (ARCHITECTURE.md).
- `KTRACE` file in `st/hd`: every kernel call is logged as `k <vbl> <name or $number>(args) ->
  result` (hook at hunk 4 `+$9ee`, `c_ktrace_pre/post` in shim.c; per-frame functions are
  skipped, AvoidPath dumps the path). A mouse walk shows `AvoidPath`, `GetAngle`, `InitBresen`;
  a keypad press shows `MapKeyToDir`. Script probes: `MARKERS=1 tools/makescr.py` plants
  `(Abs marker)` kernel calls in the trampolines (SCRIPTS.md).
- `YM_TRACE 1` in `st/src/ym.c` logs every sound-driver call (SOUND.md).
- Game scripts: `tools/scidisasm.py extracted/res_amiga N [method|@hexoffset]` (SCRIPTS.md).

## Real hard-disk test (TOS GEMDOS instead of Hatari's)

Hatari's GEMDOS drive (`--harddrive`) differs from real hardware (load address alignment, speed,
handles 64+ instead of 6+). Before a release, also run from an ACSI image with a real driver:

    cp ../Steem.SSE.4.2.0.Linux64/ACSI/SH204.img hd.img          # AHDI 6.061, empty
    python3 -I tools/acsiput.py hd.img <unpacked release>/KQ5ST KQ5ST
    sed 's/^bUseHardDiskDirectory = TRUE/bUseHardDiskDirectory = FALSE/' ~/.config/hatari/hatari.cfg > acsi.cfg
    hatari --configfile acsi.cfg --natfeats yes --machine ste --acsi 0=hd.img \
        --auto 'C:\KQ5ST\KQ5ST.PRG' --fast-forward yes --sound off --run-vbls 9000 \
        --avirecord --avi-file v.avi                              # frames: ffmpeg -i v.avi -vf fps=1/15 f%02d.png

`acsiput.py` keeps the driver files and adds the folder as a subdirectory (1024-byte logical
sectors, FAT16). The GEMDOS drive must be off in the config or it takes C:. Start-up is slow
there: the Sierra logo appears around VBL 6000 instead of ~700, because every missing patch file
(`Lock("N.scr")`, then `"df3:N.scr"`) is a linear search of the 608-entry folder.

## Profiling and benchmarks

- Benchmark: `st/run.sh 9000 st/tests/bench_walk.txt` (Graham walking, game cycles/s printed by
  `prof`). Results and optimisations: GRAPHICS.md "Performance".
- The VBL-sampled profiler is biased (the game loop is phase-locked to the tick). Use the Timer-A
  profiler (`profreset`/`prof` in a test script; summarise with `tools/profsum.py st/run.log
  st/hd/KQ5ST.sym work/prog/disasm`) or Hatari's cycle profiler:
  `run.sh N script --parse dbg/prof.ini` (`profile on` / `profile cycles 600`) and
  `tools/profsum.py st/run.log st/hd/KQ5ST.sym work/prog/disasm --hatari`.
- `tools/hunkmap.py` gives a per-hunk profile table (run from `port/`).

## Headless-run problems (2026-10-17)

`run.sh` uses `SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`, `--fast-forward yes`,
`--sound off`, `--run-vbls N`. Interactive `play.sh` is unaffected by all of the following.

- Most headless runs stop logging during start-up: last line `Open("df3:RESOURCE.000") h=64`
  for 995.scr or 999.scr, VBL ~430 - with and without an autoplay script, save games, the silent
  driver, windowed, at normal speed. A Hatari debugger dump at VBL 1200 showed the CPU in TOS's
  floppy wait loop (`btst #5,$fffffa01`). Runs without `--run-vbls`, and one run with
  `--run-vbls 4000` + `KTRACE`, went through, so it is not deterministic. Retry a couple of
  times if a run stops early.
- Runs that get further stall once the game reaches Crispin's house after the skipped cartoon
  (~VBL 4500, sometimes as early as VBL ~1700): `c_input_poll` is no longer called, so later
  autoplay events, `shot` and `quit` do nothing (also with the silent driver). The older walk
  tests (`skip_walk.txt`, `walk_shots.txt`) therefore no longer exercise walking and `dclick.txt`
  could not be verified headless. Input polls are reliable from about VBL 700 (Sierra logo) to
  ~1600, which is where `numpad.txt` runs its checks. 2026-10-17 afternoon: six 2600-VBL runs
  (with `KTRACE` or `YM_TRACE`) all stopped at VBL ~1330, in the middle of the Sierra fanfare,
  after an ordinary cast-list walk (FirstNode/NextNode/NodeValue/IsObject), identical with two
  different `500.snd` files - so the stall point depends on the build/trace, not on the data.
- What worked the same afternoon: the same binary run **without `--run-vbls`**, ending with a
  `quit` autoplay command (`printf '2700 quit\n' > st/hd/AUTO.TXT`, then Hatari with run.sh's
  other options from `st/hd`), went through the whole fanfare at the first attempt (`YM_TRACE`
  events up to VBL 1690). So prefer a `quit` command over `--run-vbls` for headless runs.
- The settings panel ignores autoplay `press`/`click` (its loop does not go through the poll hook).
- Headless runs with Hatari sound enabled (`--sound 44100`, needed for an AVI/wav capture) stall
  right after `AddIntServer` (2 file opens, no further progress), also with the silent `NOSND`
  driver, whatever the fast-forward, buffer or mixing setting. `run.sh`'s `--sound off` placed
  before the user's options wins, so a capture made through `run.sh` is silent; the 00:11
  reference captures (`work/sound/*_emulated.wav`, SOUND.md) predate the keypad/title-skip shim
  changes. A windowed run with sound on (`play.sh`, or `--window --sound 44100 --run-vbls N`)
  progresses normally. Not investigated further.
- Hatari's `--cmd-fifo` key injection for a headless key-level test was not completed; the
  `ikbd` autoplay command covers the shim's decoder instead.
- Sound capture that worked (2026-10-17 00:11): `st/run.sh 5200 tests/intro_sound.txt --sound
  44100 --avirecord --avi-file snd.avi`, then `ffmpeg -i st/hd/snd.avi -vn snd.wav` and `sox
  snd.wav -n spectrogram`. Captures need `--fast-forward yes` (the default): with `--fast-forward
  no` the emulation fell far behind the VBL count and the run ended before the fanfare.
