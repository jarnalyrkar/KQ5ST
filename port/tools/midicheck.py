#!/usr/bin/env python3
"""midicheck.py CAPTURE: check a raw MIDI capture (hatari --midi-out FILE) from the MT-32 driver:
every SysEx (address, length, checksum, display text), event counts per type/channel, programs."""
import sys
from collections import Counter
d=open(sys.argv[1],'rb').read()
i=0; sx=[]; ev=Counter(); chans=Counter(); status=None; bad=0; progs={}
LEN={0x80:2,0x90:2,0xa0:2,0xb0:2,0xc0:1,0xd0:1,0xe0:2}
while i<len(d):
    b=d[i]
    if b==0xf0:
        j=d.index(0xf7,i); m=d[i+1:j]
        assert m[:4]==bytes([0x41,0x10,0x16,0x12]), m[:4].hex()
        body=m[4:-1]; ok=(sum(body)+m[-1])%128==0
        addr=(body[0]<<16)|(body[1]<<8)|body[2]
        sx.append((hex(addr),len(body)-3,ok, bytes(body[3:23]) if addr==0x200000 else b''))
        bad+= not ok; i=j+1; status=None; continue
    if b&0x80: status=b; i+=1
    n=LEN[status&0xf0]; args=d[i:i+n]; i+=n
    ev[hex(status&0xf0)]+=1; chans[status&15]+=1
    if status&0xf0==0xc0: progs.setdefault(status&15,set()).add(args[0])
print('sysex', len(sx), 'bad checksums', bad)
for s in sx[:3]+sx[-5:]: print(' ', s)
print('events', dict(ev)); print('channels', dict(sorted(chans.items()))); print('programs', {k:sorted(v) for k,v in progs.items()})
