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
def bt(off):   return b'\x2e' + struct.pack('<h', off)
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
    # 16-colour script branches in every interpreter: KQ5::init stores kGraph(GetColorCount) in
    # global 105 (global 159 = more than 16), and the dialog/panel colours branch on it
    # (GRAPHICS.md "Dialog box colours"). Prog already answers 16 on the ST (prog.patch, hunk 55);
    # ScummVM answers 32 for Amiga KQ5, which with the EGA `spal` (makest.py) gave white boxes
    # with light blue frames. `push1; push2; callk Graph 2` -> `ldi 16` (word) + `ldi 16` (byte):
    # acc = 16 for the following `sag 105`, nothing pushed. Only call of GetColorCount in KQ5.
    (0, 0x845, b'\x78\x7a\x43\x6c\x02', b'\x34\x10\x00\x35\x10'),
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
    # Pause panel titles redrawn wider in font 69 (makest.py TEXT_CELS, view 946): gcWin::open draws
    # DETAIL and SPEED with DrawCel at a fixed left x (per-language constants + 10), so move them
    # left by the cels' added padding to keep them centred over their sliders: the final
    # `ldi 10; add` of each x becomes 10 - pad. (VOLUME keeps its width; GAME PAUSED is centred
    # by CelWide.)
    # DETAIL (loop 0 cel 4), pad 2 would give x 71, but the opaque cel then covers the button
    # column's border line at screen x 133 (user, 2026-11-07): x 72, text 1 pixel right of its slot.
    (755, 0x9dc, b'\x35\x0a\x02', b'\x35\x09\x02'),
    (755, 0xad9, b'\x35\x0a\x02', b'\x35\x09\x02'),   # SPEED (loop 0 cel 2), pad 1: x 156 -> 155
    # Labyrinth soft lock after Dink drops the hairpin (player report 2026-11-08). The Amiga
    # giveTamboScript (script 55) ends its state 12 with HandsOn and `(UnLoad SOUND 889)` but
    # never cues state 13 (dink dispose, self dispose): the room keeps the script, and
    # rm055::doit only changes maze square while `script` is 0, so Graham walked out of the
    # square into nothing unless he picked up the hairpin (getHairPinScript replaces the script).
    # The DOS script disposes itself in state 12. Replace the UnLoad with `(= cycles 1)` (ldi 1;
    # aTop cycles) and jump over the rest, so state 13 runs on the next cycle.
    (55, 0x11fc, b'\x7a\x38\x84\x00\x38\x79\x03\x43\x01\x04', b'\x35\x01\x65\x10\x32\x03\x00\x00\x00\x00'),
]
METHODS = []
HOOKS = [
    # Esc skips the Sierra fanfare / the title song (see user_handle_event_hook).
    (996, 0x08f, 7, user_handle_event_hook),  # User::handleEvent: link 2; pushi 4; push0; lap 1
]

