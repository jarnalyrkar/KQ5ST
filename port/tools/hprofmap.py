#!/usr/bin/env python3
"""hprofmap.py RUNLOG SYMFILE [PREFIX]: per-instruction cycle shares from Hatari's "profile cycles N" output
(run with --parse, WORKFLOW.md "Profiling"), named H<hunk>_<offset> or shim:<symbol>+<offset>. Use the
KQ5ST.sym of the build that ran. Sum with LC_ALL=C awk (decimal commas otherwise)."""
import re, sys, bisect
txt=open(sys.argv[1]).read(); symf=sys.argv[2]; want=sys.argv[3] if len(sys.argv)>3 else None
h0=int(re.search(r'Prog at \$([0-9a-f]+)',txt).group(1),16)
syms=sorted((int(l.split()[0],16),l.split()[2]) for l in open(symf) if len(l.split())==3)
load=h0-dict((n,a) for a,n in syms)['hunk0']
hunks=sorted((a+load,int(n[4:])) for a,n in syms if re.fullmatch(r'hunk\d+',n))
H=[a for a,_ in hunks]; S=[a+load for a,_ in syms]
tot=sum(int(m.group(2)) for m in re.finditer(r'^0x([0-9a-f]+)\t\s*[\d.]+%\t(\d+)',txt,re.M))
rows=[]
for m in re.finditer(r'^0x([0-9a-f]+)\t\s*([\d.]+)%\t(\d+)\t\S+ ([^\n]*?)\s{2,}',txt,re.M):
    a=int(m.group(1),16); i=bisect.bisect_right(H,a)-1
    if a < dict((n,x) for x,n in syms)['prog_end']+load and i>=0: name='H%d_%x'%(hunks[i][1],a-hunks[i][0])
    else: j=bisect.bisect_right(S,a)-1; name='shim:'+syms[j][1]+'+%x'%(a-S[j])
    rows.append((int(m.group(3)),name,m.group(4)))
rows.sort(reverse=True)
for c,n,ins in rows:
    if want and not n.startswith(want): continue
    print('%5.2f%% %-14s %s'%(100*c/tot,n,ins[:60]))
