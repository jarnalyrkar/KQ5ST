/* Roland MT-32 SCI sound driver for the ST's MIDI port (2026-11-07, docs/SOUND.md "MT-32").
 * Same 18-function interface as ym.c (amiga3v.drv), but announcing device $0C and patch 1, so the
 * interpreter plays the MT-32 tracks of the sound resources (241 of 244 have one) and passes us
 * the MIDI events, which go to the MIDI ACIA nearly unchanged. Selected by a file MT32 in the game
 * folder (dos.c c_LoadSeg). Works with MT-32, CM-32L/CM-64 and Munt; not with GM-only modules.
 *
 * Init uploads patch 1 (Sierra's MT-32 set-up: display texts, patch memory, 64 timbres, rhythm
 * key map, partial reserve) as Roland SysEx, following ScummVM's MidiPlayer_Midi::readMt32Patch
 * for SCI1. That takes ~17 KB at 31250 baud plus a pause after each message (~6-8 s once, at
 * start-up, with "<--Sierra On-Line-->" on the MT-32 display).
 *
 * Output is written straight to the ACIA (busy-wait on TDRE, 320 us per byte) with running
 * status; the driver is called from Prog's tick server (our VBL) and from the main program, never
 * nested (Prog's busy counter -$6e8e), so no locking is needed. */
#include "amiga.h"

#define R struct regs *r
#define NCH 16
#define REPORT_VOICES 32           /* polyphony announced to the interpreter (MT-32: 32 partials) */

#define ACIA_CTRL (*(volatile u8 *)0xfffffc04)
#define ACIA_DATA (*(volatile u8 *)0xfffffc06)

extern volatile u32 vbl_count;

static u8 ch_prog[NCH], ch_vol[NCH], ch_hold[NCH], ch_voices[NCH];
static u16 ch_bend[NCH];
static u8 master = 15, sound_on = 1, reverb, running;
static u8 reverb_cfg[11][3], have_patch;
static const u8 *goodbye;

/* --- MIDI output ---------------------------------------------------------------------------- */
static void midi_byte(u8 b) {
    for (u32 n = 0; n < 100000; n++)                 /* ~1 byte time is 320 us; give up if no ACIA */
        if (ACIA_CTRL & 2) { ACIA_DATA = b; return; }
}

static void midi_msg(u8 status, u8 d1, u8 d2, int len) {
    if (status != running) { midi_byte(status); running = status; }
    midi_byte(d1 & 0x7f);
    if (len > 2) midi_byte(d2 & 0x7f);
}

static void wait_vbls(int n) {                       /* n VBL boundaries: (n-1)*20 to n*20 ms */
    for (int i = 0; i < n; i++) { u32 v = vbl_count; for (u32 t = 0; vbl_count == v && t < 2000000; t++) ; }
}

/* Roland DT1 to the MT-32 (model $16, device $10): F0 41 10 16 12 addr(3) data checksum F7 */
static void sysex(u32 addr, const u8 *data, int len) {
    u8 a[3] = { addr >> 16, addr >> 8, addr };
    u8 sum = 0;
    running = 0;
    midi_byte(0xf0); midi_byte(0x41); midi_byte(0x10); midi_byte(0x16); midi_byte(0x12);
    for (int i = 0; i < 3; i++) { midi_byte(a[i] & 0x7f); sum += a[i] & 0x7f; }
    for (int i = 0; i < len; i++) { midi_byte(data[i] & 0x7f); sum += data[i] & 0x7f; }
    midi_byte((128 - (sum & 127)) & 127);
    midi_byte(0xf7);
    wait_vbls(2);                                    /* the MT-32 (rev 0) needs a pause after SysEx */
}

static void send_volume(int ch) {
    midi_msg(0xb0 | ch, 7, sound_on ? ch_vol[ch] * master / 15 : 0, 3);
}

static void all_notes_off(void) {
    for (int ch = 0; ch < NCH; ch++) { midi_msg(0xb0 | ch, 0x40, 0, 3); midi_msg(0xb0 | ch, 0x7b, 0, 3); }
}

static void set_reverb(int n) {
    if (n < 0 || n > 10) return;
    reverb = n;
    if (have_patch) sysex(0x100001, reverb_cfg[n], 3);
}

/* --- patch 1 (layout as in ScummVM sci/sound/drivers/midi.cpp, SCI1 branch) ------------------
 * 0 after-SysEx text (20), 20 before-SysEx text (20), 40 goodbye text (20), 60 volume (LE word),
 * 62 reverb default, 63 reverb SysEx (11, skipped), 74 reverb data 3x11 (stored by parameter),
 * 107 patches 1-48 (384), 491 timbre count, then timbres (246 each), then optionally $ABCD +
 * patches 49-96 (384), then optionally $DCBA + rhythm key map (256) + partial reserve (9). */
