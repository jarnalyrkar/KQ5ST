# Aggregate profile data from a run log by function:
#  - shim sampler lines "prof $addr NAME count", or
#  - Hatari debugger "profile cycles N" lines ("0xADDR <tab> pct% <tab> cycles ...") with --hatari
# profsum.py RUNLOG SYMFILE DISASMDIR [--hatari]
import re, sys, bisect, glob, os
from collections import Counter
log, symf, dis = sys.argv[1:4]
txt = open(log).read()
h0 = int(re.search(r'Prog at \$([0-9a-f]+)', txt).group(1), 16)
syms = sorted((int(l.split()[0], 16), l.split()[2]) for l in open(symf) if len(l.split()) == 3)
load = h0 - dict((n, a) for a, n in syms)['hunk0']
saddr = [a + load for a, _ in syms]
# Prog function starts: link instructions or movem saves right after rts
starts = {}
for f in glob.glob(dis + '/hunk*.s'):
    h = int(os.path.basename(f)[4:6]); prev_rts = True; lst = []
    for l in open(f):
        a = int(l.split(':')[0].split('_')[1], 16)
        if 'link.w' in l or prev_rts: lst.append(a)
        prev_rts = bool(re.search(r'\b(rts|jmp)\b', l))
    starts[h] = sorted(lst)
hunks = sorted((a + load, int(n[4:])) for a, n in syms if re.fullmatch(r'hunk\d+', n))
def hname(addr):
    i = bisect.bisect_right([a for a, _ in hunks], addr) - 1
    return f'H{hunks[i][1]}_{addr - hunks[i][0]:x}' if i >= 0 and addr < dict((n, a) for a, n in syms)['prog_end'] + load else None
if '--hatari' in sys.argv:
    entries = [(int(m.group(1), 16), int(m.group(2))) for m in re.finditer(r'^0x([0-9a-f]+)\t\s*[\d.]+%\t(\d+)', txt, re.M)]
    entries = [(a, hname(a) or 'x', n) for a, n in entries]
else:
    entries = [(int(m.group(1), 16), m.group(2), int(m.group(3))) for m in re.finditer(r'prof \$([0-9a-f]+) (\S+) (\d+)', txt)]
tot = Counter(); total = 0
for addr, name, n in entries:
    total += n
    hm = re.match(r'H(\d+)_([0-9a-f]+)', name)
    if hm:
        h, off = int(hm.group(1)), int(hm.group(2), 16)
        s = starts.get(h, [0]); i = bisect.bisect_right(s, off) - 1
        key = f'H{h}_{s[max(i,0)]:x}'
    else:
        i = bisect.bisect_right(saddr, addr) - 1; key = 'shim:' + syms[i][1]
    tot[key] += n
for k, n in tot.most_common(30): print(f'{100*n/total:5.1f}%  {k}')
