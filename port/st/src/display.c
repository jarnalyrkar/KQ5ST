/* graphics.library / intuition.library stand-ins and the ST display.
 *
 * Prog's video driver (hunk 52) draws into an Amiga BitMap: 5 separate planes, 40 bytes/row.
 * We let it keep doing that and periodically convert planes 0-3 into the ST low-res screen
 * (4 interleaved planes), so pixel colour = Amiga index & 15. The 16 ST colours come from the
 * first 16 entries given to LoadRGB4. */
#include "amiga.h"

/* ---- Amiga structures (only the fields Prog touches) ------------------------------------- */
struct BitMap { u16 bytesperrow, rows; u8 flags, depth; u16 pad; u8 *planes[8]; } PACKED;
CHECK(BitMap, planes, 8);

struct RasInfo { void *next; struct BitMap *bitmap; s16 rxoffset, ryoffset; } PACKED;
struct ViewPort { void *next, *colormap, *dspins, *sprins, *clrins, *ucopins;
                  s16 dwidth, dheight, dxoffset, dyoffset; u16 modes; u8 spritepri, extendedmodes;
                  struct RasInfo *rasinfo; } PACKED;
CHECK(ViewPort, rasinfo, 0x24);

#define SCREEN_VIEWPORT 0x2c
#define SCREEN_SIZE     0x160
#define WINDOW_USERPORT 0x56
#define WINDOW_SIZE     0x100

/* ---- ST screen ------------------------------------------------------------------------------ */
static u8 *st_screen;               /* 32000 bytes, 256-aligned */
static u8 *old_phys;
static int old_rez;
static u16 st_palette[16], old_palette[16];
static void splash_update(void);
static struct BitMap *shown;        /* bitmap of the open screen */
static u32 last_convert;
extern volatile u32 vbl_count;

static long set_palette_hw(void) { for (int i = 0; i < 16; i++) ((volatile u16 *)0xff8240)[i] = st_palette[i]; return 0; }
static long save_palette_hw(void) { for (int i = 0; i < 16; i++) old_palette[i] = ((volatile u16 *)0xff8240)[i]; return 0; }

static u16 amiga_to_ste(u16 c) {    /* $0RGB (4 bits each) -> STE nibble order (bit0 = LSB extension) */
    u16 r = (c >> 8) & 15, g = (c >> 4) & 15, b = c & 15;
#define STE(v) ((((v) >> 1) & 7) | (((v) & 1) << 3))
    return (STE(r) << 8) | (STE(g) << 4) | STE(b);
}

#define R struct regs *r
/* ---- mouse pointer -----------------------------------------------------------------------------
 * Software sprite on the ST screen, drawn at VBL time with the background saved underneath.
 * Screen updates from the main program lift it first (ptr_lock keeps the VBL away meanwhile). */
static u16 ptr_rows[32][2]; static int ptr_h, ptr_hx, ptr_hy;
extern volatile s16 mouse_x, mouse_y;
static volatile u8 ptr_lock;
static u8 ptr_drawn;
static int ptr_gx, ptr_y0, ptr_rows_saved, ptr_groups;   /* saved area: first group, first row, sizes */
static int ptr_mx = -1, ptr_my = -1;                       /* mouse position it was drawn for */
static u16 ptr_save[32][8];

static void ptr_remove(void) {
    if (!ptr_drawn) return;
    for (int r = 0; r < ptr_rows_saved; r++) {
        u16 *g = (u16 *)(st_screen + (ptr_y0 + r) * 160 + ptr_gx * 8);
        for (int k = 0; k < ptr_groups * 4; k++) g[k] = ptr_save[r][k];
    }
    ptr_drawn = 0;
}

