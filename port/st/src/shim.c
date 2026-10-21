/* KQ5 TOS shim: core helpers, diagnostics and start-up (replaces the Amiga "kq5" loader). */
#include <stdarg.h>
#include "amiga.h"

void nf_init(void);
void nf_exit(long code);

/* ---- kernel call trace (hook at hunk 4 +$9ee, the callk dispatcher; glue.S hook_ktrace) -----
 * Logs selected kernel functions with their arguments and result. KTRACE file in the game folder
 * enables it. */
int ktrace_on;
static int ktrace_k = -1;
static const char *kname(int k) {
    switch (k) {
    case 0x77: return "AvoidPath"; case 0x3f: return "GetAngle"; case 0x4f: return "InitBresen";
    case 0x72: return "Memory"; case 0x68: return "SinMult"; case 0x69: return "CosMult";
    case 0x4d: return "CanBeHere";
    }
    return 0;
}
extern volatile u32 vbl_count;
void c_ktrace_pre(struct regs *r) {
    int k = (r->d[1] & 0xffff) / 4; ktrace_k = -1;             /* only d1.w is the number */
    if (!ktrace_on) return;
    if (k == 0x4b || k == 0x4d || k == 0x50 || k == 0x1c || k == 0x0b || k == 0x3b || k == 0x1a || k == 0x7c) return;   /* per-frame noise */
    ktrace_k = k;
    s16 *a = (s16 *)r->a[2]; int n = a[0];
    if (kname(k)) dbg("k %d %s(", (int)vbl_count, kname(k)); else dbg("k %d $%x(", (int)vbl_count, k);
    for (int i = 1; i <= n && i <= 8; i++) dbg("%s%d", i > 1 ? "," : "", a[i]);
    dbg(")");
}
void c_ktrace_post(struct regs *r) {
    if (ktrace_k < 0) return;
    dbg(" -> %d", (int)r->d[0]);
    if (ktrace_k == 0x77 && r->d[0]) {              /* AvoidPath: dump the path points */
        s16 *p = (s16 *)r->d[0];
        for (int i = 0; i < 12 && p[i] != 0x7777; i++) dbg(" %d", p[i]);
    }
    dbg("\n");
}

/* ---- strings ---------------------------------------------------------------------- */
void *memset(void *d, int c, unsigned long n) {
    u8 *p = d;
    while (n && ((u32)p & 3)) { *p++ = c; n--; }
    u32 v = (u8)c; v |= v << 8; v |= v << 16;
    for (u32 *q = (u32 *)p; n >= 4; n -= 4) *q++ = v, p += 4;
    while (n--) *p++ = c;
    return d;
}
void *memcpy(void *d, const void *s, unsigned long n) { u8 *p = d; const u8 *q = s; while (n--) *p++ = *q++; return d; }
int strlen(const char *s) { int n = 0; while (s[n]) n++; return n; }
int strcmp(const char *a, const char *b) { while (*a && *a == *b) a++, b++; return (u8)*a - (u8)*b; }
static int lower(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }
int stricmp(const char *a, const char *b) { while (*a && lower(*a) == lower(*b)) a++, b++; return lower((u8)*a) - lower((u8)*b); }
char *strcpy(char *d, const char *s) { char *r = d; while ((*d++ = *s++)); return r; }
char *strcat(char *d, const char *s) { strcpy(d + strlen(d), s); return d; }

/* ---- debug output (Hatari NatFeats; without it only crash reports go to the console) ---- */
static int console_on;
void nf_print(const char *s) { if (nf_available()) nf_stderr(s); else if (console_on) Cconws(s); }

static char *put_num(char *o, u32 v, int base, int width, int neg) {
    char t[12]; int n = 0;
    do { t[n++] = "0123456789abcdef"[v % base]; v /= base; } while (v);
    while (n < width) t[n++] = '0';
    if (neg) *o++ = '-';
    while (n) *o++ = t[--n];
    return o;
}

static void vfmt(char *o, const char *f, va_list ap) {
    while (*f) {
        if (*f != '%') { *o++ = *f++; continue; }
        f++; int width = 0;
        while (*f >= '0' && *f <= '9') width = width * 10 + *f++ - '0';
        switch (*f++) {
        case 's': { const char *s = va_arg(ap, const char *); if (!s) s = "(null)"; while (*s) *o++ = *s++; break; }
        case 'x': o = put_num(o, va_arg(ap, u32), 16, width, 0); break;
        case 'd': { s32 v = va_arg(ap, s32); o = put_num(o, v < 0 ? -v : v, 10, width, v < 0); break; }
        case 'u': o = put_num(o, va_arg(ap, u32), 10, width, 0); break;
        case 'c': *o++ = va_arg(ap, int); break;
        case 'H': { const char *s = hunk_addr(va_arg(ap, u32)); while (*s) *o++ = *s++; break; }
        default: *o++ = f[-1];
        }
    }
    *o = 0;
}

