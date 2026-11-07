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
VBLs since start-up: `click x y`, `rclick x y`, `press x y`,
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
`bench_walk.txt` (speed benchmark), `intro_sound.txt` (12000 VBLs, shots during
the intro), `title_skip.txt` / `title_skip_mouse.txt` (Esc / both mouse buttons skip the Sierra
logo and the title song; run with 3100 VBLs, expect `DrawPic 107` right after the first press and
the "played before?" box in the shot after the second).

The commands are executed by the shim's input code (`c_input_poll`, hooked into Prog's GetEvent,
see INPUT.md), so they only work while the game polls for events.

### Jumping to any room (debug teleport, 2026-11-07)

Script 0 turns on the game's debug keys (global 100) when the version string starts with `x`
(script 0 `+$0926`: `callk StrAt; push; ldi 120; eq?`). For a test, copy `st/hd` to a scratch
folder (without the save games), and in its `0.SCR` change the `78` of the byte sequence
`36 35 78 1a 30 07 00` to `31` (`ldi '1'`, matching "1.000.000"). Never ship this. Then Alt-T
(`key 5120`) opens "Teleport to:" (type digits with `key 48`-`57`, then `key 13`). After "played
before? Yes" (`click 183 52`, VBL 1800) the prompt works from about VBL 2700. A restart in debug
mode asks for a room again. Teleporting into a room that needs story state can stop the game with
"Oops! You have tried something we didn't think of" (room 3, the town, 2026-11-07); the sound
system shuts down too, so check a screenshot before trusting a teleported sound capture. For such
rooms restore a save instead: copy `st/hd` with the user's saves and write a `KQ5sg.dir` that
lists only the wanted save (format: 2-byte big-endian save number, name, `\n`, ..., `FF FF`), then
run `tests/restore.txt`. With `MT32` present the start-up is ~6 s longer (SysEx upload): add ~700
VBLs to the script times. Used for rooms 40 and 55 (player report 2026-11-07). The new room
starts from its default state (no inventory, flags unset).
Click coordinates are screen coordinates (picture y + 10). `key 20480` (down arrow) did not walk
Graham in a headless run; clicks do. Hatari takes screenshots on its own every ~250 VBLs as well
as on `shot`.

### MT-32 in Hatari (2026-11-07)

`st/play.sh --mt32 DEVICE [hatari args]` creates `hd/MT32` for the run (removed afterwards unless
it already existed) and adds `--midi-in /dev/null --midi-out DEVICE`. Without `--midi-in`
Hatari fails to open its default MIDI input and disables MIDI altogether. DEVICE is a raw MIDI
device: `amidi -l` lists them (`hw:2,0` = `/dev/snd/midiC2D0`), e.g. a USB MIDI interface to a
real MT-32. For Munt (an ALSA sequencer client, no raw device): `sudo modprobe snd-virmidi`, then
`amidi -l` shows the new `VirMIDI` devices; `aconnect -l` shows their sequencer ports and Munt's;
connect them with `aconnect <virmidi client:port> <munt client:port>` and pass the matching
`/dev/snd/midiCxD0`. A plain file as DEVICE captures the bytes for `tools/midicheck.py`. With
`hd/MT32` present a normal `play.sh` run is silent (the YM is off); play.sh prints a note.

Munt without root (2026-11-07): `tools/mt32bridge/` builds Munt's `libmt32emu` sources straight
with g++ (no cmake/Qt/ALSA headers; `config.h` is generated from `config.h.in` by `build.sh`)
into `mt32bridge ROMDIR FIFO`, which feeds the bytes Hatari writes into a named pipe to the
emulated MT-32 and writes 32 kHz s16 stereo to stdout. `play.sh --munt ROMDIR` makes
`st/munt.fifo`, runs `mt32bridge | pw-cat --playback` and Hatari with `--midi-out` on the FIFO
(bridge messages in `st/munt.log`, including the MT-32 display texts). Steps:
`git clone --depth 1 https://github.com/munt/munt.git ~/.local/src/munt`, then
`tools/mt32bridge/build.sh`. ROMs: the user has MT-32 ROMs in the 86Box ROM pack and in ScummVM
game folders (e.g. `~/.local/share/scummvm/games/Beneath a Steel Sky`). **Not yet run**: the
build/run of the downloaded Munt code was blocked by the session's permission check; open
question whether Hatari flushes `--midi-out` per byte (if it buffers, the music lags).

