# Track a6 loads and the library calls that follow them in the disassembly listing.
import re, glob, os, sys
from collections import defaultdict
calls = defaultdict(lambda: defaultdict(set))
for f in sorted(glob.glob(sys.argv[1] + '/hunk*.s')):
    h = os.path.basename(f)[4:6]; base = None
    for line in open(f):
        m = re.search(r'movea\.l (.+), a6$', line)
        if m: base = m.group(1); continue
        m = re.search(r'(jsr|jmp) (-\$[0-9a-f]+)\(a6\)', line)
        if m: calls[base or '?'][m.group(2)].add(h)
        if re.search(r'\b(rts|unlk)\b', line): base = None
for b, cs in calls.items():
    print(f'base {b}:')
    for c, hs in sorted(cs.items(), key=lambda x: int(x[0][2:], 16)):
        print(f'   {c:7} ({-int(c[2:],16)})  hunks {sorted(hs)}')
