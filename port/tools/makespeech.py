#!/usr/bin/env python3
"""Speech from the CD release for the ST:  makespeech.py CDDIR OUTDIR  -> OUTDIR/SPEECH.DAT

The CD release (KQ5 CD, 1.000.052) speaks each line with (Say N) / Talker clip N, where the
floppy/Amiga scripts print text (module, index) with PrintDC or proc0_28. LINES maps the text
lines to the CD clips (from a line diff of the sluicebox CD and Amiga scripts, SOUND.md
"Speech"). The clips (8-bit unsigned PCM, 11025 Hz, AUDIO001.MAP/.002) are resampled to the
STE DMA rate 12517 Hz, raised to full scale and stored signed. The intro cartoon has one long CD recording per scene
instead of a clip per line; INTRO_CUTS gives each text line a piece of it (tools/speechalign.py).

SPEECH.DAT, big-endian:  'KQSP', u16 count, u16 rate code (1 = 12517 Hz), u32 largest clip,
then count entries (u16 module, u16 index, u32 offset from file start, u32 length; sorted by
module, index; a literal string has a hashed key, see str_key), then the samples (each clip at an even offset, even length)."""
import sys, os, struct
import numpy as np

RATE_IN, RATE_OUT = 11025, 12517

# (text module, text index, CD clip). Matched by hand from the sluicebox CD and Amiga scripts
# (same code order; SOUND.md "Speech").
LINES = [
    # Room 1, outside Crispin's house (rm001): narrator Look/Do lines
    (1, 0, 162), (1, 1, 9070), (1, 2, 163), (1, 3, 171), (1, 4, 164), (1, 5, 165),
    (1, 6, 166), (1, 7, 167), (1, 9, 168), (1, 10, 169), (1, 12, 170),
    # rm001 Cedric: Do on the ornament, Look at the cellar door (CD proc762_1 3021, 3022)
    (1, 8, 3021), (1, 11, 3022),
    # rm001 introRoomScript: Cedric (view 75) and Graham (160) after the intro (CD: Talker
    # conversation local173 = Cedric 9106, Graham 7040, Cedric 9107, Graham 7041)
    (1, 13, 9106), (1, 14, 7040), (1, 15, 9107), (1, 16, 7041),
    # Main (script 0, every room): cartoon captions 0-1, inventory used on Graham 2-21 (CD Say
    # 136-155), Cedric hurt / talking to yourself 22-24, waving the wands 27-29. 25-26 are the
    # Quit/debug dialogs.
    (0, 0, 82), (0, 1, 83),
] + [(0, i, 134 + i) for i in range(2, 22)] + [
    (0, 22, 157), (0, 23, 158), (0, 24, 130), (0, 27, 134), (0, 28, 135), (0, 29, 156),
    # KQInv (every room): text 758 (pouch, sack, amulet, wands; 2 is a formatted pouch line,
    # not covered) ...
    (758, 0, 96), (758, 1, 100), (758, 3, 132), (758, 4, 115), (758, 5, 119), (758, 6, 121),
    (758, 7, 128),
] + [
    # ... and text 749 = the items' `description` (Look), joined by item name with the CD's
    (749, a, c) for a, c in [(1, 84), (2, 85), (3, 86), (4, 87), (5, 88), (6, 89), (7, 90), (8, 91),
        (9, 92), (10, 93), (11, 94), (12, 95), (15, 104), (16, 105), (17, 106), (18, 107), (20, 110),
        (21, 111), (22, 112), (23, 113), (24, 114), (25, 116), (26, 117), (27, 118), (28, 120),
        (29, 122), (30, 123), (31, 124), (32, 692), (33, 125), (34, 126), (35, 127), (36, 129),
        (37, 88)]
] + [
    # owl region (script 202, the forest rooms with Cedric): inventory on Cedric, "not listening"
    (202, 0, 3019), (202, 1, 75), (202, 2, 76), (202, 3, 77), (202, 4, 78),
] + [(600, i, c) for i, c in enumerate(          # Look at Cedric, per room (CD local52)
    [57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 66, 67, 68, 69, 70, 71, 72, 73, 74])
] + [(602, i, 3005 + i) for i in range(14)] + [  # Talk to Cedric, per room (CD local71)
    # Crispin's house (rm076, entered from room 1): Crispin 0-2, Graham 3. CD rm076: (Say 9109),
    # then the Talker array [0 9110 0 9111 1 9100]; transcribed to check (2026-11-19).
    (76, 0, 9109), (76, 1, 9110), (76, 2, 9111), (76, 3, 9100),
    # Room 2, the snake (tools/roomclips.py; 2026-11-19). Reworded lines take the CD wording
    # (maketext.py). 0, 1 Cedric's warning, 3, 4 Look, 6 Talk, 7 other items. Not covered: 2 2
    # (the CD changed the tambourine scene: 5501 Graham "Be gone, you slithery varmint"), 2 5 (Do:
    # on the CD the snake itself answers, 5502); the CD's snake death (178) has no Amiga text.
    (2, 0, 177), (2, 1, 5500), (2, 3, 172), (2, 4, 173), (2, 6, 176), (2, 7, 175),
]

