"""Render SCI1 vector pictures (KQ5 DOS EGA and Amiga 32-colour) into visual/priority/control maps.

Port of the vector-picture logic in ScummVM engines/sci/graphics/picture.cpp + screen.cpp
(GPLv3+; see COPYING in the ScummVM tree). Pictures are rendered in picture-port coordinates:
320 x 190, no status-bar offset.
"""
import struct

W, H = 320, 190
MASK_V, MASK_P, MASK_C = 1, 2, 4

EGA_DEFAULT_PALETTE = bytes([
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0x88,
    0x88, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x88, 0x88, 0xf9, 0xfa, 0xfb, 0xfc, 0xfd, 0xfe, 0xff,
    0x08, 0x19, 0x2a, 0x3b, 0x4c, 0x5d, 0x6e, 0x88])

CIRCLES = [
    [0x01], [0x72, 0x02], [0xCE, 0xF7, 0x7D, 0x0E], [0x1C, 0x3E, 0x7F, 0x7F, 0x7F, 0x3E, 0x1C, 0x00],
    [0x38, 0xF8, 0xF3, 0xDF, 0x7F, 0xFF, 0xFD, 0xF7, 0x9F, 0x3F, 0x38],
    [0x70, 0xC0, 0x1F, 0xFE, 0xE3, 0x3F, 0xFF, 0xF7, 0x7F, 0xFF, 0xE7, 0x3F, 0xFE, 0xC3, 0x1F, 0xF8, 0x00],
    [0xF0, 0x01, 0xFF, 0xE1, 0xFF, 0xF8, 0x3F, 0xFF, 0xDF, 0xFF, 0xF7, 0xFF, 0xFD, 0x7F, 0xFF, 0x9F, 0xFF,
     0xE3, 0xFF, 0xF0, 0x1F, 0xF0, 0x01],
    [0xE0, 0x03, 0xF8, 0x0F, 0xFC, 0x1F, 0xFE, 0x3F, 0xFE, 0x3F, 0xFF, 0x7F, 0xFF, 0x7F, 0xFF, 0x7F, 0xFF,
     0x7F, 0xFF, 0x7F, 0xFE, 0x3F, 0xFE, 0x3F, 0xFC, 0x1F, 0xF8, 0x0F, 0xE0, 0x03]]

# Texture bit table: 32 bytes, each read LSB first (ScummVM stores it pre-expanded and doubled).
_TEX_BYTES = [0x04, 0x29, 0x40, 0x24, 0x09, 0x41, 0x25, 0x45, 0x41, 0x90, 0x50, 0x44, 0x48, 0x08, 0x42, 0x28,
              0x89, 0x52, 0x89, 0x88, 0x10, 0x48, 0xA4, 0x08, 0x44, 0x15, 0x28, 0x24, 0x00, 0x0A, 0x24, 0x20]
_tex_one = [bool((b >> i) & 1) for b in _TEX_BYTES for i in range(8)][:255]
TEXTURE = _tex_one + _tex_one
TEXTURE_OFFSET = [
    0x00, 0x18, 0x30, 0xc4, 0xdc, 0x65, 0xeb, 0x48, 0x60, 0xbd, 0x89, 0x04, 0x0a, 0xf4, 0x7d, 0x6d,
    0x85, 0xb0, 0x8e, 0x95, 0x1f, 0x22, 0x0d, 0xdf, 0x2a, 0x78, 0xd5, 0x73, 0x1c, 0xb4, 0x40, 0xa1,
    0xb9, 0x3c, 0xca, 0x58, 0x92, 0x34, 0xcc, 0xce, 0xd7, 0x42, 0x90, 0x0f, 0x8b, 0x7f, 0x32, 0xed,
    0x5c, 0x9d, 0xc8, 0x99, 0xad, 0x4e, 0x56, 0xa6, 0xf7, 0x68, 0xb7, 0x25, 0x82, 0x37, 0x3a, 0x51,
    0x69, 0x26, 0x38, 0x52, 0x9e, 0x9a, 0x4f, 0xa7, 0x43, 0x10, 0x80, 0xee, 0x3d, 0x59, 0x35, 0xcf,
    0x79, 0x74, 0xb5, 0xa2, 0xb1, 0x96, 0x23, 0xe0, 0xbe, 0x05, 0xf5, 0x6e, 0x19, 0xc5, 0x66, 0x49,
    0xf0, 0xd1, 0x54, 0xa9, 0x70, 0x4b, 0xa4, 0xe2, 0xe6, 0xe5, 0xab, 0xe4, 0xd2, 0xaa, 0x4c, 0xe3,
    0x06, 0x6f, 0xc6, 0x4a, 0x75, 0xa3, 0x97, 0xe1]


