/* YM2149 SCI sound driver: the 18-function interface of amiga3v.drv (Sierra's SCI1 "3-voice"
 * driver: PCjr/Tandy tracks, device $13, patch 101), playing the three square-wave tone
 * generators of the ST's sound chip. Logic mirrors amiga3v.drv (see docs/SOUND.md): the
 * interpreter sequences the MIDI data and calls us with NoteOn/NoteOff/Controller/... plus
 * Service once per tick (from the VERTB server, i.e. our VBL).
 *
 * Entry: seglist+4 = "jmp stub_YmDriver" (LVO stub: all registers saved, c_YmDriver(regs)).
 *   d7 = function, arguments in d0/d1/a0, results in d0/d1.
 *   0 GetDeviceInfo  d0 = $0001_0065 (patch 101), d1 = $0013_0003 (device $13, 3 voices)
 *   1 Init           a0 = patch 101 data or NULL; d0 = $000f_0000 (max volume 15), d1 = 0 ok
 *   2 Terminate      3 Service(tick)   4 NoteOff(ch, note|vel<<16)   5 NoteOn(ch, note|vel<<16)
 *   6 -   7 Controller(ch, ctl|val<<16)   8 ProgramChange(ch, prog)   9 -   10 PitchBend(ch, lsb|msb<<16)
 *   11 Reverb(get $ff/set)   12 MasterVol(get $ff/set 0-15)   13 SoundOn(get $ff/set)   14-16 -
 *   17 AskDriver(cmd<<16|ch, ...) -> value or -1 */
#include "amiga.h"

#define R struct regs *r
#define NV 3                       /* YM tone channels A, B, C */
/* Voices announced to the interpreter. amiga3v.drv says 4; the interpreter maps a sound's channels
 * only while this budget lasts and leaves a sound that does not fit silent (sound 500, the Sierra
 * logo, asks 1+2+1). Announcing 4 with 3 real voices means a channel can be short of one; see
 * add_voices(). */
#define REPORT_VOICES 4
#define NCH 16

/* channel state (indexed by MIDI channel) */
static u8  ch_prog[NCH], ch_vol[NCH], ch_hold[NCH], ch_owed[NCH], ch_last[NCH];
static u16 ch_bend[NCH];
/* voice state */
static u8  v_ch[NV], v_note[NV], v_sus[NV], v_rel[NV], v_envpos[NV], v_envcnt[NV], v_envvol[NV], v_vel[NV];
static u16 v_age[NV], v_relage[NV], v_envoff[NV];
static u8  reverb, sound_on;
static u16 master;

/* patch 101: 128 instrument offsets + envelope strings (pairs volume,ticks; ticks $fe = hold
 * until released; volume $ff = end). Default when no patch: every instrument = "15, hold". */
#define ENVMAX 1024
static u16 inst_off[128];
static u8  envdata[ENVMAX];
static int have_patch;

/* --- hardware ------------------------------------------------------------------------------ */
#define YM_SEL  (*(volatile u8 *)0xffff8800)
#define YM_DATA (*(volatile u8 *)0xffff8802)

static u16 hw_period[NV], hw_level[NV];   /* shadows: write only on change */
static u8  hw_mixer;                      /* bits 0-2: tone off flags; bits 6-7 kept from TOS */

static inline u16 int_off(void) { u16 sr; __asm__ volatile("move.w %%sr,%0\n\tor.w #0x700,%%sr" : "=d"(sr) : : "memory"); return sr; }
static inline void int_on(u16 sr) { __asm__ volatile("move.w %0,%%sr" : : "d"(sr) : "memory"); }
static inline void ym_write(u8 reg, u8 val) { YM_SEL = reg; YM_DATA = val; }

static void hw_init(void) {
    u16 sr = int_off();
    YM_SEL = 7; hw_mixer = (YM_SEL & 0xc0) | 0x3f;        /* keep the I/O port directions, all off */
    ym_write(7, hw_mixer);
    for (int v = 0; v < NV; v++) { ym_write(8 + v, 0); hw_level[v] = 0; hw_period[v] = 0; }
    int_on(sr);
}