# The intro cartoon (rooms 100-109, 114): the CD speaks each scene as one recording (clips
# 10103-10113, music and effects mixed in). (text module, index, CD clip, start s, end s), made by
# tools/speechalign.py from whisper word timestamps, two ends set from the loudness by hand.
# Every cut was re-transcribed and compared with its text (SOUND.md "The intro cartoon").
INTRO_CUTS = [
    # clip 10103
    (102, 0, 10103, 2.16, 5.61), (102, 1, 10103, 10.42, 13.53), (102, 2, 10103, 13.88, 15.10),
    # clip 10104
    (103, 0, 10104, 3.24, 8.34), (103, 1, 10104, 8.34, 11.22),
    # clip 10105
    (104, 0, 10105, 1.82, 15.77), (104, 1, 10105, 15.86, 18.24),
    # clip 10106
    (105, 0, 10106, 2.72, 19.40),
    # clip 10107
    (103, 2, 10107, 0.00, 6.81), (103, 3, 10107, 7.52, 14.78),
    # clip 10108
    (114, 0, 10108, 2.98, 15.65), (114, 1, 10108, 16.18, 24.06), (114, 2, 10108, 24.30, 28.00),
    (114, 3, 10108, 44.04, 46.67), (114, 4, 10108, 46.84, 52.75), (114, 5, 10108, 53.28, 56.88),
    (114, 6, 10108, 56.88, 66.03), (114, 7, 10108, 66.88, 73.15), (114, 8, 10108, 73.84, 75.43),
    (114, 9, 10108, 75.90, 81.61), (114, 10, 10108, 82.42, 91.37), (114, 11, 10108, 103.42, 105.49),
    (114, 12, 10108, 105.98, 113.49), (114, 13, 10108, 113.94, 124.68),
    # clip 10109
    (100, 1, 10109, 0.70, 3.47), (100, 2, 10109, 10.46, 15.00),
    # clip 10111
    (107, 1, 10111, 39.35, 42.33), (107, 0, 10111, 42.36, 45.30),
    # clip 10112
    (108, 0, 10112, 10.64, 15.05), (108, 1, 10112, 16.88, 22.27), (108, 2, 10112, 27.56, 31.07),
    (108, 3, 10112, 36.34, 44.03), (108, 4, 10112, 49.48, 54.77), (108, 5, 10112, 54.77, 56.86),
    # clip 10113
    (109, 0, 10113, 8.30, 21.01), (109, 1, 10113, 21.02, 27.35), (109, 2, 10113, 27.35, 37.81),
    (109, 3, 10113, 38.20, 44.11), (109, 4, 10113, 44.11, 46.74), (109, 5, 10113, 46.74, 53.52),
    (109, 6, 10113, 53.66, 56.11), (109, 7, 10113, 56.18, 59.14), (109, 8, 10113, 59.28, 62.47),
    (109, 9, 10113, 66.60, 78.01), (109, 23, 10113, 106.58, 109.53), (109, 24, 10113, 111.02, 113.90),
    (109, 10, 10113, 114.52, 117.96), (109, 11, 10113, 117.96, 119.79), (109, 12, 10113, 121.22, 122.71),
    (109, 13, 10113, 122.71, 127.27), (109, 14, 10113, 127.27, 134.51), (109, 15, 10113, 138.92, 150.12),
    (109, 16, 10113, 150.12, 159.49), (109, 17, 10113, 159.98, 166.17), (109, 18, 10113, 166.17, 168.98),
    (109, 19, 10113, 168.98, 169.95), (109, 20, 10113, 169.95, 173.17), (109, 21, 10113, 173.50, 176.07),
    (109, 22, 10113, 176.52, 180.88),
]

