/* dos.library stand-in on GEMDOS. Paths are AmigaDOS style ("vol:dir/file", "/" = parent) and are
 * resolved against the directory the program was started from ("root"). Locks and file handles are
 * BPTRs to shim-owned structures. */
#include "amiga.h"

#define MODE_READWRITE 1004
#define MODE_OLDFILE   1005
#define MODE_NEWFILE   1006
#define OFFSET_BEGINNING -1
#define OFFSET_CURRENT    0
#define OFFSET_END        1
#define ERROR_OBJECT_NOT_FOUND 205
#define ERROR_NO_MORE_ENTRIES  232

#define PATHMAX 160

struct Lock { char path[PATHMAX]; int isdir; u8 dta[44]; int scanning; } __attribute__((aligned(4)));
struct FileHandle { u32 link, port, type, buf, pos, end, funcs, func2, func3; s32 handle; u32 arg2; int console, cached; }
    __attribute__((aligned(4)));

static char root[PATHMAX];        /* e.g. "C:\KQ5" (no trailing backslash) */
static u32 last_error;
static struct FileHandle con_in, con_out;

#define BADDR(b) ((void *)((u32)(b) << 2))
#define MKBADDR(p) ((u32)(p) >> 2)

/* ---- path handling --------------------------------------------------------------------- */
/* Build an ST path from a base directory (ST form) and an AmigaDOS relative path. */
static void resolve(char *out, const char *base, const char *apath) {
    const char *colon = 0;
    for (const char *s = apath; *s; s++) if (*s == ':') colon = s;
    if (colon) { strcpy(out, root); apath = colon + 1; }     /* "vol:x" and ":x" -> game root */
    else strcpy(out, base);
    while (*apath) {
        if (*apath == '/') {                                   /* leading/extra '/' = parent */
            char *b = out + strlen(out);
            while (b > out && *b != '\\') b--;
            if (b > out + 2) *b = 0;
            apath++; continue;
        }
        char comp[64]; int n = 0;
        while (*apath && *apath != '/' && n < 63) comp[n++] = *apath++;
        comp[n] = 0;
        if (*apath == '/') apath++;
        if (strcmp(comp, ".")) { strcat(out, "\\"); strcat(out, comp); }
    }
}

static const char *cur_dir(void) {
    struct Lock *l = the_process->currentdir ? BADDR(the_process->currentdir) : 0;
    return l ? l->path : root;
}

/* ---- game-directory cache ------------------------------------------------------------- */
/* SCI looks for a patch file before every resource (Lock "N.scr", then "df3:N.scr") and opens
 * RESOURCE.000 again for each one. On a real disk every such GEMDOS lookup searches the ~600-entry
 * folder linearly (start-up took ~2 min). So the folder's names, attributes and sizes are read
 * once: lookups of files directly in the game folder are answered from the cache, and a few
 * read-only handles are kept open for reuse (c_Open/c_Close). Files the game creates or rewrites
 * are marked "live" (asked from GEMDOS again); deleted ones are dropped. Names are kept in GEMDOS
 * 8.3 upper-case form. */
#define DC_MAX  1024
#define DC_HASH 256
struct DEnt { char name[13]; u8 attr; u16 next; u16 live; u32 size; };   /* next: index + 1, 0 = end */
static struct DEnt *dc;
static u16 dc_head[DC_HASH];
static int dc_n, dc_ok;

