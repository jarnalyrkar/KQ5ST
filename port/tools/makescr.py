#!/usr/bin/env python3
"""Write patched KQ5 scripts as SCI patch files (N.SCR) into OUTDIR:  makescr.py st/hd
Two kinds of patches against the unpacked scripts in extracted/res_amiga/script:
  PATCHES: script number, byte offset, expected old bytes, new bytes (same length);
  METHODS: script number, class offset, selector, builder - the method's code is rebuilt by the
    builder (gets the original method bytes, returns the new ones), stored in a new code block
    appended to the script, and the class's method table is pointed at it. The new code must only
    use relative branches (no `call` to local procedures, no lofsa into itself).
  HOOKS: script number, code offset, byte count, builder - the n bytes at the offset (whole
    instructions, no relative branch in or into them) are replaced by a jmp to a trampoline in a
    new code block appended to the script; the builder gets the replaced bytes and returns the
    trampoline code, which normally ends with those bytes (the trampoline then jumps back to the
    instruction after the hook). The original method stays in place, so its lofsa/call operands
    are untouched.
The interpreter loads N.SCR from the game folder in preference to the RESOURCE volumes
(the Amiga release itself ships 756.SCR that way). Disassemble with tools/scidisasm.py."""
import sys, os, struct
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'extracted', 'res_amiga', 'script')

# ---- SCI bytecode helpers (word forms where an operand is a word, byte forms otherwise) ---------
def jmp(off):  return b'\x32' + struct.pack('<h', off)
def bnt(off):  return b'\x30' + struct.pack('<h', off)
def ldi(v):    return b'\x34' + struct.pack('<H', v & 0xffff)
def pushi(v):  return b'\x38' + struct.pack('<H', v)
PUSH0, PUSH, AND = b'\x76', b'\x36', b'\x12'
def lap(n):    return b'\x87' + bytes([n])
def send(n):   return b'\x4a' + bytes([n])
def self_(n):  return b'\x54' + bytes([n])
def pToa(n):   return b'\x63' + bytes([n])
def sat(n):    return b'\xa5' + bytes([n])
def dec_at(n): return b'\xe5' + bytes([n])      # -at: temp[n] -= 1, acc = temp[n]
def link(n):   return b'\x3f' + bytes([n])
def lag(n):    return b'\x80' + struct.pack('<H', n)   # load acc global (word form)
def lsg(n):    return b'\x88' + struct.pack('<H', n)   # push global
def lat(n):    return b'\x85' + bytes([n])
PUSH1, EQ, LT, RET = b'\x78', b'\x1a', b'\x22', b'\x48'
SEL_modifiers, SEL_doit, SEL_prevDir = 64, 60, 314
SEL_type, SEL_message, SEL_claimed, SEL_script, SEL_state, SEL_cue, SEL_stop = 34, 40, 76, 135, 32, 138, 153
SEL_eachElementDo, SEL_dispose = 115, 107
G_curRoom, G_cast, G_roomNumber, G_titleMusic = 2, 5, 11, 397
ROOM_TITLE = 119
PROP_mover = 100
def user_handle_event_hook(replaced):
    """Trampoline hooked into the start of User::handleEvent (script 996): Esc (or both mouse
    buttons, which the ST shim turns into Esc) in the title room 119 skips the Sierra fanfare
    (animScript states 0-7 -> state 8, the KQ5 title and its song) or the title song (states
    8-10 -> state 12, the "Have you played King's Quest V before?" box). The room's script is
    moved to the state before the target and cued; the title music is stopped (state 8 starts the
    song itself) and the cast (the logo twinkle / title glint Props) disposed so that no cycler
    cues the script late. The hook runs before anything else can claim the key (the icon bar
    opens on Esc). Code: (if (and (== global11 119) (== (event type) keyDown) (== (event message)
    27) (= theScript (curRoom script)) (< (theScript state) 11)) ...)."""
    assert replaced[:2] == b'\x3f\x02', replaced.hex()         # link 2 (the method's own temps)
    t = bytearray(replaced[:2]); fix = []
    def br(op, label): fix.append((len(t) + 1, label)); t.extend(op(0))
    def mark(n):                            # debug probe `(Abs n)` in the kernel trace (MARKERS=1)
        if os.environ.get('MARKERS'): t.extend(PUSH1 + pushi(n) + b'\x43\x3d\x02')
    mark(1)
    t += lsg(G_roomNumber) + ldi(ROOM_TITLE) + EQ;                       br(bnt, 'orig')
    mark(2)
    t += pushi(SEL_type) + PUSH0 + lap(1) + send(4) + PUSH + ldi(4) + EQ;   br(bnt, 'orig')
    mark(3)
    t += pushi(SEL_message) + PUSH0 + lap(1) + send(4) + PUSH + ldi(27) + EQ; br(bnt, 'orig')
    mark(4)
    t += pushi(SEL_script) + PUSH0 + lag(G_curRoom) + send(4) + sat(0);  br(bnt, 'orig')
    mark(5)
    t += pushi(SEL_state) + PUSH0 + lat(0) + send(4) + PUSH + ldi(8) + LT;  br(bnt, 'song')
    mark(6)
    t += pushi(SEL_state) + PUSH1 + pushi(7) + lat(0) + send(6);          br(jmp, 'cue')
    labels = {'song': len(t)}
    mark(7)
    t += pushi(SEL_state) + PUSH0 + lat(0) + send(4) + PUSH + ldi(11) + LT; br(bnt, 'orig')
    mark(8)
    t += pushi(SEL_state) + PUSH1 + pushi(11) + lat(0) + send(6)
    labels['cue'] = len(t)
    t += pushi(SEL_stop) + PUSH0 + lag(G_titleMusic) + send(4)
    t += pushi(SEL_eachElementDo) + PUSH1 + pushi(SEL_dispose) + lag(G_cast) + send(6)
    t += pushi(SEL_cue) + PUSH0 + lat(0) + send(4)
    t += pushi(SEL_claimed) + PUSH1 + PUSH1 + lap(1) + send(6)
    t += ldi(1) + RET
    labels['orig'] = len(t)
    t += replaced[2:]                      # the rest of the replaced instructions, then back
    for pos, label in fix: t[pos:pos + 2] = struct.pack('<h', labels[label] - (pos + 2))
    return bytes(t)

