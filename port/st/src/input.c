/* ST mouse/keyboard -> SCI events.
 *
 * On the Amiga, "FerretTask" turns IDCMP messages into SCI events and keeps the mouse position and
 * button flag up to date asynchronously; SCI's button tracking reads those globals in a loop
 * without fetching events. The shim splits that work:
 *   - interrupt time (VBL, IKBD): mouse position/button globals in Prog and in the window are kept
 *     current; button transitions and autoplay events go into a small lock-free ring;
 *   - main time (hunk 16 +$160, called by GetEvent): the ring is drained into SCI's event
 *     queue with Prog's own post function (hunk 14 +$1a4).
 * The keyboard: TOS only reports key presses (Bconin), never releases, so the shim replaces TOS's
 * ikbdsys routine (XBIOS Kbdvbase) and decodes the IKBD bytes itself (glue.S ikbd_handler ->
 * ikbd_byte): mouse packets go to mouse_handler as before, keys are turned into SCI key events with
 * TOS's own key tables (Keytbl). The numeric keypad is reported the way the Amiga and DOS
 * interpreters report it: PC keypad codes ($4700 Home .. $5100 PgDn, 5 = $4c00 Center), which
 * the kernel's MapKeyToDir turns into direction events (type $44) for the game's PseudoMouse
 * (pointer movement, or walking with the walk cursor); keypad 0 = Insert ($5200, toggles the walk
 * cursor), keypad . = Delete ($5300, opens the icon bar), keypad Enter = Enter, as in the manual.
 * No joystick: IKBD joystick event reporting ($14) switches the mouse off.
 *
 * SCI event: type.w, message.w, modifiers.w, time.l, y.w, x.w */
#include "amiga.h"

struct SciEvent { u16 type, message, modifiers; u32 time; s16 y, x; } PACKED;
#define EV_MOUSEDOWN 1
#define EV_MOUSEUP   2
#define EV_KEYDOWN   4
#define EV_DIRECTION 0x40

#define A4G(a4, off, type) (*(type *)((a4) - (off)))
#define G_MOUSEX    0x6e62
#define G_MOUSEY    0x6e64
#define G_MODIFIERS 0x575a
#define G_TICKS     0x7128
#define G_WINDOW    0x5974
#define G_BUTTON    0x6e60   /* left button held (maintained by FerretTask on the Amiga) */

extern char hunk14[];
extern volatile u32 vbl_count;
long call_prog1(void *fn, u32 a4, void *arg);
long Kbshift(int mode);
void **Kbdvbase(void);
void **Keytbl(long unshift, long shift, long caps);
extern void ikbd_handler(void);
extern void mouse_packet(const u8 *pkt);
void nf_exit(long code);
extern void mouse_handler(void);
extern volatile s16 mouse_x, mouse_y;
extern volatile u8 mouse_buttons;

static void *old_mousevec;
void *old_ikbdsys;                      /* also used by ikbd_handler (glue.S) */
static volatile u32 prog_a4;            /* Prog's A4, known after the first poll */
static volatile u8 auto_buttons;        /* buttons held by the autoplay script */
static volatile s16 cur_mods;

/* ---- pending events: produced at interrupt time, consumed by the poll ------------------------- */
struct Pending { u16 type, message, modifiers; s16 x, y; };
static struct Pending ring[32];
static volatile u8 ring_head, ring_tail;

static void queue_event(int type, int message, int mods) {
    u16 sr;                                             /* producers: VBL and IKBD interrupts */
    __asm__ volatile("move.w %%sr,%0\n\tori.w #0x700,%%sr" : "=d"(sr) : : "memory");
    u8 t = ring_tail, n = (t + 1) & 31;
    if (n != ring_head) {                               /* full: drop */
        ring[t] = (struct Pending){ type, message, mods, mouse_x, mouse_y };
        ring_tail = n;
    }
    __asm__ volatile("move.w %0,%%sr" : : "d"(sr) : "memory");
}

/* Double-click: a second left-button press within DBL_TICKS VBLs and DBL_DIST pixels of the
 * previous one gets modifier bit DBLCLICK (unused by SCI); the patched Ego::handleEvent
 * (tools/makescr.py) then walks Graham to the spot in one go. */
#define DBLCLICK  0x80
#define DBL_TICKS 25
#define DBL_DIST  4
static u32 last_down; static s16 last_dx, last_dy;
static int double_click(void) {
    u32 now = vbl_count; int dbl = 0;
    int dx = mouse_x - last_dx, dy = mouse_y - last_dy;
    if (last_down && now - last_down <= DBL_TICKS && dx <= DBL_DIST && dx >= -DBL_DIST && dy <= DBL_DIST && dy >= -DBL_DIST) dbl = 1;
    last_down = dbl ? 0 : now; last_dx = mouse_x; last_dy = mouse_y;
    return dbl;
}

