# Sound: the YM2149 driver and the sound resources

Index: [`README.md`](README.md). Code: `st/src/ym.c`. Tools: `tools/sndvoices.py`, `tools/makesnd.py`.

## How Prog plays sound

Prog loads `amigasnd.drv` (the Amiga 4-voice sampled driver) and, when the loader gave it no
sample bank, falls back to `amiga3v.drv`: a port of Sierra's SCI1 PCjr/Tandy 3-voice driver that
plays the device-`$13` tracks of the sound resources with square waves. The ST driver
reimplements that driver on the YM2149 (3 tone channels, no noise, no samples). Its logic mirrors
`amiga3v.drv` (disassembly `work/amiga3v/disasm/hunk00.s`); the same logic is in ScummVM's
`engines/sci/sound/drivers/pcjr.cpp` (`SoundChannel_PCJr_SCI1`). `LoadSeg("amigasnd.drv")`
returns the shim's YM driver segment (`ym_seg`: next = 0, then `jmp stub_YmDriver`).

Prog's side (hunks 31, 37):

- Hunk 31 (DoSound init) builds `<dir>amigasnd.drv`, `LoadSeg`s it and calls driver function 0;
  if the patch number (`d0 & $7f`) is 5 or 9 it expects the loader's sample bank
  (`LoaderMsg+$20`); without it the driver is unloaded and `amiga3v.drv` is loaded instead.
  Otherwise the patch resource (type `$89`, number `d0 & $7f`, locked when bit 7 set) is loaded
  and its data passed to function 1 in a0. Then the tick server `H37_166e` is registered
  (`H29_12e`, AddIntServer) and function 3 is called once.
- Hunk 37 `+$6`: `DriverCall(func.w, ...)` (`func.w, args...` on the stack). Function 0 stores
  d1.b → `-$6e82` (the voice budget for mapping sound channels to the driver; a sound that needs
  more stays unmapped), d1 high byte → `-$6e84` (device type matched against the track type at
  `+$2124`), d0 high word >> 4 → `-$6e80`. Function 1: d1 = -1 means failure; d0 low/high words →
  `-$6e88/-$6e86`; then function 11 (reverb 0). Function 2 is preceded by master volume 15. The
  tick server skips the whole tick while `-$6e8e` (busy counter) is set, so driver calls never
  nest with Service.
- `amiga3v.drv` data: `$58` DMA bits, `$5c` chip-RAM copy of the 16-byte square wave (`$60`),
  `$72` Paula period table (4 words per semitone), `$456` patch copy (128 offsets + envelopes),
  `$858` velocity map, `$898` program, `$8a8` channel volume, `$8c8` hold, `$8d8` voices owed,
  `$8e8` bend, `$908` last voice, `$918` voice→channel, `$91c` voice note, `$920` sustained,
  `$924/$92c` age/release age, `$934/$93c/$940/$944` envelope offset/pos/counter/volume,
  `$948` released, `$94c` velocity volume, `$950` reverb, `$951` sound on, `$952` master.
  Function table at `$954`: 0 `$13b4`, 1 `$12f0`, 2 `$b4c`, 3 `$1092`, 4 `$9bc`, 5 `$a16`,
  7 `$a74`, 8 `$aec`, 10 `$afa`, 11 `$b86`, 12 `$b9a`, 13 `$bac`, 17 `$1240`; 6/9/14/15/16 `rts`.

## Driver interface (`*.drv`, entry = seglist+4, `d7` = function, arguments d0/d1/a0, results d0/d1)