# ---- Speech (SOUND.md "Speech", st/src/speech.c) -----------------------------------------------
# The text procedures start the line's CD clip and stop it when the text box closes:
#   start (replaces the procedure's `link`):
#     temp0 = (DoAudio 2 param[MOD] param[IDX])  ; clip length in ticks, 0 = no clip; MOD >= 1000
#                                                ; is a string (speech.c hashes its text)
#     if temp0: temp0 = temp0/60 + 2 (seconds) and every `#time n` (25 n) among the params from
#       FIRST on (FIRST-1 for a string, whose Print parameters start right after it) gets
#       n = temp0: a timed box stays up while the line is spoken, and no longer than that (the
#       reading time n made spoken lines wait; 2026-11-19, user)
#     a `#dispose` (107) among them makes the box modeless (Print returns at once): temp0 = 0, so
#       the clip is not stopped and plays to its end or until the next line replaces it
#   stop (every exit path jumps here): if temp0 (DoAudio 3); acc is kept (in temp1, which both
#   procedures only use before their Print returns).
# The cartoons time their modeless boxes with (proc932_2 english other) -> `seconds`; speech_wait
# makes it return the seconds left of the playing clip + 1 instead (whole seconds: the wait ends
# 0-1 s early, so +1 never cuts the line), from (DoAudio 6 1) in speech.c (Prog and ScummVM leave
# acc / answer -1, so nothing changes there). Values > 30 are kept: its other two callers
# (script 28, 763) pick values >= 113.
K_DoAudio = 117
def speech_patch(d, start, mod_p, idx_p, first, tails, retargets):
    """start: offset of the procedure's 3-byte `link`; tails: (offset, n) of `calle ...; ret`
    sequences (n bytes, the calle copied to a trampoline that then jumps to stop); retargets:
    offsets of `jmp` instructions to the procedure's `ret` that now jump to stop."""
    blocks, end = blocks_of(d)
    ins = next((p for t, p, sz in blocks if t == 8), end)
    base = ins + 4
    t = bytearray(); fix = []; labels = {}
    def br(op, label): fix.append((len(t) + 1, label)); t.extend(op(0))
    def lab(n): labels[n] = len(t)
    replaced = bytes(d[start:start + 3]); assert replaced[0] == 0x3e, replaced.hex()   # link (word)
    lst = lambda n: b'\x8d' + bytes([n]); lsp = lambda n: b'\x8f' + bytes([n])
    lapi = lambda n: b'\x97' + bytes([n]); sapi = lambda n: b'\xb7' + bytes([n])
    inc_at = lambda n: b'\xc5' + bytes([n])
    callk = lambda k, n: b'\x43' + bytes([k, n])
    ULT, DIV, ADD, LE = b'\x2a', b'\x08', b'\x02', b'\x24'
    t += replaced
    t += ldi(0) + pushi(3) + pushi(2) + lsp(mod_p) + lsp(idx_p) + callk(K_DoAudio, 6) + sat(0); br(bnt, 'back')   # acc stays 0 without speech
    t += lst(0) + ldi(60) + DIV + PUSH + ldi(2) + ADD + sat(0)
    t += ldi(first) + sat(1)
    t += lsp(mod_p) + ldi(1000) + ULT;                                    br(bt, 'loop')
    t += dec_at(1)                          # a string: the Print parameters start one earlier
    lab('loop')
    t += lst(1) + lap(0) + LE;                                            br(bnt, 'back')   # params are 1-based
    t += lat(1) + lapi(0) + PUSH + ldi(107) + EQ;                         br(bnt, 'time')
    t += ldi(0) + sat(0);                                                 br(jmp, 'next')
    lab('time')
    t += lat(1) + lapi(0) + PUSH + ldi(25) + EQ;                          br(bnt, 'next')
    t += lat(0);                                                          br(bnt, 'next')   # (0 after #dispose)
    t += lst(0) + lat(1) + sapi(1)
    lab('next')
    t += inc_at(1);                                                       br(jmp, 'loop')
    lab('back')
    fix.append((len(t) + 1, ('abs', start + 3))); t += jmp(0)
    lab('stop')
    t += sat(1) + lat(0);                                                 br(bnt, 'ret')
    t += PUSH1 + pushi(3) + callk(K_DoAudio, 2)
    lab('ret')
    t += lat(1) + RET
    for k, (off, n) in enumerate(tails):
        calle = bytes(d[off:off + n - 1]); assert calle[0] == 0x47 and d[off + n - 1] == 0x48, calle.hex()
        lab(('tail', k)); t += calle;                                     br(jmp, 'stop')
    for pos, label in fix:
        dest = label[1] if isinstance(label, tuple) and label[0] == 'abs' else base + labels[label]
        t[pos:pos + 2] = struct.pack('<h', dest - (base + pos + 2))
    if len(t) & 1: t += b'\0'
    # patch the procedure (offsets below ins, unaffected by the insertion)
    d[start:start + 3] = jmp(base - (start + 3))
    for k, (off, n) in enumerate(tails):
        d[off:off + n] = jmp(base + labels[('tail', k)] - (off + 3)) + b'\0' * (n - 3)
    for off in retargets:
        assert d[off] == 0x32, hex(d[off])
        d[off:off + 3] = jmp(base + labels['stop'] - (off + 3))
    d[ins:ins] = struct.pack('<HH', 2, len(t) + 4) + t
    return d

def speech_wait_patch(d, proc):
    """Point the export at `proc` to a wrapper: r = (proc &rest); s = (DoAudio 6 1);
    s > 0 and r <= 30 ? s + 1 : r."""
    blocks, end = blocks_of(d)
    exp = next(p for t, p, sz in blocks if t == 7)
    cnt = struct.unpack('<H', d[exp + 4:exp + 6])[0]
    slot = next(exp + 6 + 2 * i for i in range(cnt) if struct.unpack('<H', d[exp + 6 + 2 * i:exp + 8 + 2 * i])[0] == proc)
    ins = next((p for t, p, sz in blocks if t == 8), end)
    base = ins + 4
    lst = lambda n: b'\x8d' + bytes([n]); GT = b'\x1e'
    t = bytearray(link(2) + PUSH0 + b'\x59\x01')                         # push0 &rest 1
    t += b'\x40' + struct.pack('<h', proc - (base + len(t) + 4)) + b'\x00'   # call proc 0
    t += sat(0) + ldi(0) + b'\x7a' + pushi(6) + PUSH1 + b'\x43' + bytes([K_DoAudio, 4]) + sat(1)   # acc 0 if no clip
    ADD, LE = b'\x02', b'\x24'
    t += lst(1) + ldi(0) + GT + bnt(16)                               # a clip is playing
    t += lst(0) + ldi(30) + LE + bnt(7)                               # and the value is a time
    t += lst(1) + ldi(1) + ADD + RET                                  # -> seconds left + 1
    t += lat(0) + RET
    if len(t) & 1: t += b'\0'
    d[ins:ins] = struct.pack('<HH', 2, len(t) + 4) + t
    struct.pack_into('<H', d, slot, base)
    return d

