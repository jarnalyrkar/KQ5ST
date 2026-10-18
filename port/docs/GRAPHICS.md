# Graphics: art pipeline, display, performance

Index: [`README.md`](README.md). Code: `st/src/display.c`, `blit.c`, `blitter.c`. Tools:
`tools/makest.py`, `makepic.py`, `egaconvert.py`, `sciview.py`, `scipic.py`, `picalign.py`,
`viewcmp.py`, `colourmap.py`, `viewpreview*.py`, `st2png.py`.

## The ST art set

The Amiga scripts need the Amiga resources (AMIGA_PROG.md "Why the Amiga scripts"), but the 32
colour Amiga art does not fit a 16-colour ST screen, so the DOS EGA art is used where possible:
EGA backgrounds embedded in the Amiga pictures (110), EGA views where structurally safe (253),
Amiga views reduced to 16 colours (217); fixed EGA palette. `tools/makest.py st/hd` writes the
set as SCI patch files (`N.p32` pictures, `N.v32` views) into the game folder, where Prog picks
them up before the resource volumes.

### Using DOS EGA art with the Amiga interpreter (analysis 2026-10-16)

`tools/viewcmp.py extracted/res_dos extracted/res_amiga -v` compares view structure.
The EGA views are separately drawn art, not conversions of the Amiga/VGA art:

| Shared views (442) | Count |
|---|---|
| Structurally identical (loops, cels, sizes, displacement) | 70 |
| Same loops/cels, different cel sizes or displacement | 251 |
| Different cel counts | 99 |
| Different loop count / mirroring | 22 |

Amiga-only views (no EGA counterpart): 166, 251, 769, 775–785 (odd), 891–901, 1041–1120, 1998, 1999.

- View container format is the same in both; only the cel RLE differs
  (EGA: `count<<4 | colour`; Amiga: `colour<<3 | count(1–7)`, `count<<3` = transparent skip).
  Amiga cel RLE runs never cross row ends; clear key is `$ff`.
- The DOS EGA game draws Graham's head as a separate object; EGA views whose cels are much
  smaller than the Amiga ones (44 views) are therefore taken from the Amiga art instead
  (`ega_usable`).
- Pictures: the Amiga picture renderer supports an embedded cel (`FE 01`), so a hybrid picture
  can carry the EGA visual as a bitmap while keeping the Amiga priority/control vector data.

### Colour conversion for Amiga-only art (2026-10-16)

`tools/colourmap.py` learns `P(EGA colour | Amiga colour)` from 400 views with same-size cels in
both releases (2.29 M opaque pixel pairs) → `extracted/colourmap.json`.

- Best fixed mapping agrees with the real EGA pixels 63.8% of the time; nearest-RGB only 44.8%.
- No KQ5 Amiga picture redefines the palette (no `FE 02` 16-colour blocks; the one `FE 02`
  is a skipped VGA leftover), and palette resource 999 is a VGA leftover too: `spal` is the
  only palette, so the learned mapping applies everywhere. (The grey "face" in early previews
  was Graham's lavender hat, which Sierra's EGA art also made grey.)
- `tools/egaconvert.py`: per-view conversion = learned candidates + EGA checkerboard pairs +
  splitting of neighbouring shades that would merge. `tools/viewpreview2.py` renders comparison
  sheets into `previews/`.
- Status (v3): solid colours by default; checkerboard pairs only when two neighbouring shades
  would merge. Characters and dark detailed art (bear 1110/1111) convert well. The chest 1101 is
  busy and the frame 166 needs hand retouching.

### EGA backgrounds in Amiga pictures (2026-10-16)

