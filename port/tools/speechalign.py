#!/usr/bin/env python3
"""Cut the CD's per-scene cartoon recordings into one clip per Amiga text box (SOUND.md "The intro
cartoon"). Three steps, each writing into WORK:

  speechalign.py extract CDDIR WORK        clips of SCENES -> WORK/N.wav (11025 Hz) + N.f32 (16 kHz)
  VENV/bin/python -I speechalign.py transcribe WORK
                                           whisper word timestamps -> WORK/N.json (needs
                                           faster-whisper in a venv; model small.en, ~500 MB)
  speechalign.py align WORK TEXTDIR        -> table for makespeech.py INTRO_CUTS (stdout), WORK/cuts.json
  VENV/bin/python -I speechalign.py verify WORK TEXTDIR
                                           re-transcribes every cut alone, '!!' = little overlap

TEXTDIR = extracted/res_amiga/text. A line's cut runs from its first matched word to its last
(leading "Oh"/"Well" the CD adds and closely following unmatched words, e.g. "Mordak", go with
the line), padded and split at the middle of a pause;
lines with no matched words fill the gap between their neighbours. OVERRIDE holds the ends set
by hand from the loudness where whisper's word times were off."""
import sys, os, re, json, struct, wave, difflib

# CD clip -> [(text module, index)] in spoken order (the order differs from the text resources)
SCENES = {10103: [(102, 0), (102, 1), (102, 2)], 10104: [(103, 0), (103, 1)],
          10105: [(104, 0), (104, 1)], 10106: [(105, 0)], 10107: [(103, 2), (103, 3)],
          10108: [(114, i) for i in range(14)], 10109: [(100, 1), (100, 2)],
          10111: [(107, 1), (107, 0)], 10112: [(108, i) for i in range(6)],
          10113: [(109, i) for i in range(10)] + [(109, 23), (109, 24)] + [(109, i) for i in range(10, 23)]}
# (module, index) -> (start, end) seconds, None = keep the computed one
OVERRIDE = {(107, 1): (39.35, None),    # whisper stretched "There" over the music before it
            (114, 2): (24.3, 28.0),     # Cedric's "Whoa" and his crash (no words recognised)
            (100, 2): (None, 15.0),     # "Follow meeeee" fades out over 3 s
            (109, 24): (None, 113.9)}   # "That's all used up" ends after the matched words
LEAD = ('oh', 'well', 'o', 'ah', 'not')   # words the CD puts in front of a line (normalised)

def norm(s):
    w = re.sub(r"[^a-z0-9' ]", ' ', s.lower().replace('...', ' ').replace('-', ' ')).split()
    return [re.sub(r'(.)\1+', r'\1', x) for x in w]        # "Hmmmm" = "Hmm", "meeeee" = "me"

def text(textdir, m):
    return [s.decode('latin1') for s in open(os.path.join(textdir, str(m)), 'rb').read().split(b'\0')]

def extract(cd, work):
    import numpy as np, subprocess
    name = lambda n: next(os.path.join(cd, x) for x in (n, n.lower()) if os.path.exists(os.path.join(cd, x)))
    d = open(name('AUDIO001.MAP'), 'rb').read()
    amap = {}
    for i in range(0, len(d) - 9, 10):
        n, vo, sz = struct.unpack('<HII', d[i:i + 10]); amap.setdefault(n, (vo >> 28, vo & 0xfffffff, sz))
    os.makedirs(work, exist_ok=True)
    for n in SCENES:
        v, o, s = amap[n]
        with open(name('AUDIO001.%03d' % v), 'rb') as f: f.seek(o); raw = f.read(s)
        w = wave.open(os.path.join(work, '%d.wav' % n), 'wb')
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(11025); w.writeframes(raw); w.close()
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', os.path.join(work, '%d.wav' % n),
                        '-ar', '16000', '-ac', '1', '-f', 'f32le', os.path.join(work, '%d.f32' % n)], check=True)
        print(n, '%.1f s' % (s / 11025))

def model(work):
    from faster_whisper import WhisperModel
    return WhisperModel('small.en', device='cpu', compute_type='int8',
                        download_root=os.path.join(work, 'models'))

def transcribe(work):
    import numpy as np
    m = model(work)
    for n in SCENES:
        segs, _ = m.transcribe(np.fromfile(os.path.join(work, '%d.f32' % n), np.float32),
                               word_timestamps=True, language='en', beam_size=5)
        words = [(round(w.start, 2), round(w.end, 2), w.word) for s in segs for w in s.words]
        json.dump(words, open(os.path.join(work, '%d.json' % n), 'w'))
        print(n, ' '.join(w[2] for w in words), flush=True)