/* level 0 = silent (tone disabled too) */
static void hw_voice(int v, u16 period, u8 level) {
    u8 mixer = level ? (hw_mixer & ~(1 << v)) : (hw_mixer | (1 << v));
    u16 sr = int_off();
    if (period != hw_period[v]) { hw_period[v] = period; ym_write(2 * v, period & 0xff); ym_write(2 * v + 1, period >> 8); }
    if (level != hw_level[v])   { hw_level[v] = level; ym_write(8 + v, level); }
    if (mixer != hw_mixer)      { hw_mixer = mixer; ym_write(7, mixer); }
    int_on(sr);
}

/* --- pitch ---------------------------------------------------------------------------------- */
/* YM tone period = 125000 / f (2 MHz / 16). Periods of the lowest octave (MIDI notes 0-11) in
 * quarter-semitone steps; higher octaves shift right. Generated with
 * round(125000 / (440 * 2 ** ((q / 4 - 69) / 12))) for q = 0..47. */
static const u16 base_period[48] = {
    15289, 15070, 14854, 14641, 14431, 14224, 14020, 13819, 13621, 13426, 13233, 13043,
    12856, 12672, 12490, 12311, 12135, 11961, 11789, 11620, 11454, 11290, 11128, 10968,
    10811, 10656, 10503, 10353, 10204, 10058, 9914, 9772, 9631, 9493, 9357, 9223,
    9091, 8961, 8832, 8705, 8581, 8458, 8336, 8217, 8099, 7983, 7869, 7756,
};

static u16 note_period(int note, u16 bend) {
    int units = bend / 168;                         /* 0..97, centre 48, as amiga3v.drv */
    int q = note * 4 + (units > 48 ? units - 49 : units - 48);
    if (q < 0) q = 0;
    if (q > 127 * 4 + 3) q = 127 * 4 + 3;
    int oct = q / 48, p = base_period[q % 48];
    if (oct) p = (p + (1 << (oct - 1))) >> oct;
    if (p > 4095) p = 4095;
    if (p < 1) p = 1;
    return p;
}

/* --- volume --------------------------------------------------------------------------------- */
/* Sierra's PCjr formula gives an SN76489 attenuation (2 dB steps); the YM's 16 levels are about
 * 3 dB apart, so the attenuation is scaled by 2/3 to keep the same loudness curve. */
static const u8 velo_tab[16] = { 1, 3, 6, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 14, 15, 15 };
static const u8 attn_to_level[16] = { 15, 14, 14, 13, 12, 12, 11, 10, 10, 9, 8, 8, 7, 6, 6, 0 };

static u8 voice_level(int v) {
    if (!sound_on) return 0;
    int cv = ch_vol[v_ch[v]];
    int vol = cv ? (cv >> 3 ? cv >> 3 : 1) : 0;
    int velo = v_vel[v] ? velo_tab[v_vel[v] >> 3] : 0;
    int tl = ((vol * velo / 15) * v_envvol[v] / 15) * master;
    if (tl > 0 && tl < 15) tl = 15;
    return attn_to_level[15 - tl / 15];
}

/* --- voices --------------------------------------------------------------------------------- */
static void voice_stop(int v) {
    v_vel[v] = 0; v_note[v] = 0xff; v_sus[v] = 0; v_rel[v] = 0;
    v_envpos[v] = 0; v_envcnt[v] = 0; v_age[v] = 0; v_relage[v] = 0;
    hw_voice(v, hw_period[v], 0);
}