- 0 GetDeviceInfo (d0 = `$0001_0065`: patch 101; d1 = `$0013_0004`: device `$13`, 4 voices
  announced, see "Voices"), 1 Init (a0 = patch 101 data or NULL; returns d0 = `$000f_0000`,
  d1 = 0), 2 Terminate, 3 Service (once per tick from Prog's VERTB server, i.e. our VBL),
  4 NoteOff / 5 NoteOn (d0 = channel, d1 = note | velocity << 16), 7 Controller (d1 = number |
  value << 16: 7 volume, $40 hold, $4b voices, $7b all notes off), 8 ProgramChange, 10 PitchBend
  (lsb | msb << 16), 11 reverb, 12 master volume 0–15, 13 sound on/off (`$ff` = read back),
  17 AskDriver (d0 = `$e0/$c0/$b0` << 16 | channel: query bend / program / controller value).
- Patch 101 (in the Amiga and DOS resources): 128 little-endian instrument offsets, then
  envelopes as (volume 0–15, ticks) pairs; ticks `$fe` = hold until note off, volume `$ff` =
  end of the envelope, which **stops the voice**. Prog passes the resource data to Init; the
  driver copies it (the resource may be purged). Consequences: an instrument like program 8
  (`15,0; $ff`) sounds for exactly one tick whatever the note length - the "chord hits" of the
  fanfare are such blips - while program 127 (`15,0; 15,$fe; 15,0`) holds at full volume until
  the note-off and program 18 (`13,0; 15,0; 14,0; 13,$fe; 11,0; 9,0; 7,0; 5,0; 3,0`) has a
  short attack, holds at 13 and releases over 5 ticks. All envelopes of patch 101 can be listed
  with `sndvoices.load_patch`.
- Voices: controller `$4b` assigns voices to channels (round-robin per channel, oldest/released
  voice stolen); the counts come from the sound header and the sound data itself reassigns
  voices during a piece. The interpreter budgets the voices the driver announces (GetDeviceInfo
  d1 low byte, stored at `-$6e82`): a sound whose channels do not fit the budget is left
  unmapped, i.e. silent, until voices free up (sound 500 asks 1+2+1 and only started half-way
  when 3 was announced). The driver therefore announces 4 like `amiga3v.drv`, and when the
  interpreter hands out more than 3, a channel that would get nothing takes one voice from a
  channel holding two (`voice_steal_for`, an addition to the Amiga logic). A "borrow idle voice"
  experiment in the driver was reverted as unnecessary (the sound data reallocates voices itself).
- Volume = Sierra's PCjr formula (channel volume, velocity table, envelope, master) giving an
  attenuation in 2 dB steps, scaled by 2/3 for the YM's ~3 dB steps (`attn_to_level`). Pitch:
  period = 125000 / f, quarter-semitone table for one octave, bend ±12 semitones like the original.
- Hardware writes are done with interrupts masked (register select + data must not be split by
  the VBL); shadow registers avoid redundant writes; mixer bits 6–7 (port directions) are kept.
- A file `NOSND` in the game folder selects the old silent driver (in `glue.S`).
- `YM_TRACE 1` in ym.c logs every call except Service/AskDriver with the VBL count:
  `ym 1345: f7 d0=100001 d1=5b0007` = controller 7 = $5b on channel 1; `f8 d0=4 d1=7f` = program
  127 on channel 4; `f5 d0=4 d1=62003d` = note-on 61 velocity 98; a note-on with velocity 0
  (`f5 d0=4 d1=3d`) is a note-off. Set it back to 0 and rebuild before playing (it slows the game).

## Which sounds play

208 of the 244 Amiga sounds have a `$13` track; 36 have only MT-32/Amiga tracks (types 6 and
$c) and stay silent, including 799 (the largest, intro cartoon?), 889, 863, 880. The DOS
resources are no better (PCjr owners had the same silence), so playing those would mean
rendering the type-`$c` (or Adlib) tracks on the YM - a possible later extension (the
interpreter accepts one device type, hunk 37 `+$2124` compares it with the track type).

Sound resource layout (SCI1): first byte of each track = device type, then 6-byte channel
entries (2 unknown bytes, data offset, data size), `$ff` ends a track, a second `$ff` ends the
header. Channel data = 2 bytes (channel number | flags, poly/priority) + MIDI-like events with
delta ticks (`$f8` = +240), running status, sysex skipped, `$fc` = end. Channel 15 is the control
channel (tempo, cues: `cf n` = cue n). Amiga sounds carry types 6, $c (all), $13 (208 of 244),
some 0/9/$12/$16; DOS sounds carry 0, 8, 9, $c, $12, $13 (205 of 245 have $13).

## Verification by recording

Verified 2026-10-17 00:11 with `st/run.sh 5200 tests/intro_sound.txt --sound 44100 --avirecord
--avi-file snd.avi`, `ffmpeg -i st/hd/snd.avi -vn snd.wav`, `sox snd.wav -n spectrogram`: the
Sierra fanfare plays (three clean square-wave voices). Reference clips:
`work/sound/fanfare_emulated.wav` (a 4 s two-channel trill C5/G5 vs D5/A5 at 10 Hz, i.e. a
drum-roll imitation, then chord hits), `logo_blip_emulated.wav` (channel 5, G2 toggled three
times), `logo_emulated.wav`. Headless sound capture has since stopped working (WORKFLOW.md
"Headless-run problems"); a windowed run with sound is fine. The user confirmed title music,
intro cartoon and the Sierra fanfare sound right.

## Listening to single voices (`tools/sndvoices.py`)

`sndvoices.py SOUND|N.snd [PATCH101] OUTDIR --prefix P --start N --index FILE` renders every
channel of every device track of an SCI1 sound resource (or of a generated `N.snd` patch file)
to numbered square-wave wavs, plus a mix per track (duplicate channels across tracks are
skipped), with ym.c's pitch/volume mapping and the patch 101 envelopes on the `$13` track (other
tracks get a flat envelope, so only their notes are meaningful). The index lists channel,
polyphony, note count, range and programs. Ticks are rendered at 60 Hz.

- `work/sound/500_voices.txt` + `amiga500_NN_*.wav` / `dos500_NN_*.wav`: the Sierra fanfare
  (sound 500) channels of both resource sets. The DOS `$13` (PCjr) track is a 3-channel
  arrangement made for 3 voices, while the Amiga `$13` track is the 4-voice Amiga arrangement
  (channels 2, 3 (poly 2), 4, 5, 1).
- `work/sound/st500_voices.txt` + `st500_NN_*.wav`: the patched `st/hd/500.snd` as the ST plays
  it; `st500_18_t13_mix.wav` is the three voices together, `st500_15_t13_ch3.wav` the trill,
  `st500_16_t13_ch4.wav` the chord hits. `st500alt_*` = the program-9 trill alternative (below).