# Literal strings in the Amiga scripts (not text resources) that the CD speaks: matched by a
# hash of the exact bytes (speech.c str_key). (text, CD clip)
# Cedric's nag per forest room (`lofsa "..."; sag 325` in the room script; the CD sets the clip
# number instead, `ldi N; sag 325`, found in its RESOURCE.001 by that byte pattern). Not covered:
# room 12 (the CD's clip 3051 is missing from its audio), room 40 (the CD reuses room 10's clip,
# whose words differ from the Amiga text).
STRINGS = [
    (b'"Come ON, Graham! There\'s nothing here. Let\'s go!"', 3020),           # room 1
    (b'"There\'s nothing interesting around here. Come on!"', 3023),           # room 2
    (b'"Let\'s DO something, Graham!"', 3025),                                 # room 3
    (b'"I\'m getting bored, Graham. Let\'s move on."', 3030),                  # room 6
    (b'"You can see there\'s nothing here, Graham!"', 3033),                   # room 7
    (b'"We\'ve got better things to do than stand around here, Graham!"', 3035), # room 8
    (b'"Come on, Graham. Let\'s go someplace else!"', 3041),                   # room 9
    (b'"Let\'s get a move-on, Graham. There isn\'t anything here."', 3044),    # room 10
    (b'"We\'ve got things to do, Graham! Come on!"', 3045),                    # room 11
    (b'"Let\'s move on, Graham!"', 3053),                                      # room 13
    (b'"This is getting tedious, Graham. Can we go now?"', 3055),              # room 27
    (b'"It\'s cold, Graham! Let\'s get moving!"', 3057),                       # rooms 29, 35
    (b'"Let\'s look for another way around this!"', 3059),                     # room 30
    (b'"There must be another way!"', 3062),                                   # room 31
    (b'"Come on, Graham! Let\'s explore the beach!"', 3066),                   # room 44
    (b'"I\'m tired of this place. Let\'s go somewhere else."', 3068),          # room 45
    (b'"Come on, Graham! Let\'s explore someplace else!"', 3070),              # rooms 46, 51, 111
    (b'"Come on, Graham! This place gives me the shivers!"', 3083),            # rooms 52, 53, 54
    # room 2's own copy of Main's tambourine line (no quotes), CD clip 174
    (b"Graham hits and shakes the tambourine with much ruckus, but finds it doesn't accomplish anything.", 174),
]

# The Amiga's sampled sound effects that makesnd.py 'sample' turns on (the music drivers start
# them, speech.c speech_sample): key ($e000, sound number); the sample is the `$fe` channel of the
# sound's type-6 track (fe 00, u16 rate, u16 size, u16 loop start, u16 loop end, signed 8-bit).
SAMPLES = [83]                  # Graham's fall (peak 19 of 127: raised up to x6)
SRC_SOUND = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'extracted', 'res_amiga', 'sound')

def amiga_sample(n):
    d = open(os.path.join(SRC_SOUND, str(n)), 'rb').read()
    p = 0
    while d[p] != 0xff:
        t = d[p]; p += 1
        while d[p] != 0xff:
            off = struct.unpack_from('<H', d, p + 2)[0]; p += 6
            if t == 6 and d[off] == 0xfe:
                rate, size = struct.unpack_from('<HH', d, off + 2)
                s = np.frombuffer(d[off + 10:off + 10 + size], np.int8).astype(np.int16) + 128
                return resample(s.astype(np.uint8), rate, 6.0).tobytes()
        p += 1
    raise ValueError('sound %d has no sample' % n)