static int norm83(char *out, const char *s) {           /* 0 if not a plain 8.3 name */
    int n = 0, base = 0, ext = -1;
    for (; *s; s++) {
        char c = *s;
        if (c == '*' || c == '?' || c == '\\' || c == ':') return 0;
        if (c == '.') { if (ext >= 0 || !base) return 0; ext = 0; out[n++] = '.'; continue; }
        if (c >= 'a' && c <= 'z') c -= 32;
        if (ext < 0) { if (base++ < 8) out[n++] = c; }      /* GEMDOS truncates to 8.3 */
        else if (ext++ < 3) out[n++] = c;
    }
    out[n] = 0;
    return base > 0;
}
static int dc_hash(const char *s) { u16 h = 0; while (*s) h = h * 31 + (u8)*s++; return h & (DC_HASH - 1); }
static struct DEnt *dc_find(const char *n) {
    for (int i = dc_head[dc_hash(n)]; i; i = dc[i - 1].next) if (!strcmp(dc[i - 1].name, n)) return &dc[i - 1];
    return 0;
}
static struct DEnt *dc_add(const char *n) {               /* n already normalised */
    struct DEnt *e = dc_find(n);
    if (e) return e;
    if (dc_n == DC_MAX) { dc_ok = 0; return 0; }           /* too many: GEMDOS for everything */
    e = &dc[dc_n++]; int h = dc_hash(n);
    strcpy(e->name, n); e->attr = 0; e->live = 1; e->size = 0; e->next = dc_head[h]; dc_head[h] = dc_n;
    return e;
}
static void dc_build(void) {
    u8 dta[44]; char spec[PATHMAX], n[13];
    dc = mem_alloc(DC_MAX * sizeof *dc, 0); if (!dc) return;
    dc_ok = 1;
    Fsetdta(dta); strcpy(spec, root); strcat(spec, "\\*.*");
    for (long rc = Fsfirst(spec, 0x17); rc == 0 && dc_ok; rc = Fsnext()) {
        struct DEnt *e = norm83(n, (const char *)dta + 30) ? dc_add(n) : 0;
        if (e) { e->attr = dta[21]; e->size = (dta[26] << 24) | (dta[27] << 16) | (dta[28] << 8) | dta[29]; e->live = 0; }
    }
    dbg("directory cache: %d names%s\n", dc_n, dc_ok ? "" : " (too many, off)");
}
/* For a path directly in the game folder: put its normalised name in n and return 1. */
static int in_root(const char *stpath, char *n) {
    const char *r = root;
    while (*r && *r == *stpath) r++, stpath++;
    if (*r || *stpath != '\\') return 0;
    for (const char *s = ++stpath; *s; s++) if (*s == '\\') return 0;
    return dc_ok && norm83(n, stpath);
}

/* Read-only handles kept open after Close, for files in the game folder (RESOURCE.00x). */
#define HC_N 6
static struct { char name[13]; u8 busy; long h; u32 used; } hc[HC_N];
static u32 hc_clock;
static void hc_drop(const char *n) {                       /* the file is rewritten or deleted */
    for (int i = 0; i < HC_N; i++) if (hc[i].h && !strcmp(hc[i].name, n)) {
        if (hc[i].busy) hc[i].name[0] = 0;                  /* closed by c_Close */
        else { Fclose(hc[i].h); hc[i].h = 0; }
    }
}

static int st_isdir(const char *path, u8 *dta) {
    Fsetdta(dta);
    if (strlen(path) <= 2) return 1;                           /* "C:" */
    char n[13];
    if (in_root(path, n)) {
        struct DEnt *e = dc_find(n);
        if (!e) return -1;
        if (!e->live) {                                        /* as Fsfirst would fill the DTA */
            dta[21] = e->attr; dta[26] = e->size >> 24; dta[27] = e->size >> 16; dta[28] = e->size >> 8; dta[29] = e->size;
            strcpy((char *)dta + 30, n);
            return (e->attr & 0x10) ? 1 : 0;
        }
    }
    if (Fsfirst(path, 0x17) < 0) return -1;                    /* include dirs/hidden/system */
    return (dta[21] & 0x10) ? 1 : 0;
}

/* ---- locks ---------------------------------------------------------------------------- */
static u32 make_lock(const char *stpath) {
    struct Lock *l = mem_alloc(sizeof *l, 0x10000);
    strcpy(l->path, stpath);
    int d = st_isdir(stpath, l->dta);
    if (d < 0) { mem_free(l, sizeof *l); last_error = ERROR_OBJECT_NOT_FOUND; return 0; }
    l->isdir = d;
    return MKBADDR(l);
}

u32 dos_lock_dir(const char *path) { char p[PATHMAX]; resolve(p, root, path); return make_lock(p); }