def with_markers(orig, sites):
    """Debug probes for a METHODS builder (not used by the shipped patches): at each
    (offset, marker, n[, kind]) replace n bytes (whole instructions, no relative branches, no
    branch target inside) with a jmp to a trampoline that calls `(Abs marker)` - visible in the
    shim's kernel trace (KTRACE file in the game folder) as `$3d(marker)` - then runs the replaced
    bytes and jumps back. kind 'val' logs `GetAngle(marker, acc)` with the acc the replaced bytes
    produce (e.g. a property read)."""
    code = bytearray(orig)
    for site in sites:
        off, marker, n = site[:3]; kind = site[3] if len(site) > 3 else 'abs'
        assert n >= 3
        replaced = bytes(orig[off:off + n])
        tramp = len(code)
        code[off:off + n] = jmp(tramp - (off + 3)) + b'\0' * (n - 3)
        if kind == 'abs':
            t = b'\x78' + pushi(marker) + b'\x43\x3d\x02' + replaced
        else:   # 'val': `(GetAngle marker acc)` where acc is the result of the replaced bytes, then redo them
            t = b'\x7a' + pushi(marker) + replaced + PUSH + b'\x43\x3f\x04' + replaced
        t += jmp((off + n) - (tramp + len(t) + 3))
        code += t
    return bytes(code)

PATCHES = [
    # Default game speed: KQ5::init sets (self egoMoveSpeed: 2) - the Speed slider of the
    # settings panel (0 = top/fastest .. 15 = bottom) copies this into ego's moveSpeed and
    # cycleSpeed, so Graham only stepped every third game cycle. Make the default the slider's
    # top position (100 %): push2 -> push0.
    (0, 0x8e4, b'\x7a', b'\x76'),
    # Keypad with the walk cursor walks Graham (as in the DOS game / the manual). KQ5 Amiga's
    # kQPMouse::handleEvent (script 0, a PseudoMouse) saves the current icon's verb, forces it to 0,
    # calls PseudoMouse::handleEvent (script 933) and restores the verb - so the stock walk-cursor
    # exception in PseudoMouse (verb 1 -> return 0, i.e. not claimed, and User::handleEvent passes
    # the direction on to Ego::handleEvent -> setDirection, same key again = stop) never applied
    # and the keypad only moved the pointer. The DOS version has no kQPMouse at all. Replace the
    # method body with a plain `(super handleEvent: event)`: pushi handleEvent; push1; lsp 1;
    # super PseudoMouse 6; ret.
    (0, 0x1a58, b'\x3f\x01\x39\x28\x76\x38\xcb\x00\x76\x81', b'\x38\x80\x00\x78\x8f\x01\x57\x6a\x06\x48'),
    # Copy protection off (as in the CD release). Four rooms call `(CPCheck doit: prompt)` (script
    # 754: "Use Crispin's wand to ..." + a word written in the manual's symbol alphabet, 3 tries,
    # failure = death or a lost item); each call sits behind a `bnt` to the normal continuation
    # (flag/global-100/Random tests). Turn that last `bnt` into a `jmp` (opcode $30 -> $32), so the
    # check block is never entered - exactly the path the game takes when Random(1,4) != 1.
    (22, 0x46b, b'\x30\x43\x00', b'\x32\x43\x00'),    # getSmall::changeState - witch's house door
    (30, 0xf92, b'\x30\x64\x00', b'\x32\x64\x00'),    # rock::handleEvent - throwing the rope
    (216, 0x403, b'\x30\x30\x00', b'\x32\x30\x00'),   # rm216::doit - bandit in the small tent
    (220, 0x9fb, b'\x30\x42\x00', b'\x32\x42\x00'),   # leave::changeState - rowing the boat
    # Bakery customers walk out at the speed of the PC game: doWinners::changeState states 18/19
    # set `cycleSpeed: 4 moveSpeed: 4` (a step every fifth cycle, ~25 s at 8 cycles/s before the
    # baker speaks). pushi 4 -> pushi 0 for both values.
    (206, 0x5a7, b'\x39\x04\x39\x38\x78\x39\x04', b'\x39\x00\x39\x38\x78\x39\x00'),  # boy
    (206, 0x5e5, b'\x39\x04\x39\x38\x78\x39\x04', b'\x39\x00\x39\x38\x78\x39\x00'),  # woman
    # Cedric lands faster when Graham enters a room: stdWalkIn::changeState state 0 (script 202,
    # the owl region) plays his 9-14 cel landing loop with `cycleSpeed: 3` under HandsOff, ~5-7 s
    # at 8 cycles/s before Graham can move. pushi 3 -> pushi 0 (the idle head-turn in `rotate`
    # keeps its speed 3).
    (202, 0x4f6, b'\x38\xd8\x00\x78\x39\x03\x38\x93\x00', b'\x38\xd8\x00\x78\x39\x00\x38\x93\x00'),
]
METHODS = []
HOOKS = [
    # Esc skips the Sierra fanfare / the title song (see user_handle_event_hook).
    (996, 0x08f, 7, user_handle_event_hook),  # User::handleEvent: link 2; pushi 4; push0; lap 1
]