void dbg(const char *fmt, ...) {
    char buf[320]; va_list ap; va_start(ap, fmt); vfmt(buf, fmt, ap); va_end(ap); nf_print(buf);
}

void fatal(const char *fmt, ...) {
    char buf[320]; va_list ap; va_start(ap, fmt); vfmt(buf, fmt, ap); va_end(ap);
    console_on = 1;
    nf_print("FATAL: "); nf_print(buf); nf_print("\n");
    display_shot();
    nf_exit(1);
    for (;;) ;
}

/* ---- Prog address naming -------------------------------------------------------------- */
#include "hunkstarts.inc"   /* const u32 hunk_off[]; int hunk_count; (offsets from hunk0) */

const char *hunk_addr(u32 a) {
    static char buf[2][24]; static int k; char *b = buf[k ^= 1];
    u32 base = (u32)hunk0;
    if (a < base || a >= (u32)prog_end) { char *o = b; *o++ = '$'; o = put_num(o, a, 16, 6, 0); *o = 0; return b; }
    u32 off = a - base; int h = 0;
    while (h + 1 < hunk_count && hunk_off[h + 1] <= off) h++;
    char *o = b; *o++ = 'H'; o = put_num(o, h, 10, 0, 0); *o++ = '_'; o = put_num(o, off - hunk_off[h], 16, 0, 0); *o = 0;
    return b;
}

/* ---- failure reporting ------------------------------------------------------------- */
static const char *exc_name(int v) {
    switch (v) { case 2: return "bus error"; case 3: return "address error"; case 4: return "illegal instruction";
    case 5: return "divide by zero"; case 8: return "privilege violation"; case 10: return "line-A"; case 11: return "line-F"; }
    return "exception";
}

void c_exception(u32 *f) {
    /* f: usp, d0-d7, a0-a7, then vector word, then the CPU frame */
    u16 *w = (u16 *)(f + 17); int vec = w[0]; u32 pc;
    console_on = 1;
    if (vec == 2 || vec == 3) {      /* 68000 group 0 frame: fc.w, addr.l, ir.w, sr.w, pc.l */
        u32 addr = (w[2] << 16) | w[3]; pc = (w[6] << 16) | w[7];
        dbg("\n*** %s at %H (pc $%x), access $%x %s, ir %4x, sr %4x\n", exc_name(vec), pc, pc, addr,
            (w[1] & 0x10) ? "read" : "write", w[4], w[5]);
    } else {
        pc = (w[2] << 16) | w[3];
        dbg("\n*** %s at %H (pc $%x), sr %4x\n", exc_name(vec), pc, pc, w[1]);
    }
    dbg("d0-7 %8x %8x %8x %8x %8x %8x %8x %8x\n", f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8]);
    dbg("a0-6 %8x %8x %8x %8x %8x %8x %8x  usp %8x\n", f[9], f[10], f[11], f[12], f[13], f[14], f[15], f[0]);
    u16 sr = (vec == 2 || vec == 3) ? w[5] : w[1];
    u32 *sp = (sr & 0x2000) ? (u32 *)((u8 *)f[16] + 2 + ((vec == 2 || vec == 3) ? 14 : 6)) : (u32 *)f[0];
    dbg("%s stack: %H %H %H %H %H %H %H %H\n", (sr & 0x2000) ? "super" : "user",
        sp[0], sp[1], sp[2], sp[3], sp[4], sp[5], sp[6], sp[7]);
    fatal("stopped");
}

/* ---- PC sampling profiler (VBL) ---- */
extern u32 pc_samples[256], old_vbl_vector;
extern char pcsample_entry[];
static long install_sampler(void) { old_vbl_vector = *(u32 *)0x70; *(u32 *)0x70 = (u32)pcsample_entry; return 0; }
/* Exit: put the VBL vector back and stop the profiler's Timer A if it ran (MFP TACR, IERA/IMRA
 * bit 5); both point into this program, which TOS frees at Pterm. */
extern u16 *prof_hist_ptr;
static long remove_interrupts(void) {
    *(u32 *)0x70 = old_vbl_vector;
    if (prof_hist_ptr) {
        *(volatile u8 *)0xfffffa19 = 0;
        *(volatile u8 *)0xfffffa07 &= ~0x20; *(volatile u8 *)0xfffffa13 &= ~0x20;
    }
    return 0;
}
void pc_report(void) {
    static u32 pcs[256]; static int cnt[256]; int n = 0;
    for (int i = 0; i < 256; i++) {
        u32 pc = pc_samples[i]; if (!pc) continue;
        int j; for (j = 0; j < n && pcs[j] != pc; j++) ;
        if (j == n) { pcs[n] = pc; cnt[n] = 0; n++; }
        cnt[j]++;
    }
    for (int k = 0; k < 8 && n; k++) {
        int best = 0; for (int j = 1; j < n; j++) if (cnt[j] > cnt[best]) best = j;
        if (!cnt[best]) break;
        dbg("  pc %H: %d\n", pcs[best], cnt[best]); cnt[best] = 0;
    }
}

