# KQ5 Atari ST port — work folder

- `extracted/` — raw files from both releases (`amiga_files`, `dos_files`) and every resource decompressed (`res_amiga`, `res_dos`).
- `work/prog/` — `Prog` split into hunks (`hunkNN.bin`, `hunks.json`) and annotated disassembly (`disasm/hunkNN.s`).
- `work/loader/` — the `kq5` loader split into hunks.
- `docs/` — the documentation, split by area; start with `docs/README.md` (index) and `docs/HANDOFF.md` (state).
- `st/` — the Atari ST port: shim sources (`src/`), Prog patches (`patches/`), build/run scripts, the game folder `hd/`, test scripts (`tests/`).
- `tools/` — the Python tools (run with `python3 -I`):
  - `adf.py IMAGE OUTDIR` — extract an AmigaDOS OFS/FFS disk image
  - `sciextract.py SRCDIR OUTDIR` — dump/decompress SCI resources (auto-detects map format)
  - `cmp.py A B TYPE` — compare a resource type between two dumps
  - `names.py` — compare kernel/selector tables of the two versions
  - `hunks.py FILE [OUTDIR]` — parse/split an Amiga hunk executable
  - `disasm.py HUNKDIR OUTDIR` — relocation-aware 68000 disassembly (capstone)
  - `libcalls.py DISASMDIR` — list OS library calls per library base
  - `hunkmap.py` — per-hunk profile table (run from this folder)
  - `viewcmp.py A B [-v]` — compare view structure between two dumps
  - `sciview.py` — EGA/Amiga view decoder + Amiga RLE encoder (library)
  - `colourmap.py DOS AMIGA SPAL` — learn Amiga→EGA colour statistics
  - `egaconvert.py` — per-view Amiga→EGA conversion (library)
  - `viewpreview.py` / `viewpreview2.py OUT.png VIEW...` — comparison sheets
  - `scipic.py` — EGA/Amiga picture renderer (library)
  - `picalign.py [--sheet OUT.png PIC...]` — compare priority/control maps of all pictures, or render sheets
  - `makepic.py OUTDIR` — build and verify hybrid pictures (Amiga priority/control + EGA visual)
  - `scidisasm.py RESDIR SCRIPT [method]` — SCI script disassembler (objects, properties, bytecode)
  - `makescr.py OUTDIR` — patched game scripts as `N.SCR` patch files (tables of patches/methods/hooks inside, see `docs/SCRIPTS.md`)
  - `makest.py OUTDIR` — the ST art set as `N.p32` / `N.v32` patch files (`docs/GRAPHICS.md`)
  - `makesnd.py OUTDIR` — patched sound resources as `N.snd` patch files (channels to keep, held notes; `docs/SOUND.md`)
  - `sndvoices.py SOUND|N.snd [PATCH101] OUTDIR` — render every channel of a sound resource to wav files to pick voices by ear
  - `hunk2gas.py` / `elf2prg.py` — Prog hunks → GNU as source, ELF → TOS PRG (used by `st/build.sh`)
  - `mkrelease.sh VERSION` — pack `st/hd` and `READ_ME.TXT` into `dist/KQ5ST-VERSION.zip` for a GitHub release
  - `st2png.py SHOT.ST...` — convert ST screenshots; `sym.py` — resolve shim addresses; `profsum.py` — summarise profiles (`docs/WORKFLOW.md`)
- `previews/` — rendered comparison sheets

`sciextract.py`, `scipic.py` and parts of `sciview.py` port logic from ScummVM's SCI engine,
so treat these tools as GPLv3+ (same as ScummVM). The game data itself remains Sierra's.
