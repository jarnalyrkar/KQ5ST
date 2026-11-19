#!/usr/bin/env python3
"""Write patched KQ5 text resources as SCI patch files (N.TEX) into OUTDIR:  maketext.py st/hd

The CD release reworded some lines it speaks. So that the text box says what the voice says
(user's choice, 2026-11-19), those lines take the CD wording: TEXTS maps text module -> {index:
new text}. The wording comes from whisper transcripts of the CD clips (the CD keeps no text for
spoken lines), proofread against the Amiga line, whose punctuation and spelling are kept where
the words agree. The interpreter (and ScummVM) load N.TEX from the game folder in preference to
the RESOURCE volumes, as the Amiga release's own 756.TEX."""
import os, sys

TEXTS = {
    2: {   # the snake (makespeech.py LINES, room 2)
        0: 'Having entered the warm valley a while back, Graham has since removed his uncomfortably heavy cloak.',   # 177
        1: '"Graham, watch out! A poisonous snake!"',                                                                # 5500
        3: 'A worn dirt path wanders through a thick wood, alive with the sounds of many creatures. Between the trees, to the east, Graham can see the outline of a great mountain range.',   # 172
        6: 'In silence, the large serpent eyes Graham menacingly.',                                                  # 176 (Talk)
        7: "That won't convince the snake to leave.",                                                                # 175 (other items)
    },
}

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'extracted', 'res_amiga', 'text')

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'st/hd'
    for n, lines in TEXTS.items():
        parts = open(os.path.join(SRC, str(n)), 'rb').read().split(b'\0')
        for i, t in lines.items():
            assert i < len(parts) and parts[i], 'text %d has no line %d' % (n, i)
            parts[i] = t.encode('latin1')
        data = b'\0'.join(parts)
        path = os.path.join(out, '%d.TEX' % n)
        open(path, 'wb').write(b'\x83\x00' + data)     # SCI patch header: resource type $83 = text
        print('wrote', path, len(data), 'bytes,', len(lines), 'line(s) changed')

if __name__ == '__main__':
    main()