/* Called from the VBL queue (supervisor, interrupt time): periodic diagnostics. */
extern volatile u32 vbl_count;
u32 report_every = 0;
/* Profiler: one counter per 64 bytes of the program image, sampled by MFP Timer A (~1117 Hz,
 * not synchronised with the VBL, so the game loop's VBL phase does not bias it). Test runs only. */
extern u16 *prof_hist_ptr; extern u32 prof_base, prof_limit, prof_total_a, prof_other_a;
extern char _start[], timera_prof[];
#define PROF_SHIFT 6
static u32 prof_n;
u32 game_cycles; static u32 prof_cycles0;
long Xbtimer(int timer, int control, int data, void *vec);
void prof_reset(void) {
    if (!prof_hist_ptr) {
        prof_n = (((u32)prog_end - (u32)_start) >> PROF_SHIFT) + 1;
        prof_hist_ptr = mem_alloc(prof_n * 2, 0x10000);
        prof_base = (u32)_start; prof_limit = (u32)prog_end - (u32)_start;
        Xbtimer(0, 7, 11, timera_prof);           /* timer A: 2457600 / 200 / 11 = 1117 Hz */
    } else memset(prof_hist_ptr, 0, prof_n * 2);
    prof_total_a = prof_other_a = 0; prof_cycles0 = game_cycles;
}
void prof_report(void) {
    u32 total = prof_total_a; if (!prof_hist_ptr || !total) return;
    u16 *hist = mem_alloc(prof_n * 2, 0); if (!hist) return;
    memcpy(hist, prof_hist_ptr, prof_n * 2);
    dbg("profile: %d samples (%d s), %d outside the program (TOS), %d game cycles = %d.%d per second\n", total, total / 1117,
        prof_other_a, game_cycles - prof_cycles0, (game_cycles - prof_cycles0) * 1117 / total, (game_cycles - prof_cycles0) * 11170 / total % 10);
    for (int k = 0; k < 400; k++) {
        u32 best = 0;
        for (u32 i = 1; i < prof_n; i++) if (hist[i] > hist[best]) best = i;
        if (!hist[best]) break;
        u32 a = (u32)_start + (best << PROF_SHIFT);
        dbg("  prof $%x %H %d\n", a, a, hist[best]);
        hist[best] = 0;
    }
    mem_free(hist, prof_n * 2);
}
void vbl_hook(void) { }

/* ---- start-up ------------------------------------------------------------------------- */
extern char exc_2[], exc_3[], exc_4[], exc_5[], exc_6[], exc_7[], exc_8[], exc_10[], exc_11[], trap5_handler[];

static char prog_stack[48 * 1024];
static u32 the_lock;

struct LoaderMsg *loader_msg;

int shim_main(void *bp) {
    (void)bp;
    extern char nf_illegal[];
    long old_illegal = Setexc(4, nf_illegal);   /* NatFeats opcodes are illegal without Hatari */
    nf_init();
    Setexc(4, (void *)old_illegal);
    dbg("KQ5 TOS shim starting; Prog at $%x..$%x\n", (u32)hunk0, (u32)prog_end);
    static const int vecs[] = { 2, 3, 4, 5, 6, 7, 8, 10, 11 };
    void *hs[] = { exc_2, exc_3, exc_4, exc_5, exc_6, exc_7, exc_8, exc_10, exc_11 };
    long old_vecs[10];
    for (int i = 0; i < 9; i++) old_vecs[i] = Setexc(vecs[i], hs[i]);
    old_vecs[9] = Setexc(32 + 5, trap5_handler);

    mem_init();
    Supexec(install_sampler);
    exec_init();
    dos_init();
    display_init();
    input_init();
    { long h = Fopen("KTRACE", 0); if (h >= 0) { Fclose(h); ktrace_on = 1; dbg("kernel trace on\n"); } }
    void blitter_init(void); blitter_init();
    the_lock = dos_lock_dir("");

    /* Prepare the loader message; it is queued when Prog creates "SCIport". */
    loader_msg = mem_alloc(sizeof *loader_msg, 0x10001);
    loader_msg->msg.node.name = "heyyou";
    loader_msg->msg.length = sizeof *loader_msg;
    loader_msg->dirlock = the_lock;
    loader_msg->reserve = mem_alloc(0x2f9b8, 1);
    loader_msg->heap_n = 0x36da6;
    loader_msg->heap = mem_alloc(loader_msg->heap_n, 1);

    long rc = run_prog(hunk0, prog_stack + sizeof prog_stack, sizeof prog_stack - 8);
    dbg("Prog returned %d\n", rc);
    /* Back to the desktop: undo everything that points into this program or changed the
     * machine (on a real ST a leftover vector halted the CPU right after Pterm). */
    Supexec(remove_interrupts);
    Supexec(ym_silence);
    input_restore();
    display_restore();
    for (int i = 0; i < 9; i++) Setexc(vecs[i], (void *)old_vecs[i]);
    Setexc(32 + 5, (void *)old_vecs[9]);
    nf_exit(rc);
    return rc;
}
