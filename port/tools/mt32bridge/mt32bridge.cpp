// mt32bridge ROMDIR FIFO: plays raw MIDI bytes arriving on FIFO (Hatari --midi-out FIFO) through
// Munt's MT-32 emulation (libmt32emu) and writes 32 kHz stereo s16 PCM to stdout, paced by the
// audio player on the other end of the pipe (pw-cat/aplay). MT-32 display texts go to stderr.
// ROMDIR holds MT32_CONTROL.ROM and MT32_PCM.ROM (or CM32L_*). Build: build.sh (docs/WORKFLOW.md
// "MT-32 in Hatari").
#include <cstdio>
#include <cstring>
#include <string>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include "mt32emu.h"

using namespace MT32Emu;

struct Report : ReportHandler {
    void printDebug(const char *, va_list) override {}
    void showLCDMessage(const char *m) override { fprintf(stderr, "MT-32 display: \"%s\"\n", m); }
    void onErrorControlROM() override { fprintf(stderr, "control ROM error\n"); }
    void onErrorPCMROM() override { fprintf(stderr, "PCM ROM error\n"); }
};

static const ROMImage *load(const std::string &dir, const char *a, const char *b) {
    for (const char *n : { a, b }) {
        FileStream *f = new FileStream;
        if (f->open((dir + "/" + n).c_str())) {
            const ROMImage *img = ROMImage::makeROMImage(f);
            if (img && img->getROMInfo()) { fprintf(stderr, "ROM: %s (%s)\n", n, img->getROMInfo()->description); return img; }
        }
        delete f;
    }
    return nullptr;
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: mt32bridge ROMDIR FIFO > pcm\n"); return 2; }
    signal(SIGPIPE, SIG_DFL);
    const ROMImage *ctl = load(argv[1], "MT32_CONTROL.ROM", "CM32L_CONTROL.ROM");
    const ROMImage *pcm = load(argv[1], "MT32_PCM.ROM", "CM32L_PCM.ROM");
    if (!ctl || !pcm) { fprintf(stderr, "no usable MT-32/CM-32L ROMs in %s\n", argv[1]); return 1; }
    Report report;
    Synth synth(&report);
    if (!synth.open(*ctl, *pcm)) { fprintf(stderr, "synth open failed\n"); return 1; }
    fprintf(stderr, "mt32bridge: %u Hz stereo, reading %s\n", synth.getStereoOutputSampleRate(), argv[2]);
    DefaultMidiStreamParser parser(synth);
    int fd = open(argv[2], O_RDONLY | O_NONBLOCK);          // FIFO: does not wait for a writer
    if (fd < 0) { perror(argv[2]); return 1; }
    enum { FRAMES = 256 };                                   // 8 ms per chunk at 32 kHz
    Bit16s buf[FRAMES * 2];
    Bit8u in[4096];
    unsigned long total = 0;
    for (;;) {
        ssize_t n;
        while ((n = read(fd, in, sizeof in)) > 0) { parser.parseStream(in, (Bit32u)n); total += n; }
        synth.render(buf, FRAMES);
        if (fwrite(buf, sizeof buf, 1, stdout) != 1) break;  // player gone
    }
    fprintf(stderr, "mt32bridge: %lu MIDI bytes\n", total);
    synth.close();
    return 0;
}
