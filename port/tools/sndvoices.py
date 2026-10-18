#!/usr/bin/env python3
"""Render every channel of an SCI1 sound resource to numbered square-wave wav files so each
voice can be listened to on its own (one wav per channel of every device track, plus a mix of
each track). Volume, pitch and the patch-101 envelopes follow st/src/ym.c (the ST's YM2149
driver); other tracks (Adlib/MT-32/Amiga) are rendered with a flat "15, hold" envelope, i.e.
only their notes are meaningful, not their timbre.

usage: sndvoices.py SOUNDFILE|N.snd [PATCH101] OUTDIR [--prefix P] [--start N] [--rate 44100] [--index F]
writes OUTDIR/P_NN_tXX_chY.wav, OUTDIR/P_NN_tXX_mix.wav and appends to the index file (default
OUTDIR/P_index.txt). A channel whose events are identical to an earlier one (the device tracks
share a lot) is not written again; the index says which number it equals."""
import sys, os, struct, numpy as np

DEVICES = {0x00: 'Adlib', 0x04: 'CMS', 0x06: 'Amiga', 0x08: 'Casio', 0x09: 'FB-01/Casio',
           0x0c: 'MT-32', 0x12: 'PC speaker', 0x13: 'PCjr/Tandy 3-voice', 0x16: 'Mac?'}
TICK = 60.0                                         # SCI ticks per second (Amiga NTSC)

BASE_PERIOD = [15289, 15070, 14854, 14641, 14431, 14224, 14020, 13819, 13621, 13426, 13233, 13043,
    12856, 12672, 12490, 12311, 12135, 11961, 11789, 11620, 11454, 11290, 11128, 10968,
    10811, 10656, 10503, 10353, 10204, 10058, 9914, 9772, 9631, 9493, 9357, 9223,
    9091, 8961, 8832, 8705, 8581, 8458, 8336, 8217, 8099, 7983, 7869, 7756]
VELO_TAB = [1, 3, 6, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 14, 15, 15]
ATTN_TO_LEVEL = [15, 14, 14, 13, 12, 12, 11, 10, 10, 9, 8, 8, 7, 6, 6, 0]

def note_period(note, bend):
    units = bend // 168
    q = note * 4 + (units - 49 if units > 48 else units - 48)
    q = max(0, min(q, 127 * 4 + 3))
    octv, p = q // 48, BASE_PERIOD[q % 48]
    if octv: p = (p + (1 << (octv - 1))) >> octv
    return max(1, min(p, 4095))

def level(chvol, vel, env, master=15):
    vol = ((chvol >> 3) or 1) if chvol else 0
    velo = VELO_TAB[vel >> 3] if vel else 0
    tl = ((vol * velo // 15) * env // 15) * master
    if 0 < tl < 15: tl = 15
    return ATTN_TO_LEVEL[15 - tl // 15]

def ym_amp(lv):                                     # YM2149 16-level DAC, ~3 dB per step
    return 0.0 if lv == 0 else 10 ** (-(15 - lv) * 3 / 20)

# --- resource parsing ------------------------------------------------------------------------
def parse_header(d):
    tracks, p = [], 0
    while d[p] != 0xff:
        t, chans = d[p], []; p += 1
        while d[p] != 0xff:
            off, sz = struct.unpack_from('<HH', d, p + 2)
            chans.append((d[off] & 15 if d[off] < 0xfe else d[off], d[off + 1] & 15, d[off + 1] >> 4, d[off + 2:off + sz]))
            p += 6
        p += 1
        tracks.append((t, chans))
    return tracks

def parse_events(data):
    """-> list of (tick, status, d1, d2); sysex skipped; stops at $fc."""
    ev, p, t, status = [], 0, 0, 0
    while p < len(data):
        delta = 0
        while p < len(data) and data[p] == 0xf8: delta += 240; p += 1
        if p >= len(data): break
        delta += data[p]; p += 1; t += delta
        if p >= len(data): break
        if data[p] & 0x80: status = data[p]; p += 1
        if status == 0xfc: break
        if status == 0xf0:
            while p < len(data) and data[p] != 0xf7: p += 1
            p += 1; continue
        kind = status & 0xf0
        if kind in (0xc0, 0xd0): ev.append((t, status, data[p], 0)); p += 1
        else: ev.append((t, status, data[p], data[p + 1])); p += 2
    return ev

def load_patch(path):
    env = {}
    if not path: return env
    p = open(path, 'rb').read()
    for i in range(128):
        off = struct.unpack_from('<H', p, 2 * i)[0]
        s, q = [], off
        while q + 1 < len(p) and p[q] != 0xff: s.append((p[q], p[q + 1])); q += 2
        if s: env[i] = s
    return env

# --- rendering -------------------------------------------------------------------------------
class Voice:
    def __init__(self, note, vel, envelope):
        self.note, self.vel, self.env, self.pos, self.cnt, self.vol = note, vel, envelope, 0, 0, 0
        self.rel = self.sus = False; self.dead = False; self.phase = 0.0
    def tick(self):
        if self.cnt == 0xfe:
            if not self.rel: return
            self.cnt = 0
        elif self.cnt: self.cnt -= 1; return
        if self.pos >= len(self.env): self.dead = True; return
        self.vol, self.cnt = self.env[self.pos]; self.pos += 1

def render_channel(events, envelopes, rate, use_env, end_tick):
    spt = rate / TICK
    out = np.zeros(int((end_tick + 2) * spt) + 1, dtype=np.float64)
    voices, chvol, bend, prog, hold = [], 127, 0x2000, 0, 0
    ei, notes = 0, 0
    for tick in range(end_tick + 1):
        while ei < len(events) and events[ei][0] <= tick:
            _, st, a, b = events[ei]; ei += 1; k = st & 0xf0
            if k == 0x90 and b:
                notes += 1
                for v in voices:
                    if v.note == a and not v.dead: v.dead = True
                env = envelopes.get(prog, [(15, 0xfe)]) if use_env else [(15, 0xfe)]
                voices.append(Voice(a, b, env))
            elif k == 0x80 or k == 0x90:
                for v in voices:
                    if v.note == a and not v.dead and not v.rel:
                        if hold: v.sus = True
                        else: v.rel = True
            elif k == 0xb0:
                if a == 7: chvol = b
                elif a == 0x40:
                    hold = b
                    if not b:
                        for v in voices:
                            if v.sus: v.sus = False; v.rel = True
                elif a == 0x7b:
                    for v in voices: v.dead = True
            elif k == 0xc0: prog = a
            elif k == 0xe0: bend = ((b & 0x7f) << 7) | (a & 0x7f)
        s0, s1 = int(tick * spt), int((tick + 1) * spt)
        n = s1 - s0
        for v in voices:
            if v.dead: continue
            v.tick()
            if v.dead: continue
            lv = level(chvol, v.vel, v.vol)
            amp = ym_amp(lv)
            if amp == 0: continue
            f = 125000.0 / note_period(v.note, bend)
            ph = v.phase + np.arange(n) * (f / rate)
            out[s0:s1] += np.where((ph % 1.0) < 0.5, amp, -amp)
            v.phase = (v.phase + n * f / rate) % 1.0
        voices = [v for v in voices if not v.dead]
    return out, notes

def write_wav(path, x, rate):
    peak = np.max(np.abs(x)) if len(x) else 0
    if peak > 1.0: x = x / peak
    pcm = (x * 32767 * 0.9).astype('<i2')
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + pcm.nbytes) + b'WAVE')
        f.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b'data' + struct.pack('<I', pcm.nbytes)); f.write(pcm.tobytes())

