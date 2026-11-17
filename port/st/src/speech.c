/* Speech from the CD release on STE/TT/Falcon DMA sound (SOUND.md "Speech").
 *
 * SPEECH.DAT (tools/makespeech.py) holds the CD clips of the text lines that have one, keyed by
 * text (module, index), as signed 8-bit mono at 12517 Hz. The patched scripts (makescr.py,
 * PrintDC in script 759 and the talker procedure proc0_28 in script 0) call
 *   (DoAudio 2 module index)  -> starts the clip, returns its length in ticks (0 = none)
 *   (DoAudio 3)               -> stops it (when the text box closes)
 * which replaces Prog's own DoAudio (kernel 117, a no-op without audio hardware). Every other
 * call keeps the old behaviour (nothing happens, acc unchanged), except Position while one of our
 * clips is active. Without SPEECH.DAT or DMA sound (_SND bit 1) everything is a no-op. */
#include "amiga.h"

void *mem_alloc(u32 size, u32 flags);

struct line { u16 module, index; u32 offset, length; } PACKED;

static struct line *lines;
static int nlines;
static u8 *buf;                     /* one clip, loaded whole when it starts */
static long fh = -1;
static int active;                  /* a clip of ours is playing or just finished */
static u32 cur_len;

#define SND(o) (*(volatile u8 *)(0xffff8900UL + (o)))
#define RATE   12517

static long snd_cookie;
static long read_snd_cookie(void) {
    const u32 *jar = *(const u32 **)0x5a0;
    if (jar) for (; jar[0]; jar += 2) if (jar[0] == 0x5f534e44) { snd_cookie = jar[1]; break; }   /* '_SND' */
    return 0;
}

static long dma_stop(void) { SND(0x01) = 0; return 0; }

void speech_init(void) {
    Supexec(read_snd_cookie);
    if (!(snd_cookie & 2)) { dbg("speech: no DMA sound\n"); return; }
    long h = Fopen("SPEECH.DAT", 0);
    if (h < 0) return;
    u8 hdr[12];
    if (Fread(h, 12, hdr) != 12 || hdr[0] != 'K' || hdr[1] != 'Q' || hdr[2] != 'S' || hdr[3] != 'P') { Fclose(h); return; }
    int n = hdr[4] << 8 | hdr[5];
    u32 maxlen = (u32)hdr[8] << 24 | (u32)hdr[9] << 16 | hdr[10] << 8 | hdr[11];
    lines = mem_alloc(n * sizeof *lines, 0);
    buf = mem_alloc(maxlen, 0);
    if (!lines || !buf || Fread(h, n * sizeof *lines, lines) != (long)(n * sizeof *lines)) { Fclose(h); lines = 0; return; }
    nlines = n; fh = h;
    dbg("speech: %d lines, buffer %d bytes at $%x\n", n, (int)maxlen, (u32)buf);
}

void speech_exit(void) {
    if (fh < 0) return;
    Supexec(dma_stop);
    Fclose(fh); fh = -1;
}

static const struct line *find(int module, int index) {
    int lo = 0, hi = nlines - 1;
    while (lo <= hi) {
        int m = (lo + hi) >> 1; const struct line *l = &lines[m];
        int c = l->module != module ? l->module - module : l->index - index;
        if (!c) return l;
        if (c < 0) lo = m + 1; else hi = m - 1;
    }
    return 0;
}

static u32 dma_pos(void) {          /* bytes played */
    u32 p = (u32)SND(0x09) << 16 | (u32)SND(0x0b) << 8 | SND(0x0d);
    u32 s = (u32)buf & 0xffffff;
    return p > s ? p - s : 0;
}

/* Runs in supervisor mode (Prog does). args: argc, sub-function, ... */
void c_doaudio(const s16 *args, s16 *acc) {
    int argc = args[0], fn = argc ? args[1] : 0;
    if (fh < 0) return;
    switch (fn) {
    case 1: case 2:                 /* WPlay / Play */
        if (argc != 3) return;      /* a CD clip number: not ours */
        SND(0x01) = 0; active = 0;
        {
            const struct line *l = find(args[2], args[3]);
            if (!l || Fseek(l->offset, fh, 0) != (long)l->offset || Fread(fh, l->length, buf) != (long)l->length) {
                *acc = 0; return;
            }
            u32 s = (u32)buf, e = s + l->length;
            SND(0x03) = s >> 16; SND(0x05) = s >> 8; SND(0x07) = s;
            SND(0x0f) = e >> 16; SND(0x11) = e >> 8; SND(0x13) = e;
            SND(0x21) = 0x81;       /* mono, 12517 Hz */
            SND(0x01) = 1;          /* play once */
            active = 1; cur_len = l->length;
            dbg("speech: line %d %d, %d bytes\n", args[2], args[3], (int)cur_len);
            *acc = cur_len * 60 / RATE + 1;
        }
        return;
    case 3:                         /* Stop */
        if (active) dbg("speech: stop, %s, %d of %d bytes\n", (SND(0x01) & 1) ? "playing" : "done",
                        (int)dma_pos(), (int)cur_len);
        SND(0x01) = 0; active = 0;
        return;
    case 6:                         /* Position: ticks played, -1 when done */
        if (!active) return;
        *acc = (SND(0x01) & 1) ? (s16)(dma_pos() * 60 / RATE) : -1;
        return;
    }
}
