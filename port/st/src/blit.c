/* CPU replacement for the KQ5 Amiga video driver's blitter rectangle engine (hunk 52 +$872).
 *
 * In:  d0 = top, d1 = left, d2 = bottom (excl.), d3 = right (excl.)
 *      d4 = plane count (1 = chunky byte map), d5 = mode << 16 | colour
 *      a0 = source, a2 = destination, a4 = Prog's small-data base
 * Modes (exactly as the blitter code, including the packed save-buffer layouts):
 *   1  colour < $fe: fill planes   colour $ff: copy planes a0 -> a2   colour $fe: invert planes a2
 *   2  save planes a0 (screen) -> packed a2       4  restore packed a0 -> planes a2
 *   3  save chunky a0 (320/row) -> packed a2      5  restore packed a0 -> chunky a2
 * Packed buffers hold, per plane, `height` rows of `words` words, masked with the edge masks.
 *
 * Only planes 0-3 are processed: the ST shows 4 planes and the ST art uses colours 0-15, so plane 4
 * is never visible. Save and restore both skip it, so the packed layout stays consistent. */
#include "amiga.h"

#define A4G(off, type) (*(type *)(r->a[4] - (off)))   /* Prog global at -off(a4) */
#define PLANE_STRIDE_SRC A4G(0x6808, s32)
#define PLANE_STRIDE_DST A4G(0x6804, s32)
#define ROWTAB40  ((u16 *)(r->a[4] - 0x6624))
#define ROWTAB320 ((u16 *)(r->a[4] - 0x67b4))
#define ST_PLANES 4

static inline u16 edge(int w, int words, u16 first, u16 last) {
    return (w == 0 ? first : 0xffff) & (w == words - 1 ? last : 0xffff);
}

/* One row of words: d = (s & m) | (d & ~m) with edge masks. */
static inline void row_copy(u16 *d, const u16 *s, int words, u16 first, u16 last) {
    if (words == 1) { u16 m = first & last; *d = (*s & m) | (*d & ~m); return; }
    *d = (*s & first) | (*d & ~first); d++; s++;
    for (int n = words - 2; n > 0; n--) *d++ = *s++;
    *d = (*s & last) | (*d & ~last);
}
static inline void row_fill(u16 *d, u16 v, int words, u16 first, u16 last) {
    if (words == 1) { u16 m = first & last; *d = (v & m) | (*d & ~m); return; }
    *d = (v & first) | (*d & ~first); d++;
    for (int n = words - 2; n > 0; n--) *d++ = v;
    *d = (v & last) | (*d & ~last);
}
static inline void row_invert(u16 *d, int words, u16 first, u16 last) {
    if (words == 1) { *d ^= first & last; return; }
    *d++ ^= first;
    for (int n = words - 2; n > 0; n--) { *d = ~*d; d++; }
    *d ^= last;
}
/* save: packed = s & mask */
static inline u16 *row_save(u16 *pk, const u16 *s, int words, u16 first, u16 last) {
    if (words == 1) { *pk++ = *s & first & last; return pk; }
    *pk++ = *s++ & first;
    for (int n = words - 2; n > 0; n--) *pk++ = *s++;
    *pk++ = *s & last;
    return pk;
}
/* restore: masked copy packed -> d (also correct when the packed edge words hold extra bits) */
static inline const u16 *row_restore(u16 *d, const u16 *pk, int words, u16 first, u16 last) {
    row_copy(d, pk, words, first, last);
    return pk + words;
}

extern int blitter_ok;
void blitter_rect(const void *src, int src_xinc, int src_stride, void *dst, int dst_xinc, int dst_stride,
                  int words, int rows, u16 first, u16 last, int hop, int op);
void blitter_halftone(u16 v);
void blitter_planes(int planes, const u8 *src, int src_xinc, int src_stride, s32 src_step,
                    u8 *dst, int dst_xinc, int dst_stride, s32 dst_step,
                    int words, int rows, u16 first, u16 last, int hop, int op);
#define HOP_ONES 0
#define HOP_HALFTONE 1
#define HOP_SRC 2
#define OP_ZERO 0
#define OP_AND 1
#define OP_SRC 3
#define OP_OR 7
#define OP_NOTD 10
#define OP_ONES 15