#define R struct regs *r

void c_Lock(R) {
    char p[PATHMAX]; resolve(p, cur_dir(), (const char *)r->d[1]);
    r->d[0] = make_lock(p);
    dbg("Lock(\"%s\") -> %s %s\n", (const char *)r->d[1], p, r->d[0] ? "ok" : "not found");
}
void c_UnLock(R) { if (r->d[1]) mem_free(BADDR(r->d[1]), sizeof(struct Lock)); }
void c_DupLock(R) { r->d[0] = r->d[1] ? make_lock(((struct Lock *)BADDR(r->d[1]))->path) : make_lock(root); }
void c_CurrentDir(R) { r->d[0] = the_process->currentdir; the_process->currentdir = r->d[1]; }
void c_ParentDir(R) {
    struct Lock *l = r->d[1] ? BADDR(r->d[1]) : 0;
    char p[PATHMAX]; strcpy(p, l ? l->path : root);
    char *b = p + strlen(p); while (b > p && *b != '\\') b--;
    if (b <= p + 2) { r->d[0] = 0; return; }                   /* already at drive root */
    *b = 0; r->d[0] = make_lock(p);
}

/* FileInfoBlock offsets */
#define FIB_DIRENTRYTYPE 4
#define FIB_FILENAME     8
#define FIB_PROTECTION 116
#define FIB_ENTRYTYPE  120
#define FIB_SIZE       124
#define FIB_NUMBLOCKS  128

static void fill_fib(u8 *fib, const u8 *dta, const char *name) {
    memset(fib, 0, 260);
    s32 type = (dta[21] & 0x10) ? 2 : -3;
    *(s32 *)(fib + FIB_DIRENTRYTYPE) = type; *(s32 *)(fib + FIB_ENTRYTYPE) = type;
    int n = strlen(name); if (n > 106) n = 106;
    memcpy(fib + FIB_FILENAME, name, n); fib[FIB_FILENAME + n] = 0;    /* fib_FileName is a C string */
    u32 size = (dta[26] << 24) | (dta[27] << 16) | (dta[28] << 8) | dta[29];
    *(u32 *)(fib + FIB_SIZE) = size; *(u32 *)(fib + FIB_NUMBLOCKS) = (size + 511) >> 9;
}

void c_Examine(R) {
    struct Lock *l = BADDR(r->d[1]); u8 *fib = (u8 *)r->d[2];
    const char *name = l->path + strlen(l->path);
    while (name > l->path && name[-1] != '\\' && name[-1] != ':') name--;
    u8 dta[44];
    if (l->isdir) { memset(dta, 0, sizeof dta); dta[21] = 0x10; }
    else if (st_isdir(l->path, dta) < 0) { r->d[0] = 0; last_error = ERROR_OBJECT_NOT_FOUND; return; }
    fill_fib(fib, dta, name);
    l->scanning = 0;
    r->d[0] = -1;
}

void c_ExNext(R) {
    struct Lock *l = BADDR(r->d[1]); u8 *fib = (u8 *)r->d[2];
    Fsetdta(l->dta);
    long rc;
    for (;;) {
        if (!l->scanning) { char spec[PATHMAX]; strcpy(spec, l->path); strcat(spec, "\\*.*"); rc = Fsfirst(spec, 0x17); l->scanning = 1; }
        else rc = Fsnext();
        if (rc < 0) { r->d[0] = 0; last_error = ERROR_NO_MORE_ENTRIES; return; }
        const char *n = (const char *)l->dta + 30;
        if (strcmp(n, ".") && strcmp(n, "..")) break;
    }
    fill_fib(fib, l->dta, (const char *)l->dta + 30);
    r->d[0] = -1;
}

void c_Info(R) {
    u32 *info = (u32 *)r->d[2];
    long di[4]; int drive = root[0] >= 'a' ? root[0] - 'a' + 1 : root[0] - 'A' + 1;
    memset(info, 0, 36);
    if (Dfree(di, drive) == 0) {           /* free clusters, total clusters, bytes/sector, sectors/cluster */
        info[3] = di[1] * di[3]; info[4] = (di[1] - di[0]) * di[3]; info[5] = di[2];
    }
    info[2] = 82;                           /* ID_VALIDATED */
    info[6] = 0x444f5300;                   /* ID_DOS_DISK */
    r->d[0] = -1;
}