static void voice_start(int v, u8 note, u8 vel) {
    v_note[v] = note; v_rel[v] = 0; v_sus[v] = 0;
    v_envpos[v] = 0; v_envcnt[v] = 0; v_envvol[v] = 0; v_age[v] = 0; v_relage[v] = 0;
    v_envoff[v] = inst_off[ch_prog[v_ch[v]] & 127];
    v_vel[v] = vel;
    hw_voice(v, note_period(note, ch_bend[v_ch[v]]), 0);   /* audible after the first tick's envelope step */
}

/* round-robin voice of the channel: a free one, else the oldest (released voices first) */
static int voice_alloc(int ch) {
    int v = ch_last[ch], best = -1;
    u16 bestkey = 0;
    for (int n = 0; n < NV; n++) {
        v = (v + 1) % NV;
        if (v_ch[v] != ch) continue;
        if (v_note[v] == 0xff) { ch_last[ch] = v; return v; }
        u16 key = v_relage[v] ? 0x8000 + v_relage[v] : v_age[v];
        if (key >= bestkey) { bestkey = key; best = v; }
    }
    if (best >= 0) voice_stop(best);
    ch_last[ch] = best >= 0 ? best : 0;
    return best;
}

/* Fair share (not in amiga3v.drv): a channel that would get no voice at all takes one from a
 * channel holding two or more, its silent voice if it has one, else its oldest. */
static int voice_steal_for(int ch) {
    int count[NCH] = {0};
    for (int v = 0; v < NV; v++) if (v_ch[v] != 0xff) count[v_ch[v]]++;
    int rich = -1;
    for (int c = 0; c < NCH; c++) if (count[c] >= 2 && (rich < 0 || count[c] > count[rich])) rich = c;
    if (rich < 0) return -1;
    int best = -1; u16 bestkey = 0;
    for (int v = 0; v < NV; v++) {
        if (v_ch[v] != rich) continue;
        if (v_note[v] == 0xff) { best = v; break; }
        u16 key = v_relage[v] ? 0x8000 + v_relage[v] : v_age[v];
        if (key >= bestkey) { bestkey = key; best = v; }
    }
    voice_stop(best); v_ch[best] = ch;
    ch_owed[rich]++;
    return best;
}

static void add_voices(int ch, int n) {
    for (int v = 0; v < NV && n; v++)
        if (v_ch[v] == 0xff) { v_ch[v] = ch; if (v_note[v] != 0xff) voice_stop(v); n--; }
    if (n) {
        int have = 0;
        for (int v = 0; v < NV; v++) if (v_ch[v] == ch) have++;
        if (!have && voice_steal_for(ch) >= 0) n--;
    }
    ch_owed[ch] += n;
}

static void remove_voices(int ch, int n) {
    if (ch_owed[ch] >= n) { ch_owed[ch] -= n; return; }
    n -= ch_owed[ch]; ch_owed[ch] = 0;
    for (int v = 0; v < NV && n; v++)
        if (v_ch[v] == ch && v_note[v] == 0xff) { v_ch[v] = 0xff; n--; }
    while (n) {
        int best = -1; u16 bestkey = 0;
        for (int v = 0; v < NV; v++) {
            if (v_ch[v] != ch) continue;
            u16 key = v_relage[v] ? 0x8000 + v_relage[v] : v_age[v];
            if (key >= bestkey) { bestkey = key; best = v; }
        }
        if (best < 0) break;
        voice_stop(best); v_ch[best] = 0xff; n--;
    }
}

/* hand free voices to channels that asked for more than were available */
static void redistribute(void) {
    int free = 0;
    for (int v = 0; v < NV; v++) if (v_ch[v] == 0xff) free++;
    for (int ch = 0; ch < NCH && free; ch++) {
        int owed = ch_owed[ch];
        if (!owed) continue;
        if (owed < free) { free -= owed; ch_owed[ch] = 0; add_voices(ch, owed); }
        else { ch_owed[ch] = owed - free; add_voices(ch, free); return; }
    }
}