/* Called from the IKBD mouse handler (glue.S) when the button bits change. Both buttons held
 * together = Esc (bit 1 left, bit 0 right): skips the Sierra fanfare / title song (script patch in
 * tools/makescr.py) and otherwise does what Esc does (opens the icon bar). */
void mouse_buttons_changed(u8 old, u8 new) {
    int mods = cur_mods;
    if ((new & 3) == 3 && (old & 3) != 3) queue_event(EV_KEYDOWN, 27, mods);
    if ((new & 2) && !(old & 2)) queue_event(EV_MOUSEDOWN, 0, mods | (double_click() ? DBLCLICK : 0));
    if (!(new & 2) && (old & 2)) queue_event(EV_MOUSEUP, 0, mods);
    if ((new & 1) && !(old & 1)) queue_event(EV_MOUSEDOWN, 0, mods | 3);     /* right = shift-click */
    if (!(new & 1) && (old & 1)) queue_event(EV_MOUSEUP, 0, mods | 3);
}

/* Keep Prog's view of the mouse current (what FerretTask/IDCMP did on the Amiga). */
static void update_mouse_globals(void) {
    u32 a4 = prog_a4;
    if (!a4) return;
    A4G(a4, G_MOUSEX, s16) = mouse_x;
    A4G(a4, G_MOUSEY, s16) = mouse_y;
    A4G(a4, G_BUTTON, s16) = ((mouse_buttons | auto_buttons) & 2) ? 1 : 0;
    u8 *win = A4G(a4, G_WINDOW, u8 *);
    if (win) { *(s16 *)(win + 0xc) = mouse_y; *(s16 *)(win + 0xe) = mouse_x; }
}

/* ST scancode -> SCI (PC) key code for keys without ASCII */
static int special_key(int scan) {
    switch (scan) {
    case 0x48: case 0x50: case 0x4b: case 0x4d: case 0x47: case 0x52: case 0x53:
        return scan << 8;                                  /* arrows, Clr/Home, Insert, Delete */
    case 0x61: return 27;                                  /* Undo -> Esc */
    case 0x62: return 0x3b00;                              /* Help -> F1 */
    case 0x70: return 0x5200;                              /* keypad 0 -> Insert */
    case 0x71: return 0x5300;                              /* keypad . -> Delete */
    }
    if (scan >= 0x67 && scan <= 0x6f) {                    /* keypad 7 8 9 / 4 5 6 / 1 2 3 -> PC keypad codes */
        static const u8 pc[9] = { 0x47, 0x48, 0x49, 0x4b, 0x4c, 0x4d, 0x4f, 0x50, 0x51 };
        return pc[scan - 0x67] << 8;
    }
    if ((scan >= 0x3b && scan <= 0x44) || (scan >= 0x54 && scan <= 0x5d)) return scan << 8;   /* (shift-)F1-F10 */
    return 0;
}


/* ---- IKBD bytes (interrupt time, from ikbd_handler in glue.S) ---------------------------------- */
#define REP_DELAY  25                   /* key repeat: first after 0.5 s, then every 6 VBLs */
#define REP_PERIOD 6
static u8 pkt_left, pkt_n, pkt[8];      /* IKBD packet being collected */
static u8 shift_state;                  /* bits as Kbshift: 0 rshift, 1 lshift, 2 ctrl, 3 alt, 4 caps */
static u8 rep_scan; static u32 rep_t;   /* key being repeated and when it fires next */
static u8 **keytab;                     /* TOS key tables: unshifted, shifted, caps lock */

static void post_key(int scan) {
    int code = special_key(scan);
    if (!code && keytab) {
        u8 *t = (shift_state & 3) ? keytab[1] : (shift_state & 0x10) ? keytab[2] : keytab[0];
        code = t[scan];
        if ((shift_state & 4) && (code | 0x20) >= 'a' && (code | 0x20) <= 'z') code &= 0x1f;   /* ctrl-letter */
    }
    if (code) queue_event(EV_KEYDOWN, code, cur_mods);
}

static void key_byte(int b) {
    int scan = b & 0x7f, make = !(b & 0x80);
    int bit = scan == 0x36 ? 1 : scan == 0x2a ? 2 : scan == 0x1d ? 4 : scan == 0x38 ? 8 : 0;
    if (bit) { shift_state = make ? shift_state | bit : shift_state & ~bit; cur_mods = shift_state & 0x0f; return; }
    if (scan == 0x3a) { if (make) shift_state ^= 0x10; return; }
    if (make) { rep_scan = scan; rep_t = vbl_count + REP_DELAY; post_key(scan); }
    else if (scan == rep_scan) rep_scan = 0;
}

