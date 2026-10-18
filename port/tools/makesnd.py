#!/usr/bin/env python3
"""Write patched KQ5 sound resources as SCI patch files (N.snd) into OUTDIR:  makesnd.py st/hd

SOUNDS: sound number -> dict with
  'keep':  {device track type: MIDI channels to keep (in order)}. The other channels of that
           track are dropped from the track header (their data stays in the file; only the
           header shrinks and the data offsets move). The control channel (15) is always kept.
  'drop':  [device track types] - remove these tracks from the header entirely, so the sound has
           no track for the YM driver and stays silent on the ST (like the sounds that never had a
           $13 track); the other devices' tracks are untouched.
  'edits': [(track type, channel, edit, argument), ...] - changes to one channel's event data.
           The edited channel is copied to the end of the resource and the track's header entry
           points at the copy, so other tracks that share the original data are untouched.
           Edits:
             'program', {OLD: NEW, ...}: rewrite the channel's program changes (OLD -> NEW, in
               place, same size). Patch 101 instruments: 6 and 8 (and 0-5, 10) are one-tick
               clicks; 17 = 3-tick attack, hold at 15, 5-tick release; 18 = 2-tick attack, hold
               at 13, 5-tick release; 9 = 3 ticks at 15 then a 7-tick decay (percussive, no
               hold); 12 = long decay; 127 = full volume, hold until note-off.
             'hold_last_note', PROGRAM: insert a program change to PROGRAM right before the
               channel's last note-on, so that note plays with that instrument's envelope.
           Several edits on the same channel are applied in order.
Check the result by ear with tools/sndvoices.py (it reads N.snd files too)."""
import os, struct, sys

SOUNDS = {
    # Sierra fanfare: the Amiga $13 (PCjr) track is the 4-voice Amiga arrangement; on the 3 YM
    # voices keep the drum-roll trill (channel 3, 2 voices), the chord hits (4) and the high
    # final notes (1); drop the bass (2) and the sustained chord (5). Chosen by ear 2026-10-17.
    # The $13 track keeps the Amiga arrangement's programs 6 (trill, channel 3) and 8 (chord
    # hits, channel 4), which patch 101 defines as one-tick clicks (no other sound uses them), so
    # every note of those channels was a blip. Each channel first selects a sustained program
    # (3: 17, 4: 18) and then overrides it; the override is undone here (2026-10-17): the trill
    # pulses, the three hits and the final chord (61, ticks 558-778) are held, and channel 3's
    # last note (77, ticks 363-780) is held under them. Alternative for a crisper drum roll:
    # program 9 for the trill plus 'hold_last_note' 17 (see docs/SOUND.md).
    500: {'keep': {0x13: [3, 4, 1]},
          'edits': [(0x13, 3, 'program', {6: 17}),
                    (0x13, 4, 'program', {8: 18})]},
    # Desert ambience (looped with sound 2 by the desert rooms, region script 15, and by room 14
    # at the desert's edge): note 84 (~1 kHz) retriggered every 2 ticks on two interleaved
    # channels, at velocity 14 - a faint insect chirp on the MT-32 and the Amiga sample. On the
    # square-wave $13 (PCjr) track it is a fast high chatter; the user wanted it gone
    # (2026-10-17), so the $13 track is dropped. Sound 2 (the desert wind) never had a $13 track.
    3: {'drop': [0x13]},
}

def parse_tracks(d):
    """-> (tracks, header end): tracks = [(type, [6-byte channel entries])]"""
    tracks, p = [], 0
    while d[p] != 0xff:
        t, chans = d[p], []; p += 1
        while d[p] != 0xff: chans.append(d[p:p + 6]); p += 6
        p += 1; tracks.append((t, chans))
    return tracks, p + 1

def entry_off_size(c): return struct.unpack_from('<HH', c, 2)

def entry_channel(d, c): return d[entry_off_size(c)[0]] & 15