## Reading the log

- The log goes through Hatari NatFeats (`--natfeats yes`; the user's config has `bNatFeats = TRUE`).
  Without NatFeats (real ST, Steem, Hatari default) `nf_init` catches the illegal `$7300` opcode
  (`nf_illegal` in glue.S) and the log is silent, except crash reports (`c_exception`, `fatal`),
  which go to the screen via Cconws. v0.1.0 lacked this and gave 4 bombs at start (2026-10-19).
  **Assume NatFeats is off (user's rule, 2026-10-21):** players run real STs and Steem, so a
  behaviour only counts as verified when it was checked with `--natfeats no` (video via
  `--avirecord`, or the screen). NatFeats is a logging aid only; its `nf_exit` ends Hatari at once
  and hid the Quit crash (ARCHITECTURE.md "Interrupts and timing"). Never rely on it for control
  flow.
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
sectors, FAT16). The GEMDOS drive must be off in the config or it takes C:.

Start-up from such a disk was slow (Sierra logo ~94 s after the desktop in v0.1.2, vs ~14 s on
the GEMDOS drive): each lookup was a linear search of the 608-entry folder, ~5 VBLs per Lock and
~15 per Open, and SCI looks up two missing patch names per resource and reopens RESOURCE.000 each
time (49 opens to the title). The directory cache in `dos.c` (ARCHITECTURE.md) brought it to
~19 s (2026-10-20). Measure with `--avirecord` and the first non-black frame
(`ffmpeg -vf fps=1`); the lookup results are logged, so `Lock`/`Open` lines can be diffed
between builds to check the cache answers as GEMDOS did.

## Profiling and benchmarks

- Benchmark: `st/run.sh 9000 st/tests/bench_walk.txt` (Graham walking, game cycles/s printed by
  `prof`). Results and optimisations: GRAPHICS.md "Performance".
- The VBL-sampled profiler is biased (the game loop is phase-locked to the tick). Use the Timer-A
  profiler (`profreset`/`prof` in a test script; summarise with `tools/profsum.py st/run.log
  st/hd/KQ5ST.sym work/prog/disasm`) or Hatari's cycle profiler:
  `run.sh N script --parse dbg/prof.ini` (`profile on` / `profile cycles 600`) and
  `tools/profsum.py st/run.log st/hd/KQ5ST.sym work/prog/disasm --hatari`; per instruction:
  `tools/hprofmap.py LOG KQ5ST.sym [H23_]` (2026-11-07; the `profile cycles 1500` list).
  The cycle profiler slows Hatari a lot: 250 profiled VBLs need ~30-60 min, so run Hatari with a
  long `timeout` (run.sh's 900 s is not enough) and keep the profiling window short. Breakpoint
  VBLs are Hatari's count, ~1100 more than the shim's autoplay times.
- Three-scene benchmark `tools/bench3.py TAG PRG` (BENCH_DIR with a game-folder copy `hdm` and
  `st/tests/bench_save.txt`): room 1 walk plus two restored saves; compare sums, ignore <3 %.
- `tools/hunkmap.py` gives a per-hunk profile table (run from `port/`).

## Equivalence tests (2026-11-07)

Prog routines replaced by faster code in `glue.S` are checked against the originals in a
68000 emulator: `tools/equiv/run.sh [cases]` assembles the replacement blocks from `glue.S`,
loads Prog's hunks (`work/prog/hunkNN.bin`) into Python `unicorn` (user site-packages, so it
runs without `-I`) and compares results, memory writes, stack and the registers the original
may change. `geotest.py`: the five hunk 36 geometry helpers (20000 cases each incl. edge values
and aliased output). `celtest.py`: the whole cel row routine (hunk 56 `+$4e0`) with random RLE
sprites, priority maps and thresholds. Set the CPU model to `UC_CPU_M68K_M68000`: unicorn's
default is a ColdFire, which lacks `movem` with predecrement among others. A deliberately wrong
replacement must fail (checked: 31 of 40 cel cases). The method-lookup cache experiment (since
reverted, GRAPHICS.md "Performance") used the same approach with whole-routine register
comparison and an offline table-fingerprint proof over all scripts.

`pmtest.py` (2026-11-07) checks the rewritten bytecode interpreter and send (`st/src/pmachine.S`,
ARCHITECTURE.md "Bytecode interpreter") against Prog's hunk 4 loop running with Prog's real hunk 23:
`tools/equiv/pmbuild.sh DIR` assembles `pmachine.S` with stand-ins (`pmtstub.S`) and
`python3 tools/equiv/pmtest.py BIN ENTRY [worlds] [seed] [world-to-trace]` generates random
worlds (1-3 scripts with procedures, classes with method dictionaries and superclass chains,
instances, globals, locals; bytecode with every opcode, calls, kernel calls, sends/self/super/
class, `&rest`, forward branches, invalid exports/classes/selectors/opcodes for the error paths)
and runs each on both interpreters in unicorn. Kernel functions, the script loader and PError
are Python stand-ins on `rts` stubs that clobber every register they may, return pseudo-random
results in acc and move every script's code now and then; the loader keeps a2 as Prog relies
on. Compared: all variables, stack, objects, code, interpreter globals (except the debug send
stack, `-$7132`, `-$4f3e`, which `pmachine.S` does not keep), the kernel-call log, the error
and a0/a2 at the final `ret`. `run.sh` runs 150 worlds; 300 per seed take ~10 min. Tracing a
world prints the opcode sequence of both with acc, a2 and d2 and the first divergence.

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
  tests (`skip_walk.txt`, `walk_shots.txt`) therefore no longer exercise walking. Input polls are reliable from about VBL 700 (Sierra logo) to
  ~1600, which is where `numpad.txt` runs its checks. 2026-10-17 afternoon: six 2600-VBL runs
  (with `KTRACE` or `YM_TRACE`) all stopped at VBL ~1330, in the middle of the Sierra fanfare,
  after an ordinary cast-list walk (FirstNode/NextNode/NodeValue/IsObject), identical with two
  different `500.snd` files - so the stall point depends on the build/trace, not on the data.
- What worked the same afternoon: the same binary run **without `--run-vbls`**, ending with a
  `quit` autoplay command (`printf '2700 quit\n' > st/hd/AUTO.TXT`, then Hatari with run.sh's
  other options from `st/hd`), went through the whole fanfare at the first attempt (`YM_TRACE`
  events up to VBL 1690). So prefer a `quit` command over `--run-vbls` for headless runs.
- The settings panel ignores autoplay `press`/`click` (its loop does not go through the poll hook),
  but `move x y` onto a button then `key 13` works: `tests/restore.txt` (restores the first save listed in `KQ5sg.dir`)
  and `tests/quit.txt` (Quit; run with `--natfeats no --avirecord` and check the last frames show the
  desktop). The "played before?" Yes button is at 183,52 (straight to room 1, skipping the cartoon);
  F7 restore only works in the game's debug mode.
- Headless runs with Hatari sound enabled (`--sound 44100`, needed for an AVI/wav capture) stall
  right after `AddIntServer` (2 file opens, no further progress), also with the silent `NOSND`
  driver, whatever the fast-forward, buffer or mixing setting. `run.sh`'s `--sound off` placed
  before the user's options wins, so a capture made through `run.sh` is silent; the 00:11
  reference captures (`work/sound/*_emulated.wav`, SOUND.md) predate the keypad/title-skip shim
  changes. A windowed run with sound on (`play.sh`, or `--window --sound 44100 --run-vbls N`)
  progresses normally. Not investigated further.
- Hatari's `--cmd-fifo` key injection for a headless key-level test was not completed; the
  `ikbd` autoplay command covers the shim's decoder instead. Screenshots through it work
  (2026-11-07): start Hatari with `--cmd-fifo F --screenshot-dir D`, then
  `echo "hatari-shortcut screenshot" > F` - useful after Quit, when the shim's `shot` no longer
  runs. `--avirecord` in a headless fast-forward run gave a few hundred white frames.
- Sound capture that worked (2026-10-17 00:11): `st/run.sh 5200 tests/intro_sound.txt --sound
  44100 --avirecord --avi-file snd.avi`, then `ffmpeg -i st/hd/snd.avi -vn snd.wav` and `sox
  snd.wav -n spectrogram`. Captures need `--fast-forward yes` (the default): with `--fast-forward
  no` the emulation fell far behind the VBL count and the run ended before the fanfare.