static void set_voices(int ch, int n) {
    int have = ch_owed[ch];
    for (int v = 0; v < NV; v++) if (v_ch[v] == ch) have++;
    if (n > have) add_voices(ch, n - have);
    else if (n < have) { remove_voices(ch, have - n); redistribute(); }
}

/* --- MIDI ----------------------------------------------------------------------------------- */
static void note_off(int ch, u8 note) {
    for (int v = 0; v < NV; v++)
        if (v_ch[v] == ch && v_note[v] == note) { if (ch_hold[ch]) v_sus[v] = 1; else v_rel[v] = 1; return; }
}

static void note_on(int ch, u8 note, u8 vel) {
    if (!vel) { note_off(ch, note); return; }
    for (int v = 0; v < NV; v++)
        if (v_ch[v] == ch && v_note[v] == note) { v_sus[v] = 0; voice_stop(v); voice_start(v, note, vel); return; }
    int v = voice_alloc(ch);
    if (v >= 0) voice_start(v, note, vel);
}

static void controller(int ch, u8 ctl, u8 val) {
    switch (ctl) {
    case 7: ch_vol[ch] = val; break;
    case 0x40:
        ch_hold[ch] = val;
        if (!val) for (int v = 0; v < NV; v++) if (v_ch[v] == ch && v_sus[v]) { v_sus[v] = 0; v_rel[v] = 1; }
        break;
    case 0x4b: set_voices(ch, val); break;
    case 0x7b: for (int v = 0; v < NV; v++) if (v_ch[v] == ch && v_note[v] != 0xff) voice_stop(v); break;
    }
}

static void pitch_bend(int ch, u8 lsb, u8 msb) {
    ch_bend[ch] = ((msb & 0x7f) << 7) | (lsb & 0x7f);
    for (int v = 0; v < NV; v++)
        if (v_ch[v] == ch && v_note[v] != 0xff) hw_voice(v, note_period(v_note[v], ch_bend[ch]), hw_level[v]);
}

static void envelope(int v) {
    if (v_envcnt[v] == 0xfe) { if (!v_rel[v]) return; v_envcnt[v] = 0; }
    else if (v_envcnt[v]) { v_envcnt[v]--; return; }
    int p = v_envoff[v] + v_envpos[v];
    if (p + 1 >= ENVMAX) { voice_stop(v); return; }
    u8 vol = envdata[p], dur = envdata[p + 1];
    if (vol == 0xff) { voice_stop(v); return; }     /* note: voice_stop() resets envpos */
    v_envpos[v] += 2; v_envcnt[v] = dur; v_envvol[v] = vol;
}

static void service(void) {
    for (int v = 0; v < NV; v++) {
        if (v_note[v] == 0xff) continue;
        v_age[v]++;
        if (v_rel[v]) v_relage[v]++;
        envelope(v);
        if (v_note[v] != 0xff) hw_voice(v, hw_period[v], voice_level(v));
    }
}

static void refresh_levels(void) {
    for (int v = 0; v < NV; v++) if (v_note[v] != 0xff) hw_voice(v, hw_period[v], voice_level(v));
}

/* --- init ----------------------------------------------------------------------------------- */
static void load_patch(const u8 *p) {
    have_patch = 0;
    for (int i = 0; i < 128; i++) inst_off[i] = 0;
    envdata[0] = 15; envdata[1] = 0xfe; envdata[2] = 0xff;        /* default instrument */
    if (!p) return;
    /* 128 little-endian word offsets (relative to the start of the patch), then the envelopes */
    for (int i = 0; i < 128; i++) inst_off[i] = p[2 * i] | (p[2 * i + 1] << 8);
    int n = 0, strings = 0;
    while (n < ENVMAX - 256 && strings < 40) { envdata[256 + n] = p[256 + n]; if (p[256 + n] == 0xff) strings++; n++; }
    for (int i = 0; i < 128; i++) if (inst_off[i] < 256 || inst_off[i] >= 256 + n) inst_off[i] = 0;
    have_patch = 1;
}