def blocks_of(d):
    out = []; p = 0
    while p + 4 <= len(d):
        t, sz = struct.unpack('<HH', d[p:p+4])
        if t == 0: break
        out.append((t, p, sz)); p += sz
    return out, p

def method_table(d, obj):
    """(offset of the method count word, [(selector, offset of the code-offset word)]) of an object."""
    fsel = struct.unpack('<H', d[obj+4:obj+6])[0]
    q = obj + 6 + fsel
    n = struct.unpack('<H', d[q:q+2])[0]
    sels = struct.unpack('<%dH' % n, d[q+2:q+2+2*n])
    return [(s, q + 4 + 2*n + 2*i) for i, s in enumerate(sels)]

def replace_method(d, obj, selector, builder):
    entries = dict(method_table(d, obj))
    where = entries[selector]
    start = struct.unpack('<H', d[where:where+2])[0]
    # method end = next code start (any method/export) after it, or the end of its code block
    starts = set()
    blocks, end = blocks_of(d)
    for t, p, sz in blocks:
        if t in (1, 6):
            for _, w in method_table(d, p + 4): starts.add(struct.unpack('<H', d[w:w+2])[0])
        if t == 7:
            cnt = struct.unpack('<H', d[p+4:p+6])[0]
            starts.update(struct.unpack('<%dH' % cnt, d[p+6:p+6+2*cnt]))
    blk_end = next(p + sz for t, p, sz in blocks if t == 2 and p + 4 <= start < p + sz)
    stop = min([s for s in starts if s > start] + [blk_end])
    while d[stop-1] == 0: stop -= 1                                # trailing padding after the ret
    code = builder(bytes(d[start:stop]))
    if len(code) & 1: code += b'\0'
    # new code block goes in front of the relocation block (its entries all point below it)
    ins = next((p for t, p, sz in blocks if t == 8), end)
    blk = struct.pack('<HH', 2, len(code) + 4) + code
    d[ins:ins] = blk
    struct.pack_into('<H', d, where, ins + 4)
    return d

def hook_method(d, off, n, builder):
    assert n >= 3
    replaced = bytes(d[off:off + n])
    blocks, end = blocks_of(d)
    ins = next((p for t, p, sz in blocks if t == 8), end)
    tramp = ins + 4
    code = builder(replaced)
    code += jmp((off + n) - (tramp + len(code) + 3))
    if len(code) & 1: code += b'\0'
    d[off:off + n] = jmp(tramp - (off + 3)) + b'\0' * (n - 3)
    d[ins:ins] = struct.pack('<HH', 2, len(code) + 4) + code
    return d

if __name__ == '__main__':
    out = sys.argv[1]
    by_script = {}
    for n, off, old, new in PATCHES: by_script.setdefault(n, []).append(('bytes', off, old, new))
    for n, obj, sel, fn in METHODS: by_script.setdefault(n, []).append(('method', obj, sel, fn))
    for n, off, cnt, fn in HOOKS: by_script.setdefault(n, []).append(('hook', off, cnt, fn))
    for n, lst in by_script.items():
        d = bytearray(open(os.path.join(RES, str(n)), 'rb').read())
        for kind, a, b, c in lst:
            if kind == 'bytes':
                assert d[a:a + len(b)] == b, 'script %d +%x: expected %s, found %s' % (n, a, b.hex(), d[a:a + len(b)].hex())
                assert len(c) == len(b)
                d[a:a + len(c)] = c
            elif kind == 'method':
                d = replace_method(d, a, b, c)
            else:
                d = hook_method(d, a, b, c)
        path = os.path.join(out, '%d.SCR' % n)
        open(path, 'wb').write(b'\x82\x00' + bytes(d))   # SCI patch header: resource type $82 = script
        print('wrote', path, len(d), 'bytes,', len(lst), 'patch(es)')
