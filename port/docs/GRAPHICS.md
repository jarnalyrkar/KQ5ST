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

### Overlay faces and the beast's slip (2026-11-07)

Player report (zkogur): faces "from a different version" on the harpies (room 91) and on Cassima and
Graham (room 96, `cassima-graham-talking.jpeg`), and the blue beast changing colour when it slips
on the peas. Same cause each time: a view that failed `ega_usable` (cel counts or sizes) was
converted from the Amiga art while the picture under it (or the character's other views) is EGA.
Room 91's eyes and mouths are props of view 844 and room 96's are props of view 860, placed on
EGA pictures 91/96. The beast walks in view 884/898 (EGA) and slips in 894/906 (converted,
dark blue). The DOS scripts place the props at the same x/y as the Amiga scripts (checked with
`scidisasm.py`, script 96), and composites of EGA picture + EGA cels line up exactly.
`OVERLAY_VIEWS` in `makest.py` (844, 860, 894, 906) takes the EGA view whenever loop count and
mirroring match, like `TALKER_VIEWS`. The EGA cel counts differ (860 has more cels, 844 loop 3 has
one fewer) but the scripts only cycle them or pick cels below both counts. The EGA slip cels are
about 12% smaller than the Amiga ones, as in the DOS game.

**Sweep of the other face/head props (2026-11-07):** 26 more views with an EGA counterpart were
checked with `tools/piccomp.py` (prop x/y/loop from the decompiled room scripts). Added to
`OVERLAY_VIEWS` (clear matches, EGA cleaner): 298 queen bee (room 11), 368 horses (214), 761/763
Graham and Cedric in the intro (pics 70/71), 773 Crispin (intro9, pic 1), 776/778 Madame Mushka
and her crystal ball (77), 848/852 the ice queen (92; her close-up face on 93), 933/934/936 the
ending (65/68/218). Where an EGA loop has fewer cels (848, 933, 934) the scripts only cycle it
(End/Beg/Fwd/RandCycle, cel 0, NumCels). Left as conversions: 342, 766, 800 (different loop
count); 469 Jinx and 720 Cedric (animated characters with differently sized cels, props not
visible in the composite); 757, 768 (props not visible in the composite); 840 room-90 harpies
(positions set at run time); 176, 178, 624, 688, 806, 824 (positions set at run time or picture
not found; would need a game run). In the game the harpy close-up (room 91) was checked
(teleport, `--natfeats no`); the others only as composites.

### Picture 55: the labyrinth backdrop (2026-11-07)

Player report: the labyrinth (room 55) had a white background, so the side openings were hard to
see (`labyrinth-*.jpeg`). Pic 55 is the only Amiga picture without an embedded cel. It draws its
black visual with vector fills. On the ST, Prog's pixel plots and blits skip bitplane 4
(`prog.patch`, RELADD on the pixel table), so the cleared screen reads back as colour 15 instead of
the clear colour 31. The visual flood fill then sees no clear pixels and never starts, so the
screen stayed white (colour 15). `makepic.vector_hybrid` builds
`55.p32`: the EGA visual (all black) as an embedded cel after the palette block, then every `F0`
(visual on) replaced by `F1` (visual off), so the fills only touch priority/control. Verified:
re-rendered priority/control byte-identical to the Amiga picture; in Hatari (`--natfeats no`,
teleport, WORKFLOW.md) the maze shows on black. Any other picture drawn only with visual fills
would need the same treatment; there are none in KQ5.

### Second player report: the bear, the pantry cupboard, the maze colour (2026-11-08)

zkogur confirmed the 2026-11-07 fixes (harpies blink, Cassima and Graham look right, the blue
beast keeps its colour) and reported three more things, all art-set choices in `makest.py`:

- **The bear turns black when disturbed or when the fish is thrown** (room 11,
  `bear-changes-color-like-the-blue-monster-did.jpeg`). The idle bear is views 1110-1114, Amiga-only
  numbers: the Amiga release split the DOS bear view **302** into five views, each holding one
  real loop (loop N of 111N) behind 1x1 placeholder loops. They were Amiga conversions (grey 8 with
  light-grey 7 fur), while the disturbed/fed bear is views 304/308, EGA since the start, where the
  bear is black with dark-grey shading. `EGA_SOURCE` in `makest.py` now takes loop N of the EGA
  302 for view 111N (report source `ega-302`); the placeholder loops stay converted. EGA 302 has
  more cels in loops 0 and 4 (6/11 against 4/8); `bearScript` cycles both with `End`, so the
  animation is only longer. The bear is only present when Graham carries the fish (`rm011::init`,
  item 5), so a debug teleport into room 11 shows no bear.
- **The cupboard left of the pantry entrance** (room 56, the room after the labyrinth,
  `library-left-cupboard-looks-off.jpeg`): view 680 (cupboard doors, bag of peas, open interior,
  fire, Graham reaching in) failed `ega_usable` on loop 2 alone (8 Amiga cels, 7 EGA, cycled with
  `End`), so its converted cels, with the Amiga's opaque grey background block, sat on the EGA
  picture. Added to `OVERLAY_VIEWS`; `piccomp.py` composites of picture 56 with the EGA cels at the
  script positions (51,142 / 55,125 / 55,91 / 34,75 / 169,156) line up exactly.
- **Labyrinth walls white instead of light grey** (room 55, `labyrinth-3-change-white-for-light-gray.jpeg`).
  The walls are `mazePiece`s of script 603 from views 877 (side walls, already EGA: dark grey 8
  dithered with black, light-grey 7 edges) and 878 (front walls, floor, ceiling, openings), which
  was an Amiga conversion because its loop 4 has a 1x1 placeholder cel before the wall cel
  (script 603 draws `878 4 1`; the DOS script 55 draws `878 4 0`). The learned colour map turned
  the Amiga colour 3 of that view into white 15. `PAD_CELS` in `makest.py` puts a 1x1 transparent
  cel in front of the EGA loop so the Amiga cel numbers apply; the view then passes `ega_usable`
  and the whole maze is the EGA art: no white anywhere, dark grey with light-grey 7 edges, like
  the DOS EGA game (the player's guess). Checked in Hatari with `--natfeats no` (debug teleport
  to rooms 55 and 56, `scratch` copies of `st/hd`): maze on black in greys, cupboard matching the
  picture.

The scan behind the bear fix (`Amiga-only views with 1x1 placeholder loops, matched by cel count
and size against every DOS loop`) found no other split view; the other Amiga-only views (166,
251, 769, 775-785 odd, 891-901, 1041-1103, 1120, 1998, 1999) have no DOS counterpart to take.

### Third player report: Dink's blue frames (2026-11-08)

zkogur: "the animation with Dink has a couple of frames where black turns blue". Dink is views
873 (idle, blink, the hug), 874 (the dance, Graham with the tambourine in loop 5, the 4-pixel
hairpin in loop 4) and 1060 (the hairpin shake, Graham's dance in loop 1), all `amiga-16`
conversions (the EGA 873/874 fail `ega_usable`, 1060 has no EGA counterpart, and the EGA Dink
is blue all over). Per cel, the only Amiga colour 0 (black) pixels are Graham's tights and
boots in the cels where he stands inside Dink's view: 873 loop 6 cels 3-8 (the hug), 874 loop 2
cel 0 and 1060 loop 0 cels 0/6/7 (handing over the tambourine), 874 loop 5 and 1060 loop 1 (his
dance). `egaconvert.plan_view`'s de-collision found black (152-2275 pixels) next to Dink's body
(Amiga 1 → EGA 0, 10-60 k pixels) and next to Amiga 2 (→ dark grey 8), and moved the rarer colour
twice: off black to dark grey, then off dark grey to the next candidate, blue 1. Graham's own
walking view 0 keeps Amiga 0 black, so the tights flipped to blue for exactly those frames.
`COLOUR_OVERRIDES` now pins Amiga 0 to black for 873, 874 and 1060 (only those three `.v32`
changed). Checked in the headless Dink run (WORKFLOW.md "Dink test"): no EGA blue beyond
Graham's hat in any of the 60 screenshots of the hug, the hand-over and the dance.

The same scan (`plan_view` over the 186 converted views, Amiga 0 used but not mapped to black)
lists 40 views: 20 where black became dark grey 8 (30, 152, 200, 286, 299, 516, 540, 547, 630,
712, 764, 765, 771, 892, 893, 941, 1102, 1103 and the two above) and 19 more where it became
blue: 26, 27, 176, 221, 242, 252, 259, 342, 462, 469, 739, 762, 775, 782, 818, 846, 935, 1041,
1101. In most of them black is a large share of every cel (outlines of a dark figure), so the
whole view is consistently "blue-black" rather than flashing; not changed, to be judged in a game
run (candidates for the same override if a player reports them).

### The game folder in ScummVM (2026-11-07)

Checked with `/usr/games/scummvm` 2026.1.0 (`/usr/local/bin/scummvm` lacks libtheoradec) and the
source in `../scummvm-master`. ScummVM ignores `KQ5ST.PRG` and runs the folder with its own SCI
interpreter, loading our patch files.

- Detection: `RESOURCE.MAP`/`.000`-`.007` are the untouched Amiga files and match "King's Quest 5 -
  English Amiga" in `engines/sci/detection_tables.h` (MD5 of the first 5000 bytes + size), so
  `scummvm --detect --path=st/hd` gives `sci:kq5`, "King's Quest V: Absence Makes the Heart Go
  Yonder (Amiga/English)". A `.wag` file is no help: only the AGI engine reads one. A distinct
  name needs a ScummVM detection entry (e.g. `RESOURCE.MAP` + `KQ5ST.PRG`; the entry matching
  more files wins).
- Patch files: `engines/sci/resource/resource.cpp` loads `*.v32`/`*.p32` (Amiga view/picture
  patches), `*.scr`, `.snd`, `.tex`, `.pat`.
- View format: `detectViewType` looks at the first view 0-999 that is *not* a patch file. With all
  views patched ScummVM stopped at once with "GfxDefaultDriver: Unknown view type". `makest.py`
  `UNPATCHED_VIEWS` leaves out 947, a DOS leftover (DOS help script 753 shows it, the Amiga 753
  uses 942; no Amiga script pushes it or holds it in a property), so ScummVM sees an Amiga view.
- Colours: ScummVM colours Amiga KQ5 from `spal`, while the ST shim always loads the EGA palette
  and ignores it. `makest.py` therefore writes `spal` with the EGA colours in 0-15 (16-31 left as
  the Amiga's; original in `extracted/amiga_files/d0/spal`).
- Colour count: ScummVM's `kGraph(GetColorCount)` answers 32 for Amiga games, so the scripts would
  take their Amiga colour branch (white boxes, light blue frames). Script 0 is patched to store 16
  itself (SCRIPTS.md "16-colour branches").
- Result (windowed run, separate `--config`/`--savepath`, timed `import` screenshots): Sierra logo,
  then the cartoon warning over the EGA picture of room 1, grey box with red frame, as on the ST.
- Not yet checked there: the game beyond the intro, ScummVM's own KQ5 script fixes (they match
  signatures, so ones hitting scripts we patched are skipped), sound (its Amiga driver ignores the
  YM `$13` tracks in our `.snd` files). Saves are not interchangeable with the ST.

### Pause panel colours (2026-11-07)

User report: the pause/settings panel (script 755 `KQ5Controls`, view 946: buttons, sliders, slot
frames, title letters) looked garish in yellow. View 946 is Amiga-only art (the EGA view differs
completely), and the learned mapping sends the Amiga gold 13 (187,153,68: bevels, slider frames,
title letters) to EGA yellow 14. `COLOUR_OVERRIDES` in `makest.py` (per view, Amiga colour → EGA
pair, applied after `plan_view`) maps it to brown 6 for view 946 only, which keeps the Amiga's
single warm tone with the brown buttons; white 15 and dark grey 8 were the mocked-up
alternatives. Only `946.v32` changes. Other views keep 13 → 14 (gold coins and the like).
Second and third user passes: even plain black, the Amiga title lettering (2-pixel strokes,
1-pixel counters, letters touching: "VOLUME" read as "VOLUWE") was much harder to read than the
score line, which is drawn in font 69. `TEXT_CELS` in `makest.py` therefore redraws loop 0 cels
2-5 as black capitals of font 69 on grey 7, opaque and 9 rows high like the originals (the script
places them bottom-up by `CelHigh`). Capitals, because mixed case is wider and "Detail" ran into
"Volume" in the mock-up. The cels grow by `pad` columns each side (SPEED 1, DETAIL 2, GAME PAUSED
2, VOLUME 0); script 755 is patched to move DETAIL and SPEED left by their pad (SCRIPTS.md "Pause
panel titles centred"; DETAIL moves only 1, keeping clear of the button column's border, so it
sits 1 pixel right of its slider). An odd spare column goes to the left of the text.

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
- **Performance pass 2026-11-07** (walking benchmark `tests/bench_walk.txt`, game cycles in 45 s
  of emulated time; deterministic, two runs of one build give the same count): 302 -> 326
  (6.6 -> 7.1 cycles/s, +8%). (1) Kernel-call trace hook (hunk 4 `+$9ee`) skips its register
  saves and C calls when `KTRACE` is off: 302 -> 315. (2) Hunk 36 polygon geometry helpers
  (point sub/add `+$2cf2/$2d24`, dot `+$2d56`, cross sign `+$2d7c`, squared distance `+$2dbc`, used
  by path-finding and polygon tests) replaced by frame-less versions; the squared distance uses
  `mulu.w` on |dx| instead of the 32-bit library multiply (same low 32 bits since |dx| <= 65535):
  315 -> 324. (3) Cel drawing opaque runs (hunk 56 `+$578`): one inline loop per colour instead of
  a per-pixel `jsr` into the 32 plot routines: 324 -> 326 (the four bit-plane writes per pixel
  dominate; runs are at most 7 pixels and mostly 1-2 in the dithered art, so byte-wise packing
  does not pay; +0.6 % is within the noise below). All three are proven equal to the originals with `tools/equiv/run.sh`
  (WORKFLOW.md "Equivalence tests"), and three path-finding walks end on byte-identical screens.
  Remaining profile (Timer A): SCI `send` 12 % + property lookup 4.4 % + other hunk 23 ~3 %,
  cel loop ~10 %, hunk 36 polygon code ~7 %, sound tick ~3 %, shim display/blit ~5 %.
- **Selector lookups in `send` (2026-11-07).** Hatari's cycle profiler (instruction level,
  `tools/hprofmap.py`) showed the hottest loop in the game was the property scan in
  `hook_proplookup`: 3.9 % of all cycles, because every *method* send first scans the object's
  whole property selector list (30-50 entries) and misses. Fix kept: on an index-hint miss,
  `tabfind` looks the (table, selector) pair up in a 512-entry cache that also stores "absent".
  It needs no invalidation: each entry keeps the table's count and first/middle/last selector,
  and in KQ5's 190 scripts (with the `.SCR` patches) the 2341 property/method tables have 192
  distinct contents and no two different tables share that fingerprint (`tools/equiv/tabproof.py`),
  so an entry can never describe another table loaded at the same address later. Tables of 8 or
  fewer entries are scanned plainly. Proven register-exact against the original (`sendtest.py`,
  20000 lookups with tables replaced at reused addresses; a mutant without the fingerprint is
  caught). Cycle profile: lookup cost 5.6 % -> ~3.8 % of cycles. A second hook for the method
  dictionary scan (`+$286`) gave nothing (most tables have under 3 entries) and was removed.
- **Bytecode interpreter rewrite (2026-11-07, `st/src/pmachine.S`, ARCHITECTURE.md "Bytecode
  interpreter").** Hunk 4's dispatch loop and all opcode handlers, the call frame and `calle`
  helper, and hunk 23's `send` for bytecode sends are replaced. Loop: acc in d7, globals base in
  a3, self in a5 (Prog reloaded them from memory in every handler), written back only around
  calls out of the loop; dispatch is still `move.b (a0)+ / add / move.w (a6,d1.w) / jmp` (no
  cheaper form exists on a 68000). Send: the write-only debug send stack, `-$7132` and `-$4f3e`
  are dropped; locals are switched only when a method is called; script handle, locals, PC and
  params are saved only once a selector turns out to be a method, so property reads/writes
  (`(ego x?)`, `(ego x: 10 y: 20)`) run a short loop (`pm_sendfast`); the selector-table cache
  (`tabfind`, moved here from glue.S) is kept. Measured with `tools/bench3.py` (game cycles in
  45 s of each scene): loop only: walk 328 -> 326, town 381 -> 379, bakery 1647 -> 1641 (nothing:
  the loop was ~4.5 % of the time, send ~16 %); with send: 328/392/1710; with the send trimmed:
  341/412/1775; with the property fast path: **345/420/1791, sum 2356 -> 2556 (+8.5 %)**. Timer-A
  profile of the walk: interpreter + send 25 % of samples before, 17 % after; what remains is
  the class-chain walk per method send (~4 %), kernel-call dispatch and the per-selector work.
  Proven equal to Prog's interpreter with `tools/equiv/pmtest.py` (WORKFLOW.md "Equivalence
  tests": 900 random worlds per build, every opcode and error path, scripts moved under the
  running code). Not done: a cache that skips the class-chain walk (a method result depends on
  the whole chain; the table-fingerprint argument only identifies table contents, and KQ5's
  rooms share dictionary layouts, so an exact key was not found), and the C-level Send of
  kernel functions (hunk 23 `+$324`, ~2.5 %) still uses Prog's code.
- **Measuring:** the three-scene benchmark `tools/bench3.py` (room 1 walk, the user's "The Town"
  and "The Bakery" saves restored with `st/tests/bench_save.txt`) sums game cycles; start of day
  -> end: walk 302 -> 345 (+14 %), town 358 -> 420 (+17 %), bakery 1537 -> 1791 (+17 %). Game
  cycles are CPU-bound: `Game::play` is `(self doit:) (Wait gSpeed)` and a cycle takes ~8 ticks.
- **Benchmark noise between builds:** one build always gives the same cycle count, but two
  different builds shift timing, so game events (Cedric, random actions) drift and the count
  moves by a few cycles (~1-2 %). Treat differences under ~3 % as noise.
- The Speed slider / `egoMoveSpeed` default (why Graham crawled at 8 cycles/s): SCRIPTS.md.
- Open: faster display updates; the 1 MB memory target (ARCHITECTURE.md "Memory").