void c_blit(struct regs *r) {
    int y1 = (s16)r->d[0], x1 = (s16)r->d[1], y2 = (s16)r->d[2], x2 = (s16)r->d[3];
    int planes = (s16)r->d[4], mode = (r->d[5] >> 16) & 0xffff, colour = r->d[5] & 0xff;
    u16 first, last;
    int chunky = planes == 1;

    if (chunky) {
        first = (x1 & 1) ? 0x00ff : 0xffff; x1 &= ~1;
        last = (x2 & 1) ? 0xff00 : 0xffff; x2 = (x2 + 1) & ~1;
    } else {
        first = 0xffff >> (x1 & 15);
        last = ~(0xffff >> (x2 & 15)); if (!last) last = 0xffff;
        x1 &= ~15; x2 = (x2 + 15) & ~15;
    }
    int h = y2 - y1, wpix = x2 - x1;
    if (h <= 0 || wpix <= 0) return;

    if (mode == 1 || mode == 2 || mode == 4) {
        int words = wpix >> 4, np = planes < ST_PLANES ? planes : ST_PLANES;
        u32 off = ROWTAB40[y1] + (x1 >> 3);
        s32 sstride = PLANE_STRIDE_SRC, dstride = PLANE_STRIDE_DST;
        if (blitter_ok) {
            u8 *src = (u8 *)r->a[0] + off, *dst = (u8 *)r->a[2] + off;
            if (mode == 1 && colour == 0xff)
                blitter_planes(np, src, 2, 40, sstride, dst, 2, 40, dstride, words, h, first, last, HOP_SRC, OP_SRC);
            else if (mode == 1 && colour == 0xfe)
                blitter_planes(np, 0, 0, 0, 0, dst, 2, 40, sstride, words, h, first, last, HOP_ONES, OP_NOTD);
            else if (mode == 1)
                for (int p = 0; p < np; p++)        /* fill: the op differs per plane */
                    blitter_rect(0, 0, 0, dst + p * sstride, 2, 40, words, h, first, last, HOP_ONES,
                                 (colour & (1 << p)) ? OP_ONES : OP_ZERO);
            else if (mode == 2)
                blitter_planes(np, src, 2, 40, sstride, (u8 *)r->a[2], 2, words * 2, words * h * 2,
                               words, h, 0xffff, 0xffff, HOP_SRC, OP_SRC);
            else
                blitter_planes(np, (const u8 *)r->a[0], 2, words * 2, words * h * 2, dst, 2, 40, sstride,
                               words, h, first, last, HOP_SRC, OP_SRC);
        } else if (mode == 1) {
            u8 *src = (u8 *)r->a[0] + off, *dst = (u8 *)r->a[2] + off;
            for (int p = 0; p < np; p++) {
                if (colour == 0xff) {
                    for (int y = 0; y < h; y++) row_copy((u16 *)(dst + y * 40), (u16 *)(src + y * 40), words, first, last);
                    src += sstride; dst += dstride;
                } else if (colour == 0xfe) {
                    for (int y = 0; y < h; y++) row_invert((u16 *)(dst + y * 40), words, first, last);
                    dst += sstride;
                } else {
                    u16 v = (colour & (1 << p)) ? 0xffff : 0;
                    for (int y = 0; y < h; y++) row_fill((u16 *)(dst + y * 40), v, words, first, last);
                    dst += sstride;
                }
            }
        } else if (mode == 2) {
            u8 *src = (u8 *)r->a[0] + off; u16 *pk = (u16 *)r->a[2];
            for (int p = 0; p < np; p++, src += sstride)
                for (int y = 0; y < h; y++) pk = row_save(pk, (u16 *)(src + y * 40), words, first, last);
        } else {
            const u16 *pk = (const u16 *)r->a[0]; u8 *dst = (u8 *)r->a[2] + off;
            for (int p = 0; p < np; p++, dst += sstride)
                for (int y = 0; y < h; y++) pk = row_restore((u16 *)(dst + y * 40), pk, words, first, last);
        }
        if (mode != 2 && display_is_shown((u8 *)r->a[2] + off)) display_convert_rect(x1, y1, x2, y2);
        display_poll();
        return;
    }

    if (mode == 3 || mode == 5) {
        int words = wpix >> 1;
        u32 off = ROWTAB320[y1] + x1;
        if (blitter_ok) {
            if (mode == 3) blitter_rect((u8 *)r->a[0] + off, 2, 320, (void *)r->a[2], 2, words * 2, words, h, 0xffff, 0xffff, HOP_SRC, OP_SRC);
            else blitter_rect((void *)r->a[0], 2, words * 2, (u8 *)r->a[2] + off, 2, 320, words, h, first, last, HOP_SRC, OP_SRC);
            return;
        }
        if (mode == 3) {
            u16 *s0 = (u16 *)((u8 *)r->a[0] + off), *pk = (u16 *)r->a[2];
            for (int y = 0; y < h; y++, s0 += 160) pk = row_save(pk, s0, words, first, last);
        } else {
            const u16 *pk = (const u16 *)r->a[0]; u16 *d0 = (u16 *)((u8 *)r->a[2] + off);
            for (int y = 0; y < h; y++, d0 += 160) pk = row_restore(d0, pk, words, first, last);
        }
        return;
    }
    dbg("blit: unknown mode %d\n", mode);
}

/* Priority/control fill inside Graph (hunk 55 +$128..+$183, one blitter pass):
 * D = (A & B) | (~A & C) with A = d4 (nibble mask) & edge masks, B = d0 (pattern), C = D = a1.
 * d2 = BLTSIZE (rows << 6 | words), d5 = row modulo in bytes, d6 = first mask << 16 | last mask. */
void c_pcfill(struct regs *r) {
    int rows = (r->d[2] >> 6) & 1023, words = r->d[2] & 63;
    if (!rows) rows = 1024;
    if (!words) words = 64;
    u16 a = r->d[4], b = r->d[0], first = r->d[6] >> 16, last = r->d[6];
    u16 *d = (u16 *)r->a[1]; int mod = (s16)r->d[5] >> 1;
    if (blitter_ok) {                       /* D & ~a, then D | (b & a), both with edge masks */
        blitter_halftone(~a);
        blitter_rect(0, 0, 0, d, 2, (words + mod) * 2, words, rows, first, last, HOP_HALFTONE, OP_AND);
        blitter_halftone(b & a);
        blitter_rect(0, 0, 0, d, 2, (words + mod) * 2, words, rows, first, last, HOP_HALFTONE, OP_OR);
        return;
    }
    for (int y = 0; y < rows; y++, d += words + mod)
        for (int w = 0; w < words; w++) { u16 m = a & edge(w, words, first, last); d[w] = (b & m) | (d[w] & ~m); }
}