## Patched sounds (`tools/makesnd.py st/hd` → `st/hd/N.snd`)

Patch files with header `$84 $00` override sound resources (Prog looks for `*.snd`). The
`SOUNDS` table has, per sound: `keep` = per device track the channels to keep (the other
channels are dropped from the track header; their data stays in the file and only the offsets
move; channel 15 is always kept) and `edits` = changes to one channel's event data (the edited
channel is copied to the end of the resource and the header entry repointed, so other tracks
sharing the data are untouched). Edits: `program {OLD: NEW}` rewrites the channel's program changes in place;
`hold_last_note PROGRAM` inserts a program change before the channel's last note-on (`<delta> Cn
prog 00 9n note vel`, the explicit note status restores the running status). Several edits on one
channel are applied in order. `drop` = device tracks to remove from the header entirely (the
sound then has no `$13` track and is silent on the ST, like the 36 sounds below).

Sound 500 (the Sierra fanfare, Amiga `$13` track, 2026-10-17):

- Keeps channels 3, 4 and 1 (user's choice): the drum-roll trill (3, 2 voices), the chord hits
  (4) and the high closing notes (1); the bass (2) and the sustained chord (5) are gone. The
  sound's own data reassigns voices with controller `$4b` during the piece (channel 3: 2 then 1,
  channels 4 and 1: 0 then 1 just before their notes), so the three channels never need more
  than 3 voices and no stealing happens.
- **Why it was choppy:** the Amiga `$13` track is the Amiga arrangement with the Amiga's
  instrument numbers kept: channel 3 selects program 17 and then overrides it with 6, channel 4
  selects 18 and then 8. In patch 101, programs 0-6, 8 and 10 share the envelope `15,0; $ff` -
  one tick of sound, then the voice stops - so every trill note (5-9 ticks), channel 3's final
  note 77 (ticks 363-780, held under the chord hits) and the four chord hits were one-tick
  clicks. No other sound in the game uses programs 6 or 8 (`$13` program usage counted over all
  244 Amiga sounds: 12, 17, 31, 23, 127, 11, 19, 18 ... are the common ones), and the Amiga
  itself never plays this track (it uses the sampled `$06` track), so nobody at Sierra heard it.
  The fix in `makesnd.py` is the `program` edit: 6 → 17 on channel 3 (3-tick attack, hold at
  15, 5-tick release: the trill pulses and the final note is held to the end) and 8 → 18 on
  channel 4 (2-tick attack, hold at 13, 5-tick release: the three hits are stabs and the final
  chord 61, ticks 558-778, is held). The earlier `hold_last_note 127` on channel 4 is no longer
  needed. Measured on the renderings (non-silent 1 ms slices): channel 3 went from 6 % to 88 %
  of its 13 s, channel 4 from 1 % to 34 %.
- Alternative (rendered, not chosen): program 9 for the trill (3 ticks at 15 then a 7-tick
  decay, no hold: a crisper roll) plus `hold_last_note 17` for the final note:
  `work/sound/st500alt_18_t13_mix.wav` (three voices), `st500alt_15_t13_ch3.wav` (channel 3).
  To adopt it, set channel 3's edits to `('program', {6: 9}), ('hold_last_note', 17)`.
- Not yet re-verified in Hatari after this change (the file format is unchanged; the previous
  `500.snd` was verified headless with `YM_TRACE`: `Open("500.snd")`, note-ons on channels 3, 4,
  1 only). `sndvoices.py --index` appends to the index file - delete it before re-rendering.

Sound 3 (desert ambience, 2026-10-17): the desert region (script 15, `rm015::init`) loops sound
2 on global 397 and sound 3 on global 329; room 14 (desert edge) plays them too. Sound 2 (wind)
has no `$13` track. Sound 3's `$13` track is note 84 (~1 kHz) retriggered every 2 ticks on two
interleaved channels (12, 13; program 14, velocity 14) - a faint insect chirp on the MT-32/Amiga,
a fast high chatter on square waves. The user asked for it to be shut off, so `makesnd.py` drops
the `$13` track (`3: {'drop': [0x13]}`). For a faint version later: lower controller 7 (127) on
channels 12/13 instead. First attempt dropped sound 16 by mistake: that is the bee buzz of room
11 (`deathByBees`), left as it was. Lesson: low script numbers are rooms (script 11 = room 11);
find the room's sounds with `scidisasm.py` (`pushi 43 ; number`, `push1`, value; the value line
is often mislabelled with a selector name) and check the region script from `setRegions`.
Patch files are found when the interpreter starts: restart the game after adding an `N.snd`.

## Tick rate / tempo (open)

The game and the music run at the VBL rate; Hatari's PAL TOS gives 50 Hz where the Amiga NTSC
interpreter expects 60 (music 17 % slow). Switching the ST to 60 Hz (`$ff820a`) or a timer-based
tick would fix the tempo - not done yet. Also open: no noise channel (percussion), the 36 silent
sounds (above).