/* ---- files ----------------------------------------------------------------------------- */
static int is_device(const char *name, const char *dev) {          /* case-insensitive prefix */
    while (*dev) { char a = *name++, b = *dev++; if (a >= 'a' && a <= 'z') a -= 32; if (a != b) return 0; }
    return 1;
}
void c_Open(R) {
    const char *name = (const char *)r->d[1]; s32 mode = r->d[2];
    if (!strcmp(name, "*") || is_device(name, "CON:") || is_device(name, "RAW:") || is_device(name, "NIL:")) {
        r->d[0] = MKBADDR(mode == MODE_OLDFILE ? &con_in : &con_out); return;
    }
    char p[PATHMAX], n[13]; resolve(p, cur_dir(), name);
    int root_file = in_root(p, n), slot = -1;
    long h = -1;
    if (root_file && mode == MODE_OLDFILE) {
        for (int i = 0; i < HC_N && slot < 0; i++)
            if (hc[i].h && !hc[i].busy && !strcmp(hc[i].name, n)) { slot = i; h = hc[i].h; Fseek(0, h, 0); }
        if (slot < 0 && !dc_find(n)) h = -33;                  /* known missing */
    }
    if (root_file && mode != MODE_OLDFILE) hc_drop(n);
    if (slot < 0 && h != -33) h = mode == MODE_NEWFILE ? Fcreate(p, 0) : Fopen(p, mode == MODE_OLDFILE ? 0 : 2);
    if (h < 0 && mode == MODE_READWRITE) h = Fcreate(p, 0);
    dbg("Open(\"%s\", %d) -> %s h=%d%s\n", name, mode, p, h, slot >= 0 ? " (kept open)" : "");
    if (h < 0) { r->d[0] = 0; last_error = ERROR_OBJECT_NOT_FOUND; return; }
    if (root_file && mode != MODE_OLDFILE) { struct DEnt *e = dc_add(n); if (e) e->live = 1; }   /* may be new */
    if (root_file && mode == MODE_OLDFILE && slot < 0) {      /* take a free or the least recently used slot */
        for (int i = 0; i < HC_N; i++)
            if (!hc[i].busy && (slot < 0 || !hc[i].h || (hc[slot].h && hc[i].used < hc[slot].used))) slot = i;
        if (slot >= 0) { if (hc[slot].h) Fclose(hc[slot].h); hc[slot].h = h; strcpy(hc[slot].name, n); }
    }
    if (slot >= 0) { hc[slot].busy = 1; hc[slot].used = ++hc_clock; }
    struct FileHandle *fh = mem_alloc(sizeof *fh, 0x10000);
    fh->handle = h; fh->type = 0; fh->cached = slot + 1;
    r->d[0] = MKBADDR(fh);
}

void c_Close(R) {
    struct FileHandle *fh = BADDR(r->d[1]);
    if (!fh || fh->console) return;
    int i = fh->cached - 1;
    if (i >= 0) { hc[i].busy = 0; if (!hc[i].name[0]) { Fclose(hc[i].h); hc[i].h = 0; } }
    else Fclose(fh->handle);
    mem_free(fh, sizeof *fh);
}

void c_Read(R) {
    struct FileHandle *fh = BADDR(r->d[1]);
    if (fh->console) { r->d[0] = 0; return; }
    r->d[0] = Fread(fh->handle, r->d[3], (void *)r->d[2]);
}

void c_Write(R) {
    struct FileHandle *fh = BADDR(r->d[1]);
    if (fh->console) {
        char buf[200]; s32 n = r->d[3] < 199 ? r->d[3] : 199;
        memcpy(buf, (void *)r->d[2], n); buf[n] = 0; nf_print(buf); r->d[0] = r->d[3]; return;
    }
    r->d[0] = Fwrite(fh->handle, r->d[3], (void *)r->d[2]);
}

