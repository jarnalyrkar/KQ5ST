#!/usr/bin/env python3
"""Speech from the CD release for the ST:  makespeech.py CDDIR OUTDIR  -> OUTDIR/SPEECH.DAT

The CD release (KQ5 CD, 1.000.052) speaks each line with (Say N) / Talker clip N, where the
floppy/Amiga scripts print text (module, index) with PrintDC or proc0_28. LINES maps the text
lines to the CD clips (from a line diff of the sluicebox CD and Amiga scripts, SOUND.md
"Speech"). The clips (8-bit unsigned PCM, 11025 Hz, AUDIO001.MAP/.002) are resampled to the
STE DMA rate 12517 Hz and stored signed.

SPEECH.DAT, big-endian:  'KQSP', u16 count, u16 rate code (1 = 12517 Hz), u32 largest clip,
then count entries (u16 module, u16 index, u32 offset from file start, u32 length; sorted by
module, index), then the samples (each clip at an even offset, even length)."""
import sys, os, struct
import numpy as np

RATE_IN, RATE_OUT = 11025, 12517

# (text module, text index, CD clip)
LINES = [
    # Room 1, outside Crispin's house (rm001)
    (1, 0, 162), (1, 1, 9070), (1, 2, 163), (1, 3, 171), (1, 4, 164), (1, 5, 165),
    (1, 6, 166), (1, 7, 167), (1, 9, 168), (1, 10, 169), (1, 12, 170),
    # rm001 introRoomScript: Cedric (view 75) and Graham (160) after the intro (CD: Talker
    # conversation local173 = Cedric 9106, Graham 7040, Cedric 9107, Graham 7041)
    (1, 13, 9106), (1, 14, 7040), (1, 15, 9107), (1, 16, 7041),
]

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
    for mod, idx, n in LINES:
        if n in clips: continue
        vol, off, sz = amap[n]
        with open(os.path.join(cd, 'AUDIO001.%03d' % vol), 'rb') as f:
            f.seek(off); raw = np.frombuffer(f.read(sz), np.uint8)
        s = resample(raw).tobytes()
        if len(s) & 1: s += b'\0'
        clips[n] = s
    lines = sorted(LINES)
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