static void ptr_place(void) {
    if (!st_screen || !ptr_h) return;
    int px = mouse_x - ptr_hx, py = mouse_y - ptr_hy;
    int y0 = py < 0 ? 0 : py, y1 = py + ptr_h > 200 ? 200 : py + ptr_h;
    int gx = px >> 4; if (gx < 0) gx = 0; if (gx > 19) gx = 19;
    int groups = gx < 19 ? 2 : 1, sh = px - gx * 16;          /* sh < 0 only at the left edge */
    ptr_gx = gx; ptr_y0 = y0; ptr_rows_saved = y1 > y0 ? y1 - y0 : 0; ptr_groups = groups;
    for (int y = y0; y < y1; y++) {
        u16 *g = (u16 *)(st_screen + y * 160 + gx * 8);
        for (int k = 0; k < groups * 4; k++) ptr_save[y - y0][k] = g[k];
        u32 p0 = ptr_rows[y - py][0], p1 = ptr_rows[y - py][1];
        u32 m = (p0 | p1) << 16, w = p1 << 16;                 /* colour 1 = black, 2/3 = white */
        if (sh >= 0) { m >>= sh; w >>= sh; } else { m <<= -sh; w <<= -sh; }
        u16 mh = m >> 16, ml = m, wh = w >> 16, wl = w;
        for (int k = 0; k < 4; k++) {
            g[k] = (g[k] & ~mh) | wh;
            if (groups == 2) g[4 + k] = (g[4 + k] & ~ml) | wl;
        }
    }
    ptr_drawn = 1; ptr_mx = mouse_x; ptr_my = mouse_y;
}

static void draw_pointer(void) { ptr_place(); }

/* VBL time */
void display_vbl(void) {
    if (ptr_lock || !st_screen) return;
    if (mouse_x != ptr_mx || mouse_y != ptr_my) { ptr_remove(); ptr_place(); }
}

void c_SetPointer(R) {
    ptr_lock = 1; ptr_remove();
    u16 *data = (u16 *)r->a[1] + 2; ptr_h = r->d[0] > 32 ? 32 : r->d[0];
    for (int i = 0; i < ptr_h; i++) { ptr_rows[i][0] = data[2 * i]; ptr_rows[i][1] = data[2 * i + 1]; }
    ptr_hx = -(s16)r->d[2]; ptr_hy = -(s16)r->d[3];
    ptr_place(); ptr_lock = 0;
}

/* Convert one rectangle (pixels, x rounded to 16) of the shown bitmap to the ST screen. */
void display_convert_rect(int x1, int y1, int x2, int y2) {
    if (!shown || !st_screen) return;
    if (y1 < 0) y1 = 0; if (y2 > 200) y2 = 200; if (x1 < 0) x1 = 0; if (x2 > 320) x2 = 320;
    int g1 = x1 >> 4, g2 = (x2 + 15) >> 4;
    if (y1 >= y2 || g1 >= g2) return;
    ptr_lock = 1;
    int hit = ptr_drawn && ptr_y0 < y2 && ptr_y0 + ptr_rows_saved > y1 && ptr_gx < g2 && ptr_gx + ptr_groups > g1;
    if (hit) ptr_remove();
    extern int blitter_ok;
    void blitter_rect(const void *, int, int, void *, int, int, int, int, u16, u16, int, int);
    void blitter_planes(int, const u8 *, int, int, s32, u8 *, int, int, s32, int, int, u16, u16, int, int);
    if (blitter_ok) {
        blitter_planes(4, shown->planes[0] + y1 * 40 + g1 * 2, 2, 40, shown->planes[1] - shown->planes[0],
                       st_screen + y1 * 160 + g1 * 8, 8, 160, 2, g2 - g1, y2 - y1, 0xffff, 0xffff, 2, 3);
    } else
    for (int y = y1; y < y2; y++) {
        u16 *p0 = (u16 *)(shown->planes[0] + y * 40) + g1, *p1 = (u16 *)(shown->planes[1] + y * 40) + g1;
        u16 *p2 = (u16 *)(shown->planes[2] + y * 40) + g1, *p3 = (u16 *)(shown->planes[3] + y * 40) + g1;
        u16 *o = (u16 *)(st_screen + y * 160) + g1 * 4;
        for (int g = g1; g < g2; g++) { o[0] = *p0++; o[1] = *p1++; o[2] = *p2++; o[3] = *p3++; o += 4; }
    }
    if (hit || !ptr_drawn) draw_pointer();
    ptr_lock = 0;
    if ((x2 - x1) * (y2 - y1) >= 320 * 200 * 3 / 4) splash_update();
}