void c_Seek(R) {
    struct FileHandle *fh = BADDR(r->d[1]);
    s32 mode = r->d[3]; int m = mode == OFFSET_BEGINNING ? 0 : mode == OFFSET_CURRENT ? 1 : 2;
    long old = Fseek(0, fh->handle, 1);
    long rc = Fseek(r->d[2], fh->handle, m);
    r->d[0] = rc < 0 ? -1 : old;
}

void c_DeleteFile(R) {
    char p[PATHMAX], n[13]; resolve(p, cur_dir(), (const char *)r->d[1]);
    if (in_root(p, n)) { hc_drop(n); struct DEnt *e = dc_find(n); if (e) e->name[0] = 0; }   /* now missing */
    r->d[0] = Fdelete(p) == 0 ? -1 : 0;
}

void c_Input(R) { r->d[0] = MKBADDR(&con_in); }
void c_Output(R) { r->d[0] = MKBADDR(&con_out); }
void c_IsInteractive(R) { struct FileHandle *fh = BADDR(r->d[1]); r->d[0] = fh && fh->console ? -1 : 0; }
void c_IoErr(R) { r->d[0] = last_error; }
extern char silent_seg[], ym_seg[];
/* A file NOSND in the game directory selects the silent driver (testing). */
static int getenv_nosnd(void) { long h = Fopen("NOSND", 0); if (h < 0) return 0; Fclose(h); return 1; }
void c_LoadSeg(R) {
    const char *name = (const char *)r->d[1]; int n = strlen(name);
    if (n > 4 && !stricmp(name + n - 4, ".drv")) {
        int silent = getenv_nosnd();
        dbg("LoadSeg(\"%s\") -> %s sound driver\n", name, silent ? "silent" : "YM2149");
        r->d[0] = MKBADDR(silent ? silent_seg : ym_seg); return;
    }
    fatal("LoadSeg(\"%s\") not supported", name);
}
void c_UnLoadSeg(R) { (void)r; }
void c_Exit(R) { fatal("dos Exit(%d)", r->d[1]); }

/* ---- set-up ------------------------------------------------------------------------------ */
extern void stub_Lock(void), stub_UnLock(void), stub_DupLock(void), stub_CurrentDir(void), stub_ParentDir(void),
    stub_Examine(void), stub_ExNext(void), stub_Info(void), stub_Open(void), stub_Close(void), stub_Read(void),
    stub_Write(void), stub_Seek(void), stub_DeleteFile(void), stub_Input(void), stub_Output(void),
    stub_IsInteractive(void), stub_IoErr(void), stub_Exit(void), stub_LoadSeg(void), stub_UnLoadSeg(void);

void dos_init(void) {
    int drv = Dgetdrv();
    root[0] = 'A' + drv; root[1] = ':'; root[2] = 0;
    Dgetpath(root + 2, drv + 1);
    int n = strlen(root); if (n > 2 && root[n - 1] == '\\') root[n - 1] = 0;
    dbg("game directory: %s\n", root);
    dc_build();
    con_in.console = con_out.console = 1; con_in.port = con_out.port = 1;

    DOSBase = make_library("dos.library", 40, 0x40);
    static const struct { int lvo; void (*f)(void); } t[] = {
        { -30, stub_Open }, { -36, stub_Close }, { -42, stub_Read }, { -48, stub_Write }, { -54, stub_Input },
        { -60, stub_Output }, { -66, stub_Seek }, { -72, stub_DeleteFile }, { -84, stub_Lock }, { -90, stub_UnLock },
        { -96, stub_DupLock }, { -102, stub_Examine }, { -108, stub_ExNext }, { -114, stub_Info }, { -126, stub_CurrentDir },
        { -132, stub_IoErr }, { -144, stub_Exit }, { -150, stub_LoadSeg }, { -156, stub_UnLoadSeg }, { -210, stub_ParentDir }, { -216, stub_IsInteractive } };
    for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++) set_lvo(DOSBase, t[i].lvo, t[i].f);
}