def main():
    args = [a for a in sys.argv[1:]]
    def opt(name, default):
        if name in args:
            i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
        return default
    prefix, start, rate = opt('--prefix', None), int(opt('--start', '1')), int(opt('--rate', '44100'))
    index_file = opt('--index', None)
    patch = None
    if len(args) == 3: snd, patch, outdir = args
    elif len(args) == 2: snd, outdir = args
    else: sys.exit(__doc__)
    prefix = prefix or os.path.basename(snd)
    d = open(snd, 'rb').read()
    if d[:2] == b'\x84\x00': d = d[2:]                   # an N.snd patch file (makesnd.py)
    envelopes = load_patch(patch)
    os.makedirs(outdir, exist_ok=True)
    n = start; index = []; seen = {}
    for t, chans in parse_header(d):
        parsed = []
        for ch, poly, prio, data in chans:
            if ch >= 15: continue                       # control channel: tempo/cues only
            ev = parse_events(data)
            if not any((e[1] & 0xf0) == 0x90 and e[3] for e in ev): continue
            parsed.append((ch, poly, prio, ev))
        if not parsed: continue
        end = max(e[0] for _, _, _, ev in parsed for e in ev)
        mix = None; dev = DEVICES.get(t, '?'); keys = []
        index.append('track $%02x (%s): %d channels, %.1f s' % (t, dev, len(parsed), end / TICK))
        for ch, poly, prio, ev in parsed:
            key = (t == 0x13, tuple(ev)); keys.append(key)
            progs = sorted({e[2] for e in ev if (e[1] & 0xf0) == 0xc0})
            lo = min(e[2] for e in ev if (e[1] & 0xf0) == 0x90 and e[3]); hi = max(e[2] for e in ev if (e[1] & 0xf0) == 0x90 and e[3])
            notes = sum(1 for e in ev if (e[1] & 0xf0) == 0x90 and e[3])
            info = 'channel %2d  poly %d  %3d notes  range %3d-%3d  program %s%s' % (
                ch, poly, notes, lo, hi, ','.join(map(str, progs)) or '-', '  (percussion channel)' if ch == 9 else '')
            if key in seen:
                index.append('    %-26s same as %02d' % (info, seen[key])); continue
            x, _ = render_channel(ev, envelopes, rate, t == 0x13, end)
            name = '%s_%02d_t%02x_ch%d.wav' % (prefix, n, t, ch)
            write_wav(os.path.join(outdir, name), x, rate)
            seen[key] = n; seen[('wav', key)] = x
            index.append('%02d  %-24s %s' % (n, name, info)); n += 1
        mkey = ('mix', frozenset(keys))
        if mkey in seen:
            index.append('    mix of all channels: same as %02d' % seen[mkey]); continue
        for key in keys:
            mix = seen[('wav', key)] if mix is None else mix + seen[('wav', key)]
        name = '%s_%02d_t%02x_mix.wav' % (prefix, n, t)
        write_wav(os.path.join(outdir, name), mix, rate)
        seen[mkey] = n
        index.append('%02d  %-24s all %d channels mixed' % (n, name, len(parsed))); n += 1
    with open(index_file or os.path.join(outdir, prefix + '_index.txt'), 'a') as f:
        f.write('%s: square-wave renderings per channel (60 Hz ticks, volume/pitch as st/src/ym.c);\n' % snd)
        f.write('patch 101 envelopes applied to track $13 only, other tracks use a flat envelope.\n\n')
        f.write('\n'.join(index) + '\n\n')
    print('\n'.join(index))

if __name__ == '__main__':
    main()