/* Is p inside the shown bitmap's plane memory? */
int display_is_shown(const void *p) {
    if (!shown) return 0;
    const u8 *a = p;
    for (int i = 0; i < shown->depth; i++) if (a >= shown->planes[i] && a < shown->planes[i] + 40 * shown->rows) return 1;
    return 0;
}

void display_convert(void) {
    if (!shown || !st_screen) return;
    u16 *p0 = (u16 *)shown->planes[0], *p1 = (u16 *)shown->planes[1], *p2 = (u16 *)shown->planes[2], *p3 = (u16 *)shown->planes[3];
    u16 *o = (u16 *)st_screen;
    int rows = shown->rows < 200 ? shown->rows : 200;
    ptr_lock = 1; ptr_drawn = 0;            /* whole screen rewritten: nothing to restore */
    for (int n = rows * 20; n; n--) { o[0] = *p0++; o[1] = *p1++; o[2] = *p2++; o[3] = *p3++; o += 4; }
    draw_pointer(); ptr_lock = 0;
    splash_update();
    last_convert = vbl_count;
}

/* called from the wait loop */
void display_poll(void) {
    static u32 next_shot = 250;
    if (shown && vbl_count - last_convert >= 250) display_convert();   /* rare safety refresh */
    extern int autoplay_active;
    if (autoplay_active && shown && vbl_count >= next_shot) { next_shot = vbl_count + 250; display_shot(); }   /* test runs only */
}

/* Dump the ST screen + palette to C:\SHOTnn.ST (32 bytes palette + 32000 bytes) for inspection. */
void display_shot(void) {
    static int n; char name[16] = "SHOT00.ST";
    if (!st_screen) return;
    display_convert();
    name[4] = '0' + n / 10; name[5] = '0' + n % 10; n++;
    long h = Fcreate(name, 0);
    if (h < 0) { dbg("screenshot %s: Fcreate error %d\n", name, h); return; }
    Fwrite(h, 32, st_palette); Fwrite(h, 32000, st_screen); Fclose(h);
    dbg("screenshot %s at vbl %d\n", name, (int)vbl_count);
}

static void display_open(struct BitMap *bm) {
    if (!st_screen) {
        u8 *m = mem_alloc(32000 + 256, 0x10000);
        st_screen = (u8 *)(((u32)m + 255) & ~255UL);
        old_phys = (u8 *)Physbase();
        old_rez = Getrez();
        Supexec(save_palette_hw);
        /* The loader splash is shown before the game's first LoadRGB4; until then the hardware
         * palette is TOS's default (colour 0 white), so start with a black screen and palette.
         * Pointer colours 1-3 stay white so the cursor is still visible. */
        memset(st_screen, 0, 32000);
        memset(st_palette, 0, sizeof st_palette);
        for (int i = 1; i < 4; i++) st_palette[i] = 0xfff;
        Supexec(set_palette_hw);
        Setscreen((long)st_screen, (long)st_screen, 0);
    }
    shown = bm;
    dbg("display: bitmap %dx%d depth %d, planes $%x $%x ... (stride %d)\n", bm->bytesperrow * 8, bm->rows, bm->depth,
        (u32)bm->planes[0], (u32)bm->planes[1], (u32)(bm->planes[1] - bm->planes[0]));
}

/* ---- graphics.library -------------------------------------------------------------------------- */