static void upload_patch(const u8 *p, u32 size) {
    have_patch = 0;
    if (!p || size < 492) return;
    sysex(0x200000, p + 20, 20);                     /* display: before text */
    goodbye = p + 40;
    for (int j = 0; j < 3; j++) for (int i = 0; i < 11; i++) reverb_cfg[i][j] = p[74 + j * 11 + i];
    sysex(0x050000, p + 107, 384);                   /* patch memory 1-48 */
    int nt = p[491];
    u32 o = 492;
    for (int i = 0; i < nt && o + 246 <= size; i++, o += 246)
        sysex(0x080000 + (i << 9), p + o, 246);      /* timbre memory i */
    if (o + 2 <= size && p[o] == 0xab && p[o + 1] == 0xcd && o + 2 + 384 <= size) {
        sysex(0x050300, p + o + 2, 384);             /* patch memory 49-96 */
        o += 2 + 384;
    }
    if (o + 2 <= size && p[o] == 0xdc && p[o + 1] == 0xba && o + 2 + 256 + 9 <= size) {
        sysex(0x030110, p + o + 2, 256);             /* rhythm key map */
        sysex(0x100004, p + o + 2 + 256, 9);         /* partial reserve */
    }
    sysex(0x200000, p, 20);                          /* display: after text */
    static const u8 mystery[6] = { 0x16, 0x16, 0x16, 0x16, 0x16, 0x16 };
    sysex(0x52000a, mystery, 6);                     /* sent by SCI1 MT-32 drivers (ScummVM does too) */
    have_patch = 1;
    set_reverb(p[62]);
}

/* Resource data size: Prog passes only the data pointer. Patch 1 of KQ5 is 16889 bytes; the
 * parser checks markers before reading the optional blocks, and this bound keeps it inside the
 * resource. */
#define PATCH1_SIZE 16889

static void driver_init(const u8 *patch) {
    for (int ch = 0; ch < NCH; ch++) { ch_prog[ch] = 0; ch_vol[ch] = 127; ch_hold[ch] = 0; ch_voices[ch] = 0; ch_bend[ch] = 0x2000; }
    master = 15; sound_on = 1; reverb = 0; running = 0;
    static const u8 vol100 = 100;
    upload_patch(patch, PATCH1_SIZE);
    sysex(0x100016, &vol100, 1);                     /* MT-32 master volume 100 */
    all_notes_off();
    for (int ch = 0; ch < NCH; ch++) send_volume(ch);
    dbg("mt32 driver: init, patch 1 %s\n", have_patch ? "uploaded" : "missing");
}

static void controller(int ch, int ctl, int val) {
    switch (ctl) {
    case 7:    ch_vol[ch] = val; send_volume(ch); return;
    case 0x40: ch_hold[ch] = val; break;
    case 0x4b: ch_voices[ch] = val; return;          /* SCI voice allocation: not MIDI */
    case 1: case 10: case 11: case 0x79: case 0x7b: break;
    default:   return;                               /* other SCI-specific controllers */
    }
    midi_msg(0xb0 | ch, ctl, val, 3);
}

static u32 ask_driver(u32 d0, u32 d1) {
    int ch = d0 & 15, cmd = d0 >> 16, ctl = d1 >> 16;
    switch (cmd) {
    case 0xe0: return ch_bend[ch];
    case 0xc0: return ch_prog[ch];
    case 0xb0:
        if (ctl == 7) return ch_vol[ch];
        if (ctl == 0x40) return ch_hold[ch];
        if (ctl == 0x4b) return ch_voices[ch];
        break;
    }
    return 0xffff;
}

void c_Mt32Driver(R) {
    u32 d0 = r->d[0], d1 = r->d[1];
    int ch = d0 & 15;
    switch (r->d[7] & 0xffff) {
    case 0:  r->d[0] = 0x00010001; r->d[1] = 0x000c0000 | REPORT_VOICES; break;
    /* Init's d0 = last << 16 | first: the driver channels the interpreter may remap song channels
     * to (-$6e86/-$6e88, free-channel search at hunk 37 +$d2c). The MT-32's parts listen on MIDI
     * channels 2-9 (0-based 1-8; 9 = rhythm, kept by the songs' own flag), as in Sierra's MT-32
     * driver and ScummVM (getFirstChannel/getLastChannel). With 0-15, two sounds at once (town:
     * music 29 + ambience 886) were moved to channels 12-15, which the MT-32 ignores. */
    case 1:  driver_init((const u8 *)r->a[0]); r->d[0] = 0x00080001; r->d[1] = 0; break;
    case 2:  all_notes_off(); if (goodbye) sysex(0x200000, goodbye, 20); break;
    case 3:  break;
    case 4:  midi_msg(0x80 | ch, d1, 0x40, 3); break;
    case 5:  if (sound_on) midi_msg(0x90 | ch, d1, d1 >> 16, 3); break;
    case 7:  controller(ch, d1 & 0xff, (d1 >> 16) & 0x7f); break;
    case 8:  ch_prog[ch] = d1 & 0x7f; midi_msg(0xc0 | ch, d1, 0, 2); break;
    case 10: ch_bend[ch] = (((d1 >> 16) & 0x7f) << 7) | (d1 & 0x7f); midi_msg(0xe0 | ch, d1, d1 >> 16, 3); break;
    case 11: if ((d0 & 0xff) == 0xff) r->d[0] = reverb; else if ((d0 & 0xff) != reverb) set_reverb(d0 & 0xff); break;
    case 12: if ((d0 & 0xffff) == 0xff) r->d[0] = master;
             else { master = d0 & 15; for (int c = 0; c < NCH; c++) send_volume(c); } break;
    case 13: if ((d0 & 0xff) == 0xff) r->d[0] = sound_on;
             else { sound_on = (d0 & 0xff) != 0; if (!sound_on) all_notes_off(); for (int c = 0; c < NCH; c++) send_volume(c); } break;
    case 17: r->d[0] = ask_driver(d0, d1); break;
    default: break;
    }
}

void stub_Mt32Driver(void);
struct mtseg { u32 next; u16 jmp; void (*addr)(void); } PACKED;
struct mtseg mt32_seg __attribute__((aligned(4))) = { 0, 0x4ef9, stub_Mt32Driver };
