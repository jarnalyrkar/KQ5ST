#!/usr/bin/env python3
"""Speech from the CD release for the ST:  makespeech.py CDDIR OUTDIR  -> OUTDIR/SPEECH.DAT

The CD release (KQ5 CD, 1.000.052) speaks each line with (Say N) / Talker clip N, where the
floppy/Amiga scripts print text (module, index) with PrintDC or proc0_28. LINES maps the text
lines to the CD clips (from a line diff of the sluicebox CD and Amiga scripts, SOUND.md
"Speech"). The clips (8-bit unsigned PCM, 11025 Hz, AUDIO001.MAP/.002) are resampled to the
STE DMA rate 12517 Hz and stored signed.

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
] + [(602, i, 3005 + i) for i in range(14)]      # Talk to Cedric, per room (CD local71)

# Literal strings in the Amiga scripts (not text resources) that the CD speaks: matched by a
# hash of the exact bytes (speech.c str_key). (text, CD clip)
STRINGS = [
    (b'"Come ON, Graham! There\'s nothing here. Let\'s go!"', 3020),   # rm001 global325 (owl nag)
]

def str_key(b):
    """FNV-1a 32 of the string -> (module, index) with module >= $f000 (text modules are < 1000)."""
    h = 0x811c9dc5
    for c in b: h = ((h ^ c) * 0x01000193) & 0xffffffff
    return 0xf000 | (h >> 16) & 0xfff, h & 0xffff

def read_map(cd):
    d = open(os.path.join(cd, 'AUDIO001.MAP'), 'rb').read()
    m = {}
    for i in range(0, len(d) - 9, 10):
        n, vo, sz = struct.unpack('<HII', d[i:i + 10])
        m.setdefault(n, (vo >> 28, vo & 0xfffffff, sz))
    return m

def resample(u8):
    """Windowed-sinc interpolation 11025 -> 12517 Hz (upsampling: no extra low-pass needed)."""
    x = u8.astype(np.float64) - 128.0
    n_out = int(len(x) * RATE_OUT / RATE_IN)
    t = np.arange(n_out) * (RATE_IN / RATE_OUT)
    base = np.floor(t).astype(np.int64); frac = t - base
    taps = 8
    y = np.zeros(n_out)
    xp = np.concatenate([np.zeros(taps), x, np.zeros(taps + 1)])
    for k in range(-taps + 1, taps + 1):
        d = k - frac
        w = np.sinc(d) * (0.5 + 0.5 * np.cos(np.pi * d / taps))
        y += xp[base + k + taps] * w
    return np.clip(np.round(y), -128, 127).astype(np.int8)

def main():
    cd, out = sys.argv[1], sys.argv[2]
    amap = read_map(cd)
    clips = {}
    entries = LINES + [str_key(t) + (n,) for t, n in STRINGS]
    assert len({(m, i) for m, i, n in entries}) == len(entries), 'duplicate key'
    for mod, idx, n in entries:
        if n in clips: continue
        vol, off, sz = amap[n]
        with open(os.path.join(cd, 'AUDIO001.%03d' % vol), 'rb') as f:
            f.seek(off); raw = np.frombuffer(f.read(sz), np.uint8)
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
          '%.1f s' % (sum(map(len, clips.values())) / RATE_OUT))

if __name__ == '__main__':
    main()