static void driver_init(const u8 *patch) {
    for (int ch = 0; ch < NCH; ch++) { ch_prog[ch] = 0; ch_vol[ch] = 127; ch_hold[ch] = 0; ch_owed[ch] = 0; ch_last[ch] = 0; ch_bend[ch] = 0x2000; }
    for (int v = 0; v < NV; v++) { v_ch[v] = 0xff; v_note[v] = 0xff; v_sus[v] = v_rel[v] = 0; v_envpos[v] = v_envcnt[v] = v_envvol[v] = v_vel[v] = 0; v_age[v] = v_relage[v] = v_envoff[v] = 0; }
    reverb = 0; sound_on = 1; master = 15;
    load_patch(patch);
    hw_init();
    dbg("ym driver: init, patch 101 %s\n", have_patch ? "loaded" : "missing (default envelope)");
}

static u32 ask_driver(u32 d0, u32 d1) {
    int ch = d0 & 15, cmd = d0 >> 16, ctl = d1 >> 16;
    switch (cmd) {
    case 0xe0: return ch_bend[ch];
    case 0xc0: return ch_prog[ch];
    case 0xb0:
        if (ctl == 7) return ch_vol[ch];
        if (ctl == 0x40) return ch_hold[ch];
        if (ctl == 0x4b) {
            if ((d1 & 0xffff) != 0xff) return ch_owed[ch];
            int n = 0; for (int v = 0; v < NV; v++) if (v_ch[v] == ch) n++;
            return n;
        }
        break;
    }
    return 0xffff;
}

/* YM_TRACE 1: log every call except Service/AskDriver (with the VBL count) to find out what the
 * interpreter sends; see docs/SOUND.md for the event format. */
#define YM_TRACE 0
extern volatile u32 vbl_count;
void c_YmDriver(R) {
    u32 d0 = r->d[0], d1 = r->d[1];
    int ch = d0 & 15;
    int f = r->d[7] & 0xffff;
    if (YM_TRACE && f != 3 && f != 17) dbg("ym %d: f%d d0=%x d1=%x\n", vbl_count, f, d0, d1);
    switch (r->d[7] & 0xffff) {
    case 0:  r->d[0] = 0x00010065; r->d[1] = 0x00130000 | REPORT_VOICES; break;
    case 1:  driver_init((const u8 *)r->a[0]); r->d[0] = 0x000f0000; r->d[1] = 0; break;
    case 2:  for (int v = 0; v < NV; v++) voice_stop(v); hw_init(); break;
    case 3:  service(); break;
    case 4:  note_off(ch, d1 & 0x7f); break;
    case 5:  note_on(ch, d1 & 0x7f, (d1 >> 16) & 0x7f); break;
    case 7:  controller(ch, d1 & 0xff, (d1 >> 16) & 0x7f); break;
    case 8:  ch_prog[ch] = d1 & 0x7f; break;
    case 10: pitch_bend(ch, d1 & 0xff, (d1 >> 16) & 0xff); break;
    case 11: if ((d0 & 0xff) == 0xff) r->d[0] = reverb; else reverb = d0; break;
    case 12: if ((d0 & 0xffff) == 0xff) r->d[0] = master; else { master = d0 & 15; refresh_levels(); } break;
    case 13: if ((d0 & 0xff) == 0xff) r->d[0] = sound_on; else { sound_on = (d0 & 0xff) != 0; refresh_levels(); } break;
    case 17: r->d[0] = ask_driver(d0, d1); break;
    default: break;                                  /* 6, 9, 14, 15, 16: nothing */
    }
}

/* The segment LoadSeg("*.drv") returns: next segment (BPTR 0), then "jmp stub_YmDriver". */
void stub_YmDriver(void);
struct ymseg { u32 next; u16 jmp; void (*addr)(void); } PACKED;
struct ymseg ym_seg __attribute__((aligned(4))) = { 0, 0x4ef9, stub_YmDriver };