def str_key(b):
    """FNV-1a 32 of the string -> (module, index) with module >= $f000 (text modules are < 1000)."""
    h = 0x811c9dc5
    for c in b: h = ((h ^ c) * 0x01000193) & 0xffffffff
    return 0xf000 | (h >> 16) & 0xfff, h & 0xffff

def audio_file(cd, name):
    """The CD files may be stored in upper or lower case."""
    p = os.path.join(cd, name)
    return p if os.path.exists(p) else os.path.join(cd, name.lower())

def read_map(cd):
    d = open(audio_file(cd, 'AUDIO001.MAP'), 'rb').read()
    m = {}
    for i in range(0, len(d) - 9, 10):
        n, vo, sz = struct.unpack('<HII', d[i:i + 10])
        m.setdefault(n, (vo >> 28, vo & 0xfffffff, sz))
    return m

def resample(u8, rate_in=RATE_IN, max_gain=3.0):
    """Windowed-sinc interpolation rate_in -> 12517 Hz (rate_in <= 12517: no extra low-pass;
    above it, the samples' 13-22 kHz, a little aliasing is accepted)."""
    x = u8.astype(np.float64) - 128.0
    n_out = int(len(x) * RATE_OUT / rate_in)
    t = np.arange(n_out) * (rate_in / RATE_OUT)
    base = np.floor(t).astype(np.int64); frac = t - base
    taps = 8
    y = np.zeros(n_out)
    xp = np.concatenate([np.zeros(taps), x, np.zeros(taps + 1)])
    for k in range(-taps + 1, taps + 1):
        d = k - frac
        w = np.sinc(d) * (0.5 + 0.5 * np.cos(np.pi * d / taps))
        y += xp[base + k + taps] * w
    # peak to ~124 (the CD clips peak at 46-128, median 81; with music ducked on the ST the voices
    # were still too quiet, 2026-11-19), at most x3 so quiet clips do not bring up their noise
    peak = np.abs(y).max()
    if peak > 0: y *= min(max_gain, 124.0 / peak)
    return np.clip(np.round(y), -128, 127).astype(np.int8)

def main():
    cd, out = sys.argv[1], sys.argv[2]
    amap = read_map(cd)
    clips = {}
    # a source is (CD clip, start, end) in samples at 11025 Hz; None = the whole clip
    entries = [(m, i, (n, None, None)) for m, i, n in LINES + [str_key(t) + (n,) for t, n in STRINGS]]
    entries += [(m, i, (n, round(a * RATE_IN), round(b * RATE_IN))) for m, i, n, a, b in INTRO_CUTS]
    entries += [(0xe000, n, ('sample', n)) for n in SAMPLES]
    assert len({(m, i) for m, i, n in entries}) == len(entries), 'duplicate key'
    for mod, idx, n in entries:
        if n in clips: continue
        if n[0] == 'sample':
            s = amiga_sample(n[1])
            clips[n] = s + b'\0' if len(s) & 1 else s
            continue
        vol, off, sz = amap[n[0]]
        with open(audio_file(cd, 'AUDIO001.%03d' % vol), 'rb') as f:
            f.seek(off); raw = np.frombuffer(f.read(sz), np.uint8)[n[1]:n[2]]
        s = resample(raw).tobytes()
        if len(s) & 1: s += b'\0'
        clips[n] = s
    lines = sorted(entries)
    head = 12 + 12 * len(lines)
    blobs, where, pos = [], {}, head
    for n, s in clips.items():
        where[n] = pos; blobs.append(s); pos += len(s)
    hdr = b'KQSP' + struct.pack('>HHI', len(lines), 1, max(len(s) for s in clips.values()))
    for mod, idx, n in lines:
        hdr += struct.pack('>HHII', mod, idx, where[n], len(clips[n]))
    path = os.path.join(out, 'SPEECH.DAT')
    open(path, 'wb').write(hdr + b''.join(blobs))
    print('wrote', path, pos, 'bytes,', len(lines), 'lines,', len(clips), 'clips,',
          '%.1f s' % (sum(map(len, clips.values())) / RATE_OUT), 'largest %d' % max(map(len, clips.values())))

if __name__ == '__main__':
    main()
