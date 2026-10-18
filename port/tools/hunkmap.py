# Per-hunk profile of Prog: kernel functions, OS libraries, hardware access, referenced strings.
import json, struct, re, glob, os
from collections import defaultdict
W = 'work/prog'
H = json.load(open(f'{W}/hunks.json')); d1 = open(f'{W}/hunk01.bin', 'rb').read()
rel1 = {o: int(t) for t, offs in H[1]['relocs'].items() for o in offs}
kn = [x.decode() for x in open('extracted/res_amiga/vocab/999', 'rb').read().split(b'\0')[:-1]]
LIBS = {'-$4e9a(a4)': 'exec', '$4.w': 'exec', '-$68ba(a4)': 'exec', '-$67c0(a4)': 'exec', '-$4e96(a4)': 'dos',
        '-$4ebe(a4)': 'intuition', '-$68b6(a4)': 'graphics', '-$4e78(a4)': 'lib@-4e78', '(a0)': 'exec?'}
info = defaultdict(lambda: {'kernel': [], 'libs': set(), 'hw': set(), 'strings': [], 'entries': 0})
for i in range(124):
    o = 0x7e8 + 4 * i; v = struct.unpack('>I', d1[o:o+4])[0]
    info[rel1[o]]['kernel'].append(kn[i] if i < len(kn) else f'k{i}')
for i in range(192):
    o = 2 + 6 * i
    if o in rel1: info[rel1[o]]['entries'] += 1
def cstr(b, o):
    e = b.find(b'\0', o); s = b[o:e]
    return s.decode('latin1') if 3 <= len(s) < 60 and all(32 <= c < 127 or c in (9, 10) for c in s) else None
for f in sorted(glob.glob(f'{W}/disasm/hunk*.s')):
    h = int(os.path.basename(f)[4:6]); b = open(f'{W}/hunk{h:02d}.bin', 'rb').read(); base = None
    for line in open(f):
        m = re.search(r'movea\.l (.+), a6$', line)
        if m: base = m.group(1)
        if re.search(r'(jsr|jmp) -\$[0-9a-f]+\(a6\)', line): info[h]['libs'].add(LIBS.get(base, base))
        if re.search(r'\$df[0-9a-f]{4}\b', line): info[h]['hw'].add('custom')
        if re.search(r'\$bf[de][0-9a-f]{3}\b', line): info[h]['hw'].add('CIA')
        m = re.match(r'H\d+_([0-9a-f]+): \S+ +(pea\.l|lea\.l) \$?(-?[0-9a-f]+)\(pc\)', line)
        if m:
            tgt = int(m.group(1), 16) + 2 + int(m.group(3), 16)
            s = cstr(b, tgt) if 0 <= tgt < len(b) else None
            if s and s not in info[h]['strings']: info[h]['strings'].append(s)
    # strings referenced in data hunk via a4 are resolved later; keep it simple here
rows = []
for h, x in enumerate(H):
    if x['type'] != 'CODE': continue
    i = info[h]
    rows.append(f"| {h} | {x['size']} | {i['entries']} | {', '.join(i['kernel'][:12]) + (' …' if len(i['kernel']) > 12 else '')} | "
                f"{', '.join(sorted(i['libs']))} | {', '.join(sorted(i['hw']))} | {'; '.join(repr(s) for s in i['strings'][:4])} |")

print('\n'.join(rows))
