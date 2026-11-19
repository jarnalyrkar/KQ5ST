#!/usr/bin/env python3
"""Find the CD speech clips for a room's text lines (SOUND.md "Speech", room by room).

  VENV/bin/python -I roomclips.py CDDIR WORK TEXTDIR ROOM [TEXTMODULE...]

The CD scripts are the Amiga scripts with each spoken (PrintDC m i) replaced by (Say N) and the
Talker conversations by clip arrays, so the CD's room script names its clips as plain 16-bit
numbers: every little-endian word in CD script ROOM (uncompressed in RESOURCE.00x) that is a
clip in AUDIO001.MAP is a candidate. The candidates are transcribed with whisper (faster-whisper,
`small.en`; cached in WORK/clips.json) and each line of the Amiga text modules (default: ROOM)
is matched to the clip with the most similar words. Prints one line per text line:
  module index clip score | text || transcript
and a LINES snippet for makespeech.py with the matches scoring >= 0.6 (check the rest by hand;
lines spoken by Cedric through the owl region or by narrator-only text have no clip)."""
import sys, os, re, json, struct, difflib, subprocess

def resource_map(cd):
    m = open(os.path.join(cd, 'resource.map'), 'rb').read()
    types, i = [], 0
    while m[i] != 0xff: types.append((m[i], struct.unpack_from('<H', m, i + 1)[0])); i += 3
    types.append((0xff, struct.unpack_from('<H', m, i + 1)[0]))
    res = {}
    for (t, o), (_, o2) in zip(types, types[1:]):
        for j in range(o, o2, 6):
            n, vo = struct.unpack_from('<HI', m, j)
            res[(t, n)] = (vo >> 28, vo & 0xfffffff)
    return res

def cd_script(cd, n):
    vol, off = resource_map(cd)[(0x82, n)]
    d = open(os.path.join(cd, 'resource.%03d' % vol), 'rb').read()
    t, num, packed, unpacked, method = struct.unpack_from('<BHHHH', d, off)
    assert method == 0, 'CD script %d is compressed (method %d)' % (n, method)
    return d[off + 9:off + 9 + unpacked]

def audio_map(cd):
    d = open(os.path.join(cd, 'audio001.map'), 'rb').read(); m = {}
    for i in range(0, len(d) - 9, 10):
        n, vo, sz = struct.unpack_from('<HII', d, i)
        if vo >> 28 == 2: m.setdefault(n, (2, vo & 0xfffffff, sz))   # the audio is all in AUDIO001.002
    return m

norm = lambda s: re.sub(r"[^a-z0-9' ]", ' ', s.lower().replace('...', ' ').replace('-', ' ')).split()

def main():
    cd, work, textdir, room = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    modules = [int(x) for x in sys.argv[5:]] or [room]
    amap = audio_map(cd)
    code = cd_script(cd, room)
    cands = sorted({struct.unpack_from('<H', code, o)[0] for o in range(len(code) - 1)} & set(amap) - set(range(0, 82)))
    os.makedirs(work, exist_ok=True)
    cache_p = os.path.join(work, 'clips.json')   # port/work/speech/ keeps it across sessions
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    todo = [n for n in cands if str(n) not in cache]
    if todo:
        import numpy as np
        from faster_whisper import WhisperModel
        model = WhisperModel('small.en', device='cpu', compute_type='int8', download_root=os.path.join(work, 'models'))
        for n in todo:
            v, o, s = amap[n]
            with open(os.path.join(cd, 'audio001.%03d' % v), 'rb') as f: f.seek(o); raw = f.read(s)
            x = subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'u8', '-ar', '11025', '-ac', '1', '-i', '-',
                                '-ar', '16000', '-f', 'f32le', '-'], input=raw, capture_output=True).stdout
            cache[str(n)] = ' '.join(seg.text for seg in model.transcribe(np.frombuffer(x, np.float32), language='en', beam_size=5)[0]).strip()
            json.dump(cache, open(cache_p, 'w'))
    found = []
    for m in modules:
        for i, line in enumerate(open(os.path.join(textdir, str(m)), 'rb').read().split(b'\0')):
            line = line.decode('latin1')
            if not line.strip(): continue
            best = max(((difflib.SequenceMatcher(None, norm(line), norm(cache[str(n)])).ratio(), n) for n in cands), default=(0, None))
            r, n = best
            print('%4d %2d %5s %.2f | %s || %s' % (m, i, n, r, line[:70], cache.get(str(n), '')[:70]))
            if r >= 0.6: found.append((m, i, n))
    print('\n    ' + ', '.join('(%d, %d, %d)' % f for f in found) + ',')

if __name__ == '__main__':
    main()
