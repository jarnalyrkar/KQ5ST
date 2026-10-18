/* STE / Mega ST blitter. Used for the rectangle engine (blit.c) and the planar -> ST screen
 * conversion (display.c) when present; otherwise the CPU versions are used.
 * Runs in shared-bus (non-HOG) mode with the usual restart loop so interrupts keep being served.
 * Called only while Prog runs (supervisor mode). */
#include "amiga.h"

#define BLT(off, t) (*(volatile t *)(0xffff8a00 + (off)))
#define HALFTONE(i) BLT(0x00 + 2 * (i), u16)
#define SRC_XINC    BLT(0x20, s16)
#define SRC_YINC    BLT(0x22, s16)
#define SRC_ADDR    BLT(0x24, u32)
#define ENDMASK1    BLT(0x28, u16)
#define ENDMASK2    BLT(0x2a, u16)
#define ENDMASK3    BLT(0x2c, u16)
#define DST_XINC    BLT(0x2e, s16)
#define DST_YINC    BLT(0x30, s16)
#define DST_ADDR    BLT(0x32, u32)
#define X_COUNT     BLT(0x36, u16)
#define Y_COUNT     BLT(0x38, u16)
#define HOP         BLT(0x3a, u8)
#define OP          BLT(0x3b, u8)
#define CONTROL     BLT(0x3c, u8)
#define SKEW        BLT(0x3d, u8)

int blitter_ok;
long Blitmode(int mode);
void blitter_go(void);          /* glue.S: start + restart loop until done */

/* A file NOBLIT in the game directory forces the CPU path (testing, comparisons). */
static int getenv_noblit(void) { long h = Fopen("NOBLIT", 0); if (h < 0) return 0; Fclose(h); return 1; }

void blitter_init(void) {
    blitter_ok = (Blitmode(-1) & 2) != 0 && !getenv_noblit();
    dbg("blitter: %s\n", blitter_ok ? "present, used" : "not present (CPU fallback)");
}

/* Generic rectangle: `words` words per row, `rows` rows. Strides in bytes (row to row).
 * hop: 0 ones, 1 halftone, 2 source; op: blitter logic op (3 = source, 0/15 = clear/set, 10 = ~D,
 * 1 = S&D, 7 = S|D). Edge masks: first/last word of each row. */
void blitter_rect(const void *src, int src_xinc, int src_stride, void *dst, int dst_xinc, int dst_stride,
                  int words, int rows, u16 first, u16 last, int hop, int op) {
    if (words <= 0 || rows <= 0) return;
    SRC_XINC = src_xinc; SRC_YINC = src_stride - (words - 1) * src_xinc; SRC_ADDR = (u32)src;
    DST_XINC = dst_xinc; DST_YINC = dst_stride - (words - 1) * dst_xinc; DST_ADDR = (u32)dst;
    if (words == 1) { ENDMASK1 = first & last; ENDMASK2 = 0xffff; ENDMASK3 = 0xffff; }
    else { ENDMASK1 = first; ENDMASK2 = 0xffff; ENDMASK3 = last; }
    X_COUNT = words; Y_COUNT = rows;
    HOP = hop; OP = op; SKEW = 0;
    blitter_go();
}

/* The same rectangle on several planes: registers are set once; per further plane only the
 * addresses and the row count are reloaded (they are consumed by the blit). src may be 0. */
void blitter_planes(int planes, const u8 *src, int src_xinc, int src_stride, s32 src_step,
                    u8 *dst, int dst_xinc, int dst_stride, s32 dst_step,
                    int words, int rows, u16 first, u16 last, int hop, int op) {
    if (planes <= 0 || words <= 0 || rows <= 0) return;
    blitter_rect(src, src_xinc, src_stride, dst, dst_xinc, dst_stride, words, rows, first, last, hop, op);
    for (int p = 1; p < planes; p++) {
        src += src_step; dst += dst_step;
        SRC_ADDR = (u32)src; DST_ADDR = (u32)dst; Y_COUNT = rows;
        blitter_go();
    }
}

void blitter_halftone(u16 v) { for (int i = 0; i < 16; i++) HALFTONE(i) = v; }