def scan_events(data):
    """Byte-level event list of a channel's data (after its 2 header bytes):
    (start, delta end, end, tick, status, data bytes). Stops after $fc."""
    ev, p, t, status = [], 0, 0, 0
    while p < len(data):
        start = p; delta = 0
        while p < len(data) and data[p] == 0xf8: delta += 240; p += 1
        if p >= len(data): break
        delta += data[p]; p += 1; t += delta
        dend = p
        if p >= len(data): break
        if data[p] & 0x80: status = data[p]; p += 1
        if status == 0xfc: ev.append((start, dend, p, t, status, b'')); break
        if status == 0xf0:
            q = p
            while q < len(data) and data[q] != 0xf7: q += 1
            ev.append((start, dend, q + 1, t, status, data[p:q + 1])); p = q + 1; continue
        n = 1 if (status & 0xf0) in (0xc0, 0xd0) else 2
        ev.append((start, dend, p + n, t, status, data[p:p + n])); p += n
    return ev

def hold_last_note(data, program):
    ev = scan_events(data)
    ons = [e for e in ev if (e[4] & 0xf0) == 0x90 and e[5][1]]
    assert ons, 'no note-on in channel'
    start, dend, end, tick, status, nd = ons[-1]
    ch = status & 15
    # <delta> Cn program  00 9n note vel  (explicit note status restores the running status)
    return (data[:start] + data[start:dend] + bytes([0xc0 | ch, program])
            + b'\x00' + bytes([0x90 | ch]) + nd + data[end:])

def remap_programs(data, mapping):
    data = bytearray(data); hits = 0
    for start, dend, end, tick, status, nd in scan_events(data):
        if (status & 0xf0) == 0xc0 and nd[0] in mapping: data[end - 1] = mapping[nd[0]]; hits += 1
    assert hits, 'no program change %s in channel' % sorted(mapping)
    return bytes(data)

EDITS = {'hold_last_note': hold_last_note, 'program': remap_programs}

def apply_edits(d, tracks, edits):
    """-> (bytes to append after the resource, {(track, channel): (offset, size)} in d's offsets)"""
    extra, moved, pending = bytearray(), {}, {}
    for t, ch, kind, arg in edits:                    # several edits on one channel chain up
        if (t, ch) not in pending:
            entry = next(c for c in dict(tracks)[t] if entry_channel(d, c) == ch)
            off, sz = entry_off_size(entry)
            pending[(t, ch)] = [d[off:off + 2], d[off + 2:off + sz]]
        pending[(t, ch)][1] = EDITS[kind](pending[(t, ch)][1], arg)
    for key, (hdr2, data) in pending.items():
        moved[key] = (len(d) + len(extra), 2 + len(data))
        extra += hdr2 + data
    return bytes(extra), moved

def rebuild(d, spec):
    keep, edits = spec.get('keep', {}), spec.get('edits', [])
    tracks, hdr_end = parse_tracks(d)
    assert all(t in dict(tracks) for t in spec.get('drop', [])), 'track to drop not in sound'
    extra, moved = apply_edits(d, tracks, edits)
    out_tracks = []
    for t, chans in tracks:
        if t in spec.get('drop', []): continue
        if t in keep:
            want = keep[t]
            chans = [c for c in chans if d[entry_off_size(c)[0]] >= 15 or entry_channel(d, c) in want]
            found = {entry_channel(d, c) for c in chans}
            missing = set(want) - found
            assert not missing, 'channels %s not in track $%02x' % (sorted(missing), t)
        out_tracks.append((t, chans))
    new_hdr = sum(1 + 6 * len(c) + 1 for _, c in out_tracks) + 1
    shift = new_hdr - hdr_end
    h = bytearray()
    for t, chans in out_tracks:
        h.append(t)
        for c in chans:
            off, sz = entry_off_size(c)
            if (t, entry_channel(d, c)) in moved: off, sz = moved[(t, entry_channel(d, c))]
            h += c[:2] + struct.pack('<HH', off + shift, sz)
        h.append(0xff)
    h.append(0xff)
    assert len(h) == new_hdr
    return bytes(h) + d[hdr_end:] + extra

def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else 'st/hd'
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'extracted', 'res_amiga', 'sound')
    for n, spec in SOUNDS.items():
        d = open(os.path.join(src, str(n)), 'rb').read()
        out = rebuild(d, spec)
        path = os.path.join(outdir, '%d.snd' % n)
        open(path, 'wb').write(b'\x84\x00' + out)      # SCI patch header: resource type $84 = sound
        print('wrote', path, len(out), 'bytes (was %d)' % len(d))

if __name__ == '__main__':
    main()