`tools/scipic.py` renders both picture formats (port of ScummVM's vector code);
`tools/picalign.py` compares all 111 shared pictures (results in `extracted/picalign.tsv`).

- Priority and control maps: median 100% identical. Visible differences only in 42 (egg close-up),
  26, 15, 40, 211, 55, 961, where the EGA picture has an extra control line; the port keeps the
  Amiga maps, so gameplay is unaffected.
- 110 of 111 Amiga pictures = one full-screen embedded cel (320×190 at 0,0) + vector
  priority/control data (+ `FE 04` priority bands). Pic 55 (black scene) has no cel.
- `tools/makepic.py OUTDIR` builds hybrids: the Amiga picture with its cel replaced by the rendered
  EGA visual (Amiga RLE, colours 0–15, clear key 255). Visual drawing left after the cel is
  stripped from lines/patterns; fills keep their colour state, because a visual fill over a bitmap
  aborts entirely in SCI (priority/control included). Every hybrid is verified by re-rendering:
  visual = EGA, priority/control byte-identical to Amiga. Output: `work/hybrid_pic/` (110 pictures).
- Size: EGA bitmaps average 29.9 KB (max 42 KB) against 25.0 KB for the Amiga pictures.

### Dialog box colours and close-up ("talker") views (analysis 2026-10-17)

Compared `Cedric_DOS.png` (EGA) with `Cedric_ST.png` (the port): the ST box is white with a light
blue frame and dark grey text, and Cedric is a noisy conversion with a grey rectangle behind his
eyes. Two separate causes, neither is a rendering bug:

- **Box colours come from the colour count.** `KQ5::init` (script 0 `+$0847`) calls
  `kGraph(GetColorCount)` into global 105 and picks the dialog window's `color`/`back`/`lineColor`
  with a three-way switch: 256 colours → 8/23/19, 32 → 8/15/9, otherwise (EGA) → 0/7/4 (black text,
  grey box, red frame). Global 159 = "more than 16 colours" is set from the same value. Scripts 100
  (intro), 109, 755/758 (settings, inventory) and others branch the same way. The frame itself is
  `KQ5Window::open` (script 403): corner cels of view 944 (already EGA in the art set, red/grey),
  double line in `lineColor`, fill in `back`, black drop shadow. On the ST `Prog` answers 32
  (Graph sub-op 2, hunk 55 `+$1a9c`: `movea.w #0,a2; jsr -$7c56(a4)`, a video-driver query), so the
  Amiga palette indices 15/9/8 are shown through the fixed EGA palette: white, light blue, dark
  grey. **Applied 2026-10-17** (`prog.patch`: `55 1a9c 347c00004eac83aa 303c00104e714e71`,
  `move.w #16,d0; nop; nop`), after which every script takes its EGA branch (text 0, box 7,
  frame 4), consistent with the EGA art. Alternative with the same effect: patch script 0's call.
- **Close-ups are `DCIcon`s (script 967) inside `Print`**, built by script 0 `proc28`
  (`talkerIcon`): loop 0 cel 0 is the bust, the remaining cels of loop 0 / loop 1 are mouth and
  eye frames cycled over `NumCels`. Cedric is **view 75**. The Amiga mouth/eye cels are opaque
  48×25 blocks that carry the parchment colour 15 as background (invisible on the Amiga's 15
  box); converted to 16 colours that background becomes grey 7 = the rectangle, and the bust itself
  is dithered by the colour map. The EGA view 75 has transparent mouth/eye cels with their own
  displacement, and a different cel count (5/4 vs 4/4), which is why `ega_usable` rejected it
  (`makest.tsv`: `amiga-16`). The cel count only feeds the cycler, so the EGA view is safe to use:
  11 other talker views are already EGA (160 Graham, 81, 96, 100, 103–105, 163, 165, 177, 192,
  user-tested talking). **Applied 2026-10-17**: `TALKER_VIEWS` in `makest.py` (75, 101, 102, 129,
  161, 197) bypasses the cel-count/size test when loop count and mirroring match; the EGA busts of
  129/161/197 carry a grey-7 background that only blends in once the box is grey (both changes
  belong together). Not yet seen by the user in Hatari (headless runs stalled at start-up). Finding talker views: `callb proc28` sites in the room scripts, the
  argument after the argc is the view.

### Partly EGA views: the desert oasis palms (2026-10-18)

The user saw grey/red palms at a desert oasis (`grey-palms.png`). The oasis is view 354 (region
script 15 `oasis` Prop; loop 0/1/2/3 for picture 15/16/210/other, cel 0 = sand cover, cel 1 =
palms). It failed `ega_usable` (13 Amiga loops vs 12 EGA, the small ripple cels in loops 5-11
differ), so it was an Amiga conversion; the Amiga palms are olive/brown and the colour map turns
them grey, dark red and black. The EGA palms are bright green and loops 0-3 match the Amiga cels
(same cel counts, sizes within the `ega_usable` tolerance). `EGA_LOOPS` in `makest.py` now takes
those loops from the EGA view and keeps the rest converted (`makest.tsv` source `amiga-16+ega`).
Per-view on purpose: about 160 other views have some matching loops, but mixing EGA and converted
loops in a character view would change its colours between directions. The oasis water (view 353)
converts acceptably and stays Amiga.

## Screen formats

- Prog's visual screen: Amiga planar, 5 separate bitplanes, 40 bytes/row, planes 8000 bytes
  apart, plane-to-plane stride in `-$6804(a4)` / `-$6808(a4)`. Bitmap struct at `-$68b2(a4)`
  (planes from +8), offscreen copy at `-$647c(a4)`.
- Priority + control map: chunky, 320 bytes/row, one byte per pixel with priority in the high
  nibble and control in the low nibble (masks `$f0f0` / `$0f0f`), base `-$6478(a4)`.
  Platform-neutral - reused on the ST as-is.
- ST low-res is 4 interleaved planes. With 16-colour art (5th plane always 0), separate-plane →
  interleaved conversion is plain word copies, no bit shuffling; `display.c` does it (STE blitter
  or CPU), plane 4 is skipped in blits and pixel plots.
- Picture opcode handlers and the per-colour pixel plot routines are listed in AMIGA_PROG.md
  "Data hunk landmarks". The loader's PAL flag is 0 = 200 lines, which the ST needs
  (ARCHITECTURE.md "Loader message").

## Display code on the ST

- `display.c`: graphics/intuition stand-ins (screen, window, palette LoadRGB4 → ST palette),
  the 5-plane → 4-plane conversion, the pointer (drawn by the shim; the driver's show/hide counter
  is ignored, gap 6), screenshots (`shot` autoplay command → `st/hd/SHOTnn.ST`, convert with
  `tools/st2png.py`).
- Loader splash (2026-10-17): the screen opens before the game's first LoadRGB4, so the hardware
  palette is still TOS's default (colour 0 white). `display_open` clears the screen buffer and
  zeroes the palette except pointer colours 1-3 (white). The splash is a 1-bit picture (colours 0
  and 15 only, about 95% colour 15), and EGA colour 15 is white, so `splash_update` makes colour 15
  black while a converted frame is splash-like (equal bitplanes in the sampled groups and at least
  half colour 15), and restores it otherwise. It runs on every full convert and on large rectangle
  converts, so the splash stays black before the logo and when it returns after a skip (seen
  headless at VBL ~2940). The splash picture's source (Prog memory at $1c7ce) was not located, so
  the data is not recoloured. Autoplay `shot` only works after input polling starts (~VBL 670).
- Optimisations: STE blitter for the rectangle engine, the pri/ctl fill and the planar → ST
  conversion; plane 4 skipped in blits and pixel plots; next-fit free-handle search (hunk 59
  `+$c16`); verified property-lookup cache in send (hunk 23 `+$22c`).
- A rewritten cel renderer (word-wise packing in C and in assembly) was slower than the original:
  the dithered EGA art consists mostly of 1-pixel RLE runs, where per-run bookkeeping costs more
  than the original per-pixel plotting. The original renderer (with the plane-4 skip) is kept.
- Remaining cost (cycle profile, blitter on): SCI send ~21%, original cel drawing ~20%, blitter ~6%.
- The Speed slider / `egoMoveSpeed` default (why Graham crawled at 8 cycles/s): SCRIPTS.md.
- Open: faster display updates; the 1 MB memory target (ARCHITECTURE.md "Memory").