class Picture:
    def __init__(self, data, ega, ega_palette_no=0):
        self.d = data; self.ega = ega
        self.white = 15 if ega else 255
        self.vis = bytearray([self.white]) * (W * H)
        self.pri = bytearray(W * H); self.ctl = bytearray(W * H)
        self.palette_ops = []      # Amiga: list of 32-byte palette blocks (colours 0-15)
        self.embedded = []         # (x, y, w, h) of embedded cels
        self.cel_blocks = []       # Amiga: (FE-opcode offset, cel header offset, cel size)
        self.op_starts = []        # byte offset of every opcode, in order
        self.ops = {}              # opcode histogram
        self.egapal = bytearray(EGA_DEFAULT_PALETTE * 4); self.egapal_no = ega_palette_no

    # --- pixel helpers -------------------------------------------------------------
    def put(self, x, y, mask, c, p, k):
        o = y * W + x
        if mask & MASK_V: self.vis[o] = c
        if mask & MASK_P: self.pri[o] = p
        if mask & MASK_C: self.ctl[o] = k

    @staticmethod
    def drawing_mask(c, p, k):
        return (MASK_V if c != 255 else 0) | (MASK_P if p != 255 else 0) | (MASK_C if k != 255 else 0)

    def visible(self, x, y):
        c = self.vis[y * W + x]
        if not self.ega: return c
        return ((c ^ (c >> 4)) & 0x0F) if (x ^ y) & 1 else c & 0x0F

    def fill_match(self, x, y, mm, sc, sp, sk):
        o = y * W + x; m = 0
        if mm & MASK_V and self.visible(x, y) == sc: m |= MASK_V
        if mm & MASK_P and self.pri[o] == sp: m |= MASK_P
        if mm & MASK_C and self.ctl[o] == sk: m |= MASK_C
        return m

    # --- primitives ----------------------------------------------------------------
    def line(self, x0, y0, x1, y1, c, p, k):
        clip = lambda v, hi: max(0, min(v, hi))
        l, t, r, b = clip(x0, W - 1), clip(y0, H - 1), clip(x1, W - 1), clip(y1, H - 1)
        m = self.drawing_mask(c, p, k)
        if t == b:
            for i in range(min(l, r), max(l, r) + 1): self.put(i, t, m, c, p, k)
            return
        if l == r:
            for i in range(min(t, b), max(t, b) + 1): self.put(l, i, m, c, p, k)
            return
        dy, dx = b - t, r - l
        sy, sx = (-1 if dy < 0 else 1), (-1 if dx < 0 else 1)
        dy, dx = abs(dy) << 1, abs(dx) << 1
        self.put(l, t, m, c, p, k); self.put(r, b, m, c, p, k)
        if dx > dy:
            f = dy - (dx >> 1)
            while l != r:
                if f >= 0: t += sy; f -= dx
                l += sx; f += dy; self.put(l, t, m, c, p, k)
        else:
            f = dx - (dy >> 1)
            while t != b:
                if f >= 0: l += sx; f -= dy
                t += sy; f += dx; self.put(l, t, m, c, p, k)

    def fill(self, x, y, c, p, k):
        sm = self.drawing_mask(c, p, k)
        sc, sp, sk = self.visible(x, y), self.pri[y * W + x], self.ctl[y * W + x]
        if sm & MASK_V:
            if c == self.white or sc != self.white: return
        elif sm & MASK_P:
            if p == 0 or sp != 0: return
        elif sm & MASK_C:
            if k == 0 or sk != 0: return
        if sm & MASK_V and sc == c: sm &= ~MASK_V
        if sm & MASK_P and sp == p: sm &= ~MASK_P
        if sm & MASK_C and sk == k: sm &= ~MASK_C
        if not sm: return
        mm = MASK_V if sm & MASK_V else (MASK_P if sm & MASK_P else MASK_C)
        stack = [(x, y)]
        while stack:
            px, py = stack.pop()
            if not self.fill_match(px, py, mm, sc, sp, sk): continue
            self.put(px, py, sm, c, p, k)
            lft = rgt = px
            while lft > 0 and self.fill_match(lft - 1, py, mm, sc, sp, sk): lft -= 1; self.put(lft, py, sm, c, p, k)
            while rgt < W - 1 and self.fill_match(rgt + 1, py, mm, sc, sp, sk): rgt += 1; self.put(rgt, py, sm, c, p, k)
            a = b = False
            for cx in range(lft, rgt + 1):
                if py > 0 and self.fill_match(cx, py - 1, mm, sc, sp, sk):
                    if not a: stack.append((cx, py - 1)); a = True
                else: a = False
                if py < H - 1 and self.fill_match(cx, py + 1, mm, sc, sp, sk):
                    if not b: stack.append((cx, py + 1)); b = True
                else: b = False

    def pattern(self, x, y, c, p, k, code, tex):
        size = code & 7
        l, t, r, b = x - size, y - size, x + size + 2, y + size + 1
        if l < 0: r -= l; l = 0
        if t < 0: b -= t; t = 0
        if r > W + 1: l -= r - (W + 1); r = W + 1
        if b > H: t -= b - H; b = H
        m = self.drawing_mask(c, p, k)
        ti = TEXTURE_OFFSET[tex] if code & 0x20 else None
        if code & 0x10:  # rectangle
            for yy in range(t, b):
                for xx in range(l, r):
                    if ti is not None:
                        on = TEXTURE[ti]; ti += 1
                        if not on: continue
                    self._box_pixel(xx, yy, m, c, p, k)
        else:            # circle
            data = CIRCLES[size]; di = 0; bits = data[0]; bn = 0
            for yy in range(t, b):
                for xx in range(l, r):
                    if bn == 8: di += 1; bits = data[di] if di < len(data) else 0; bn = 0
                    if bits & 1:
                        draw = True
                        if ti is not None: draw = TEXTURE[ti]; ti += 1
                        if draw and 0 <= xx < W and 0 <= yy < H: self.put(xx, yy, m, c, p, k)
                    bn += 1; bits >>= 1

    def _box_pixel(self, x, y, m, c, p, k):
        if not (0 <= x and 0 <= y < H): return
        if x < W: self.put(x, y, m, c, p, k)
        elif y < H - 1:
            if c != 255 and c & 0xF0:
                c ^= (c << 4) & 0xFF; c = ((c << 4) | (c >> 4)) & 0xFF; c ^= (c << 4) & 0xFF
            self.put(0, y + 1, m, c, p, k)

    def embedded_cel(self, pos, x, y, ega):
        d = self.d; w, h = struct.unpack('<HH', d[pos:pos+4]); key = d[pos + 6]; n = w * h
        px = bytearray([key]) * n; i = 0; q = pos + 8
        while i < n:
            b = d[q]; q += 1
            if ega:
                r = b >> 4; px[i:i+r] = bytes([b & 15]) * min(r, n - i)
            elif b & 7:
                r = b & 7; px[i:i+r] = bytes([b >> 3]) * min(r, n - i)
            else:
                r = b >> 3
            i += r
        self.embedded.append((x, y, w, h))
        for j in range(n):
            c = px[j]; xx, yy = x + j % w, y + j // w
            if xx >= W or yy >= H: continue
            if ega:     # priority 16 in KQ5 EGA: visual only, no priority test
                if c != key: self.put(xx, yy, MASK_V, c, 0, 0)
            elif c != self.white and 0 >= self.pri[yy * W + xx]:
                self.put(xx, yy, MASK_V | MASK_P, c, 0, 0)

    # --- decoding --------------------------------------------------------------------
    def render(self):
        d = self.d; pos = 0; x = y = 0
        c, p, k = 0, 255, 255; pcode = ptex = 0
        nonop = lambda: pos < len(d) and d[pos] < 0xF0
        def absxy():
            nonlocal pos
            b = d[pos]; xx = d[pos + 1] + ((b & 0xF0) << 4); yy = d[pos + 2] + ((b & 0x0F) << 8); pos += 3
            return xx, yy
        def rel(xx, yy):
            nonlocal pos
            b = d[pos]; pos += 1
            xx += -((b >> 4) & 7) if b & 0x80 else (b >> 4)
            yy += -(b & 7) if b & 8 else (b & 7)
            return xx, yy
        def relmed(xx, yy):
            nonlocal pos
            b = d[pos]; pos += 1; yy += -(b & 0x7F) if b & 0x80 else b
            b = d[pos]; pos += 1; xx += -(128 - (b & 0x7F)) if b & 0x80 else b
            return xx, yy
        def tex():
            nonlocal pos, ptex
            if pcode & 0x20: ptex = (d[pos] >> 1) & 0x7F; pos += 1
        while pos < len(d):
            self.op_starts.append(pos)
            op = d[pos]; pos += 1; self.ops[op] = self.ops.get(op, 0) + 1
            if op == 0xF0:
                c = d[pos]; pos += 1
                if self.ega:
                    c = self.egapal[self.egapal_no * 40 + c]; c = (c ^ (c << 4)) & 0xFF
            elif op == 0xF1: c = 255
            elif op == 0xF2: p = d[pos] & 0x0F; pos += 1
            elif op == 0xF3: p = 255
            elif op == 0xFB: k = d[pos] & 0x0F; pos += 1
            elif op == 0xFC: k = 255
            elif op in (0xF7, 0xF5, 0xF6):
                x, y = absxy()
                while nonop():
                    ox, oy = x, y
                    x, y = rel(x, y) if op == 0xF7 else relmed(x, y) if op == 0xF5 else absxy()
                    self.line(ox, oy, x, y, c, p, k)
            elif op == 0xF8:
                while nonop():
                    x, y = absxy()
                    if 0 <= x < W and 0 <= y < H: self.fill(x, y, c, p, k)
            elif op == 0xF9: pcode = d[pos]; pos += 1
            elif op in (0xF4, 0xFD):
                tex(); x, y = absxy(); self.pattern(x, y, c, p, k, pcode, ptex)
                while nonop():
                    tex(); x, y = rel(x, y) if op == 0xF4 else relmed(x, y); self.pattern(x, y, c, p, k, pcode, ptex)
            elif op == 0xFA:
                while nonop():
                    tex(); x, y = absxy(); self.pattern(x, y, c, p, k, pcode, ptex)
            elif op == 0xFE:
                sub = d[pos]; pos += 1; self.ops[0xFE00 + sub] = self.ops.get(0xFE00 + sub, 0) + 1
                if self.ega:
                    if sub == 0:
                        while nonop(): self.egapal[d[pos]] = d[pos + 1]; pos += 2
                    elif sub == 1:
                        n = d[pos]; self.egapal[n * 40:(n + 1) * 40] = d[pos + 1:pos + 41]; pos += 41
                    elif sub == 2: pos += 41
                    elif sub in (3, 5): pos += 1
                    elif sub in (4, 6): pass
                    elif sub == 7:
                        ex, ey = absxy(); size = struct.unpack('<H', d[pos:pos+2])[0]; pos += 2
                        self.embedded_cel(pos, ex, ey, True); pos += size
                    elif sub == 8: pos += 14
                    else: raise ValueError(f'EGA opx {sub}')
                else:
                    if sub == 0:
                        while nonop(): pos += 1
                    elif sub == 1:
                        op_at = pos - 2
                        ex, ey = absxy(); size = struct.unpack('<H', d[pos:pos+2])[0]; pos += 2
                        self.cel_blocks.append((op_at, pos, size))
                        self.embedded_cel(pos, ex, ey, False); pos += size
                    elif sub == 2:
                        if d[pos] == 0 and d[pos + 1] == 1 and (d[pos + 32] & 0xF0) != 0xF0: pos += 256 + 4 + 1024
                        else: self.palette_ops.append(bytes(d[pos:pos + 32])); pos += 32
                    elif sub == 3: pos += 4
                    elif sub == 4: pos += 14
                    else: raise ValueError(f'VGA opx {sub}')
            elif op == 0xFF:
                break
            else:
                raise ValueError(f'bad opcode {op:#x} at {pos - 1}')
        if self.ega:
            for yy in range(H):
                for xx in range(W):
                    o = yy * W + xx; cc = self.vis[o]
                    if cc & 0xF0:
                        cc ^= (cc << 4) & 0xFF
                        self.vis[o] = (cc >> 4) if (xx ^ yy) & 1 else cc & 0x0F
        return self


def render(data, ega, ega_palette_no=0):
    return Picture(data, ega, ega_palette_no).render()