def align(work, textdir):
    out = []
    for clip, lines in SCENES.items():
        words = json.load(open(os.path.join(work, '%d.json' % clip)))
        tw = [(norm(w) or [''])[0] for _, _, w in words]
        lt, owner = [], []
        for k, (m, i) in enumerate(lines):
            for w in norm(text(textdir, m)[i]): lt.append(w); owner.append(k)
        span = [[None, None] for _ in lines]
        for a, b, n in difflib.SequenceMatcher(None, lt, tw, autojunk=False).get_matching_blocks():
            for j in range(n):
                k = owner[a + j]
                if span[k][0] is None: span[k][0] = b + j
                span[k][1] = b + j
        for k, (f, l) in enumerate(span):
            if f is None: continue
            lo = span[k - 1][1] + 1 if k and span[k - 1][1] is not None else 0
            while f > lo and tw[f - 1] in LEAD: f -= 1
            span[k][0] = f
        # trailing words whisper spelled differently ("Mordak") go with the line too, while they
        # follow closely and come before the next line's first word (not when the next line had
        # no words recognised: then they are probably that line, e.g. 108 5, 114 2)
        for k, (f, l) in enumerate(span):
            if f is None or (k + 1 < len(span) and span[k + 1][0] is None): continue   # not into an unrecognised line
            hi = span[k + 1][0] if k + 1 < len(span) else len(words)
            while l + 1 < hi and words[l + 1][0] - words[l][1] < 0.6: l += 1
            span[k][1] = l
        times = [None if f is None else [words[f][0], words[l][1]] for f, l in span]
        for k, t in enumerate(times):
            if t is None:
                prev = times[k - 1][1] if k and times[k - 1] else 0.0
                times[k] = [prev, next((x[0] for x in times[k + 1:] if x), words[-1][1])]
        clip_end = os.path.getsize(os.path.join(work, '%d.wav' % clip)) / 11025
        # lines that run into each other: whisper often lets the last word end where the next one
        # starts, though the real gap comes 0.1-0.3 s later; cut at the quietest 50 ms after the
        # last word (114 5, 108 4, 109 18, 2026-11-19)
        import numpy as np
        x = np.fromfile(os.path.join(work, '%d.f32' % clip), np.float32)
        rms = lambda t: float(np.sqrt(np.mean(x[int(t * 16000):int((t + 0.05) * 16000)] ** 2)))
        cut = {}
        for k in range(len(times) - 1):
            e, ns = times[k][1], times[k + 1][0]
            if ns - e < 0.6:
                # only search into the next line when whisper's words touch; with a real gap the
                # cut stays in it (loud music under 109 4/5 put the minimum inside "I used to")
                cand = np.arange(e - 0.05, e + 0.4, 0.01) if ns - e < 0.03 else np.arange(e, ns - 0.05, 0.01)
                cut[k] = round(float(min(cand, key=rms)) + 0.025, 2)
        for k, ((m, i), (s, e)) in enumerate(zip(lines, times)):
            last = k + 1 == len(times)
            cs = max((times[k - 1][1] + s) / 2, s - 0.3) if k else max(0.0, s - 0.3)
            ce = min(clip_end, e + 0.6) if last else min((e + times[k + 1][0]) / 2, e + 0.45)
            if k - 1 in cut: cs = cut[k - 1]
            if k in cut: ce = cut[k]
            o = OVERRIDE.get((m, i), (None, None))
            out.append((m, i, clip, round(o[0] if o[0] is not None else cs, 2), round(o[1] or ce, 2)))
    json.dump(out, open(os.path.join(work, 'cuts.json'), 'w'))
    clip = None
    for m, i, c, a, b in out:
        if c != clip: print('    # clip %d' % c); clip = c
        print('    (%d, %d, %d, %.2f, %.2f),' % (m, i, c, a, b))

def verify(work, textdir):
    import numpy as np
    mdl, audio = model(work), {}
    for m, i, clip, a, b in json.load(open(os.path.join(work, 'cuts.json'))):
        if clip not in audio: audio[clip] = np.fromfile(os.path.join(work, '%d.f32' % clip), np.float32)
        pad = np.zeros(8000, np.float32)
        x = np.concatenate([pad, audio[clip][int(a * 16000):int(b * 16000)], pad])
        got = ' '.join(s.text for s in mdl.transcribe(x, language='en', beam_size=5)[0]).strip()
        want = text(textdir, m)[i]
        r = difflib.SequenceMatcher(None, norm(want), norm(got)).ratio()
        print('%s %3d %2d %5.1fs %.2f | %s || %s' % ('  ' if r > .8 else '!!', m, i, b - a, r, want, got), flush=True)

if __name__ == '__main__':
    cmd, args = sys.argv[1], sys.argv[2:]
    {'extract': extract, 'transcribe': transcribe, 'align': align, 'verify': verify}[cmd](*args)