/* Replacement for TOS's ikbdsys state machine: headers $f6.. start a packet of a known length,
 * everything else is a key make/break code. Only relative mouse packets ($f8-$fb) are used. */
void ikbd_byte(int b) {
    if (pkt_left) {
        pkt[pkt_n++] = b;
        if (--pkt_left == 0 && pkt[0] >= 0xf8 && pkt[0] <= 0xfb) mouse_packet(pkt);
        return;
    }
    if (b >= 0xf6) {
        static const u8 len[10] = { 7, 5, 2, 2, 2, 2, 6, 2, 1, 1 };    /* status, abs mouse, rel mouse x4, clock, joysticks, joy0, joy1 */
        pkt_left = len[b - 0xf6]; pkt[0] = b; pkt_n = 1;
        return;
    }
    key_byte(b);
}

static void key_repeat(void) {
    if (rep_scan && (s32)(vbl_count - rep_t) >= 0) { rep_t = vbl_count + REP_PERIOD; post_key(rep_scan); }
}

/* ---- test automation: C:\AUTO.TXT, run at interrupt time --------------------------------------
 * "<vbl> click x y" | "<vbl> rclick x y" | "<vbl> press x y" | "<vbl> release" | "<vbl> move x y" |
 * "<vbl> key code" | "<vbl> dir n" | "<vbl> ikbd byte" (raw IKBD byte, e.g. $68 = keypad 8 down,
 * $e8 up) | "<vbl> shot" | "<vbl> quit"      (vbl = VBLs since start-up, "#" comments) */
int autoplay_active;
static char auto_buf[4096]; static char *auto_p; static u32 auto_t0;
static volatile u8 shot_request, quit_request, prof_request;

static int parse_num(char **pp) {
    char *p = *pp; int v = 0, neg = 0;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '-') neg = 1, p++;
    if (*p == '$') {
        for (p++;; p++) {
            int c = *p, d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (d < 0) break;
            v = v * 16 + d;
        }
    } else while (*p >= '0' && *p <= '9') v = v * 10 + *p++ - '0';
    *pp = p; return neg ? -v : v;
}

static void auto_load(void) {
    long h = Fopen("AUTO.TXT", 0);
    if (h < 0) return;
    long n = Fread(h, sizeof auto_buf - 1, auto_buf); Fclose(h);
    if (n <= 0) return;
    auto_buf[n] = 0; auto_p = auto_buf; auto_t0 = vbl_count; autoplay_active = 1;
    dbg("autoplay script loaded (%d bytes)\n", n);
}

static void auto_step(void) {
    while (auto_p && *auto_p) {
        char *p = auto_p;
        while (*p == '\n' || *p == '\r' || *p == ' ') p++;
        if (*p == '#') { while (*p && *p != '\n') p++; auto_p = p; continue; }
        if (!*p) { auto_p = 0; return; }
        u32 t = parse_num(&p);
        if (vbl_count - auto_t0 < t) return;
        while (*p == ' ') p++;
        char cmd[12]; int n = 0; while (*p > ' ' && n < 11) cmd[n++] = *p++; cmd[n] = 0;
        int mods = cur_mods;
        if (!strcmp(cmd, "move")) { mouse_x = parse_num(&p); mouse_y = parse_num(&p); }
        else if (!strcmp(cmd, "press")) { mouse_x = parse_num(&p); mouse_y = parse_num(&p); auto_buttons = 2; queue_event(EV_MOUSEDOWN, 0, mods); }
        else if (!strcmp(cmd, "release")) { auto_buttons = 0; queue_event(EV_MOUSEUP, 0, mods); }
        else if (!strcmp(cmd, "click") || !strcmp(cmd, "rclick")) {
            mouse_x = parse_num(&p); mouse_y = parse_num(&p);
            int m = cmd[0] == 'r' ? mods | 3 : mods;
            queue_event(EV_MOUSEDOWN, 0, m); queue_event(EV_MOUSEUP, 0, m);
        } else if (!strcmp(cmd, "dclick")) {
            mouse_x = parse_num(&p); mouse_y = parse_num(&p);
            queue_event(EV_MOUSEDOWN, 0, mods | DBLCLICK); queue_event(EV_MOUSEUP, 0, mods);
        } else if (!strcmp(cmd, "key")) queue_event(EV_KEYDOWN, parse_num(&p), mods);
        else if (!strcmp(cmd, "dir")) queue_event(EV_DIRECTION, parse_num(&p), mods);
        else if (!strcmp(cmd, "ikbd")) ikbd_byte(parse_num(&p) & 0xff);
        else if (!strcmp(cmd, "shot")) shot_request = 1;
        else if (!strcmp(cmd, "prof")) prof_request = 1;
        else if (!strcmp(cmd, "profreset")) prof_request = 2;
        else if (!strcmp(cmd, "quit")) quit_request = 1;
        while (*p && *p != '\n') p++;
        auto_p = p;
    }
}