void c_InitBitMap(R) {
    struct BitMap *bm = (struct BitMap *)r->a[0];
    bm->bytesperrow = ((r->d[1] + 15) >> 4) * 2; bm->rows = r->d[2]; bm->depth = r->d[0]; bm->flags = 0; bm->pad = 0;
}
void c_InitRastPort(R) { memset((void *)r->a[1], 0, 100); ((u8 *)r->a[1])[0x18] = 0xff; /* Mask */ }
/* The ST art set uses the 16 EGA colours everywhere, so the Amiga palette is replaced by the EGA
 * palette (exact on the STE: EGA levels 0/85/170/255 = STE 0/5/10/15). */
static const u16 ega_palette[16] = {
    0x000, 0x00a, 0x0a0, 0x0aa, 0xa00, 0xa0a, 0xa50, 0xaaa, 0x555, 0x55f, 0x5f5, 0x5ff, 0xf55, 0xf5f, 0xff5, 0xfff };
int use_ega_palette = 1;
/* The loader splash is one 1-bit picture: every pixel is colour 0 or 15 and most are 15. Sampled
 * groups of 16 pixels with equal bitplanes contain only those two colours. */
static int splash_frame(void) {
    const u16 *scr = (const u16 *)st_screen; int groups = 0, white = 0;
    for (int y = 0; y < 200; y += 2)
        for (int g = 0; g < 20; g += 2) {
            const u16 *p = scr + y * 80 + g * 4;
            if (p[0] != p[1] || p[0] != p[2] || p[0] != p[3]) return 0;
            white += p[0] == 0xffff; groups++;
        }
    return white * 2 >= groups;
}
/* Colour 15 is black while the splash is on screen, so its white never shows. */
static void splash_update(void) {
    u16 want = splash_frame() ? 0 : amiga_to_ste(ega_palette[15]);
    if (st_palette[15] == want) return;
    st_palette[15] = want;
    Supexec(set_palette_hw);
}
void c_LoadRGB4(R) {
    u16 *c = (u16 *)r->a[1]; int n = r->d[0] < 16 ? r->d[0] : 16;
    for (int i = 0; i < n; i++) st_palette[i] = amiga_to_ste(use_ega_palette ? ega_palette[i] : c[i]);
    Supexec(set_palette_hw);
}
void c_MakeVPort(R) { (void)r; }
void c_MrgCop(R) { (void)r; }
void c_LoadView(R) { (void)r; }
void c_WaitTOF(R) { (void)r; Vsync(); }
void c_WaitBOVP(R) { (void)r; }
void c_OwnBlitter(R) { (void)r; }
void c_DisownBlitter(R) { (void)r; }

/* ---- intuition.library ------------------------------------------------------------------------- */
static u8 *the_screen, *the_window;
static struct ViewPort *the_vp;
static u8 the_view[0x12];
static struct RasInfo the_rasinfo;

/* NewScreen: LeftEdge 0, TopEdge 2, Width 4, Height 6, Depth 8, ..., Type $e, Font $10,
 * DefaultTitle $14, Gadgets $18, CustomBitMap $1c */
void c_OpenScreen(R) {
    u8 *ns = (u8 *)r->a[0];
    struct BitMap *bm = *(struct BitMap **)(ns + 0x1c);
    the_screen = mem_alloc(SCREEN_SIZE, 0x10000);
    the_vp = (struct ViewPort *)(the_screen + SCREEN_VIEWPORT);
    the_vp->dwidth = *(s16 *)(ns + 4); the_vp->dheight = *(s16 *)(ns + 6);
    the_vp->rasinfo = &the_rasinfo; the_rasinfo.bitmap = bm;
    if (bm) display_open(bm);
    r->d[0] = (u32)the_screen;
}
void c_CloseScreen(R) { (void)r; }
void c_ShowTitle(R) { (void)r; }

