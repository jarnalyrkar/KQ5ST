# For every call target in hunk 62 (Aztec C OS glue), follow the code until the library call.
# Prints: target, library, LVO, name, number of call sites.  wrappers.py DISASMDIR
import re, sys, glob, os
from collections import Counter
LIBS = {'-$4e9a(a4)': 'exec', '$4.w': 'exec', '-$4e96(a4)': 'dos', '-$4ebe(a4)': 'intuition', '-$68b6(a4)': 'graphics',
        '-$4e78(a4)': 'lib4e78', '-$68ba(a4)': 'exec', '-$67c0(a4)': 'exec'}
NAMES = {
 'exec': {30:'Supervisor',108:'Alert',120:'Disable',126:'Enable',132:'Forbid',138:'Permit',162:'SetIntVector',168:'AddIntServer',
          174:'RemIntServer',198:'AllocMem',210:'FreeMem',216:'AvailMem',282:'AddTask',288:'RemTask',294:'FindTask',
          300:'SetTaskPri',306:'SetSignal',318:'Wait',324:'Signal',330:'AllocSignal',336:'FreeSignal',354:'AddPort',
          360:'RemPort',366:'PutMsg',372:'GetMsg',378:'ReplyMsg',384:'WaitPort',390:'FindPort',408:'OldOpenLibrary',414:'CloseLibrary',
          444:'OpenDevice',450:'CloseDevice',456:'DoIO',462:'SendIO',468:'CheckIO',474:'WaitIO',480:'AbortIO',552:'OpenLibrary'},
 'dos': {30:'Open',36:'Close',42:'Read',48:'Write',54:'Input',60:'Output',66:'Seek',72:'DeleteFile',78:'Rename',84:'Lock',90:'UnLock',
         96:'DupLock',102:'Examine',108:'ExNext',114:'Info',120:'CreateDir',126:'CurrentDir',132:'IoErr',138:'CreateProc',144:'Exit',
         150:'LoadSeg',156:'UnLoadSeg',174:'DeviceProc',192:'DateStamp',198:'Delay',204:'WaitForChar',210:'ParentDir',216:'IsInteractive',222:'Execute'},
 'intuition': {60:'ClearPointer',66:'CloseScreen',72:'CloseWindow',78:'CloseWorkBench',150:'ModifyIDCMP',198:'OpenScreen',204:'OpenWindow',
               210:'OpenWorkBench',270:'SetPointer',282:'ShowTitle',294:'ViewAddress',300:'ViewPortAddress'},
 'graphics': {192:'LoadRGB4',198:'InitRastPort',210:'MrgCop',216:'MakeVPort',222:'LoadView',270:'WaitTOF',390:'InitBitMap',402:'WaitBOVP',
              456:'OwnBlitter',462:'DisownBlitter'}}
D = sys.argv[1]
lines = {}
for f in glob.glob(D + '/hunk*.s'):
    for l in open(f):
        a = l.split(':')[0]; lines[a] = l.rstrip()
order = {}
for f in glob.glob(D + '/hunk*.s'):
    h = [l.split(':')[0] for l in open(f)]
    for i, a in enumerate(h): order[a] = (h, i)
calls = Counter(m.group(1) for l in lines.values() for m in [re.search(r'; -> (H62_[0-9a-f]+)', l)] if m and re.search(r'\bjsr\b', l))
for tgt, n in sorted(calls.items(), key=lambda x: int(x[0][4:], 16)):
    if tgt not in order: continue
    h, i = order[tgt]; base = None; res = None
    for j in range(i, min(i + 16, len(h))):
        l = lines[h[j]]
        mm = re.search(r'movea\.l (.+), a6$', l)
        if mm: base = mm.group(1)
        m = re.search(r'(jsr|jmp) -\$([0-9a-f]+)\(a6\)', l)
        if m:
            lib = LIBS.get(base, base); lvo = int(m.group(2), 16); res = (lib, -lvo, NAMES.get(lib, {}).get(lvo, '?')); break
        if re.search(r'\brts\b|\bjsr\b', l): break
    print(f'{tgt:10} calls {n:3}  ' + ('%-10s %5d %s' % res if res else '(C code)'))