SPEECH = [
    # PrintDC (script 759, export 0 @ $66): text = param 1, 2; Print gets params from 3 on
    (759, 0x66, 1, 2, 3, [(0x142, 5)], [0x7c, 0x138]),
    # proc0_28 (script 0, talker line with a portrait, @ $156d): text = param 2, 3; &rest from 4
    (0, 0x156d, 2, 3, 4, [(0x15f6, 5)], [0x15e1]),
]
SPEECH_WAIT = [(932, 0xa5)]     # the language picker the cartoons time their boxes with

# The intro scenes that time a modeless box with a constant, `(PrintDC ...) (= seconds N)`
# (`calle script759 0; ldi N; aTop 18`, 23 sites in 102, 104, 108, 109; none is a branch target
# past its first byte), get seconds = seconds left of the clip + 1 (N without a clip).
SECONDS_SCRIPTS = (102, 104, 108, 109)
sbyte = lambda v: v - 256 if v >= 128 else v       # the byte form of ldi is signed (`ldi 255` = -1)
def seconds_hook(replaced):
    assert replaced[0] == 0x35 and replaced[2:] == b'\x65\x12', replaced.hex()
    left = ldi(0) + b'\x7a' + pushi(6) + PUSH1 + b'\x43' + bytes([K_DoAudio, 4])   # acc = (DoAudio 6 1)
    n = ldi(sbyte(replaced[1]))
    plus1 = PUSH + ldi(1) + b'\x02'
    code = left + PUSH + ldi(0) + b'\x1e'               # a clip is playing?
    code += bnt(len(left) + len(plus1) + 3) + left + plus1 + jmp(len(n))   # yes: seconds left + 1
    return code + n + b'\x65\x12'                        # no: N; then seconds = acc
def seconds_sites(n):
    import re
    d = open(os.path.join(RES, str(n)), 'rb').read()
    pat = re.escape(b'\x46\xf7\x02\x00\x00') + b'.' + re.escape(b'\x35') + b'.' + re.escape(b'\x65\x12')
    return [(n, m.start() + 6, 4, seconds_hook) for m in re.finditer(pat, d, re.S)]
HOOKS += [h for n in SECONDS_SCRIPTS for h in seconds_sites(n)]

# Scenes 100, 102 and 109 also wait for music cues: `(if (< (global397 prevSignal) N) state--)`
# with cycles 1 (`lag 397; send 4; push; ldi N; lt?`, 16 sites), some also `(!= signal 255)`
# (music ended; `35 ff` = ldi -1; ne?). While a clip of ours is still playing the hook compares with
# 32767 instead of N / 255, so the next line waits for the spoken one.
# ((DoAudio 6 1) > 0: ScummVM's -1 and Prog's no-op leave the wait as it was.)
MUSIC_WAIT_SCRIPTS = (100, 102, 109)
def music_wait_hook(replaced):
    assert replaced[:2] == b'\x36\x35', replaced.hex()
    code = PUSH + ldi(0) + b'\x7a' + pushi(6) + PUSH1 + b'\x43' + bytes([K_DoAudio, 4])
    code += PUSH + ldi(0) + b'\x1e'                       # seconds left > 0?
    code += bnt(6) + ldi(0x7fff) + jmp(3)                 # yes: keep waiting
    return code + ldi(sbyte(replaced[2]))                 # no: the scene's own cue
def music_wait_sites(n):
    import re
    d = open(os.path.join(RES, str(n)), 'rb').read()
    pat = re.escape(b'\x80\x8d\x01\x4a\x04\x36\x35') + b'(.\x22|\xff\x1c)'    # < N, != 255
    return [(n, m.start() + 5, 3, music_wait_hook) for m in re.finditer(pat, d, re.S)]
HOOKS += [h for n in MUSIC_WAIT_SCRIPTS for h in music_wait_sites(n)]

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
    for n, *args in SPEECH: by_script.setdefault(n, []).append(('speech', args, 0, 0))
    for n, proc in SPEECH_WAIT: by_script.setdefault(n, []).append(('wait', proc, 0, 0))
    for n, lst in by_script.items():
        d = bytearray(open(os.path.join(RES, str(n)), 'rb').read())
        for kind, a, b, c in lst:
            if kind == 'bytes':
                assert d[a:a + len(b)] == b, 'script %d +%x: expected %s, found %s' % (n, a, b.hex(), d[a:a + len(b)].hex())
                assert len(c) == len(b)
                d[a:a + len(c)] = c
            elif kind == 'method':
                d = replace_method(d, a, b, c)
            elif kind == 'speech':
                d = speech_patch(d, *a)
            elif kind == 'wait':
                d = speech_wait_patch(d, a)
            else:
                d = hook_method(d, a, b, c)
        path = os.path.join(out, '%d.SCR' % n)
        open(path, 'wb').write(b'\x82\x00' + bytes(d))   # SCI patch header: resource type $82 = script
        print('wrote', path, len(d), 'bytes,', len(lst), 'patch(es)')