/* NewWindow: ..., IDCMPFlags $a, Flags $e, ..., Screen $1e */
void c_OpenWindow(R) {
    u8 *nw = (u8 *)r->a[0];
    the_window = mem_alloc(WINDOW_SIZE, 0x10000);
    *(u32 *)(the_window + 0x2e) = *(u32 *)(nw + 0x1e);          /* WScreen */
    *(u32 *)(the_window + 0x52) = *(u32 *)(nw + 0x0a);          /* IDCMPFlags */
    struct MsgPort *up = mem_alloc(sizeof *up, 0x10000);
    up->sigbit = 31; up->sigtask = the_process; list_init(&up->msglist);
    the_process->task.sigalloc |= 1UL << 31;
    *(struct MsgPort **)(the_window + WINDOW_USERPORT) = up;
    dbg("OpenWindow: IDCMP $%x flags $%x\n", *(u32 *)(nw + 0x0a), *(u32 *)(nw + 0x0e));
    r->d[0] = (u32)the_window;
}
void c_CloseWindow(R) { (void)r; }
void c_ViewAddress(R) { r->d[0] = (u32)the_view; }
void c_ViewPortAddress(R) { r->d[0] = (u32)the_vp; }
void c_ClearPointer(R) { (void)r; }
void c_ModifyIDCMP(R) { if (r->a[0]) *(u32 *)(r->a[0] + 0x52) = r->d[0]; r->d[0] = -1; }
void c_OpenWorkBench(R) { r->d[0] = 0; }
void c_CloseWorkBench(R) { r->d[0] = -1; }

extern void stub_InitBitMap(void), stub_InitRastPort(void), stub_LoadRGB4(void), stub_MakeVPort(void), stub_MrgCop(void),
    stub_LoadView(void), stub_WaitTOF(void), stub_WaitBOVP(void), stub_OwnBlitter(void), stub_DisownBlitter(void),
    stub_OpenScreen(void), stub_CloseScreen(void), stub_ShowTitle(void), stub_OpenWindow(void), stub_CloseWindow(void),
    stub_ViewAddress(void), stub_ViewPortAddress(void), stub_SetPointer(void), stub_ClearPointer(void),
    stub_ModifyIDCMP(void), stub_OpenWorkBench(void), stub_CloseWorkBench(void);

void display_init(void) {
    GfxBase = make_library("graphics.library", 110, 0x100);
    static const struct { int lvo; void (*f)(void); } g[] = {
        { -192, stub_LoadRGB4 }, { -198, stub_InitRastPort }, { -210, stub_MrgCop }, { -216, stub_MakeVPort },
        { -222, stub_LoadView }, { -270, stub_WaitTOF }, { -390, stub_InitBitMap }, { -402, stub_WaitBOVP },
        { -456, stub_OwnBlitter }, { -462, stub_DisownBlitter } };
    for (unsigned i = 0; i < sizeof g / sizeof g[0]; i++) set_lvo(GfxBase, g[i].lvo, g[i].f);

    IntuitionBase = make_library("intuition.library", 60, 0x100);
    static const struct { int lvo; void (*f)(void); } t[] = {
        { -60, stub_ClearPointer }, { -66, stub_CloseScreen }, { -72, stub_CloseWindow }, { -78, stub_CloseWorkBench },
        { -150, stub_ModifyIDCMP }, { -198, stub_OpenScreen }, { -204, stub_OpenWindow }, { -210, stub_OpenWorkBench },
        { -270, stub_SetPointer }, { -282, stub_ShowTitle }, { -294, stub_ViewAddress }, { -300, stub_ViewPortAddress } };
    for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++) set_lvo(IntuitionBase, t[i].lvo, t[i].f);
}

void display_restore(void) {
    if (!st_screen) return;
    for (int i = 0; i < 16; i++) st_palette[i] = old_palette[i];
    Supexec(set_palette_hw);
    Setscreen((long)old_phys, (long)old_phys, old_rez);
}