/* VBL (interrupt time) */
void input_vbl(void) {
    auto_step();
    key_repeat();
    update_mouse_globals();
}

void input_init(void) {
    auto_load();
    keytab = (u8 **)Keytbl(-1, -1, -1);
    shift_state = Kbshift(-1) & 0x1f; cur_mods = shift_state & 0x0f;
    void **kv = Kbdvbase();
    old_mousevec = kv[4]; old_ikbdsys = kv[8];
    kv[4] = (void *)mouse_handler;
    kv[8] = (void *)ikbd_handler;
    mouse_x = 160; mouse_y = 100;
}

void input_restore(void) {
    void **kv = Kbdvbase();
    if (old_mousevec) kv[4] = old_mousevec;
    if (old_ikbdsys) kv[8] = old_ikbdsys;
}

/* ---- main time ------------------------------------------------------------------------------ */
static void post(u32 a4, int type, int message, int mods, int x, int y) {
    struct SciEvent ev = { type, message, mods, A4G(a4, G_TICKS, u32), y, x };
    dbg("event vbl %d type %d msg %d mods $%x at %d,%d\n", (int)vbl_count, type, message, mods, x, y);
    call_prog1(hunk14 + 0x1a4, a4, &ev);
}

/* Replacement for hunk 16 +$160 (joystick poll), called at the start of SCI's GetEvent
 * (hunk 14 +$58: C function GetEvent(mask, event), so a5 is still its frame and the mask is at
 * 8(a5)). Only the pending events GetEvent asks for are posted; the others stay in the ring for a
 * later call. Prog's GetEvent drops the event at the head of its queue whenever a later event
 * matches the mask, and Game::newRoom flushes mouse events with mask 3 after a room change (for
 * seconds, while the new room loads): an Esc queued before a click would be lost there. */
void c_input_poll(struct regs *r) {
    u32 a4 = r->a[4];
    int mask = *(s16 *)(r->a[5] + 8);
    prog_a4 = a4;
    extern u32 game_cycles; game_cycles++;
    display_poll();
    A4G(a4, G_MODIFIERS, s16) = cur_mods;                   /* same bit order as SCI */
    update_mouse_globals();
    struct Pending keep[32]; int nkeep = 0;
    while (ring_head != ring_tail) {
        struct Pending e = ring[ring_head];
        ring_head = (ring_head + 1) & 31;
        if (e.type & mask) post(a4, e.type, e.message, e.modifiers, e.x, e.y);
        else keep[nkeep++] = e;
    }
    for (int i = 0; i < nkeep; i++) {                       /* back into the ring, in order */
        u16 sr;
        __asm__ volatile("move.w %%sr,%0\n\tori.w #0x700,%%sr" : "=d"(sr) : : "memory");
        u8 t = ring_tail, n = (t + 1) & 31;
        if (n != ring_head) { ring[t] = keep[i]; ring_tail = n; }
        __asm__ volatile("move.w %0,%%sr" : : "d"(sr) : "memory");
    }
    if (shot_request) { shot_request = 0; display_shot(); }
    if (prof_request) { void prof_report(void), prof_reset(void); if (prof_request == 1) prof_report(); prof_reset(); prof_request = 0; }
    if (quit_request) { display_shot(); nf_exit(0); }
}

/* kSetCursor with a position (hunk 17 +$aa..+$17f): the Amiga sends a pointer-position event
 * through input.device; on the ST we move the shim's pointer. Args (a5+8): count, view, ?, x, y;
 * coordinates are relative to the current port (port +6 top, +8 left). */
void c_setcursor(struct regs *r) {
    u32 a4 = r->a[4];
    s16 *args = *(s16 **)(r->a[5] + 8);
    u8 *port = A4G(a4, 0x7154, u8 *);
    int x = *(s16 *)(port + 8) + args[3], y = *(s16 *)(port + 6) + args[4];
    mouse_x = x < 0 ? 0 : x > 319 ? 319 : x;
    mouse_y = y < 0 ? 0 : y > 199 ? 199 : y;
    update_mouse_globals();
}
