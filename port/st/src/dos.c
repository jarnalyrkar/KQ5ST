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
struct FileHandle { u32 link, port, type, buf, pos, end, funcs, func2, func3; s32 handle; u32 arg2; int console; }
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

static int st_isdir(const char *path, u8 *dta) {
    Fsetdta(dta);
    if (strlen(path) <= 2) return 1;                           /* "C:" */
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
    char p[PATHMAX]; resolve(p, cur_dir(), name);
    long h = mode == MODE_NEWFILE ? Fcreate(p, 0) : Fopen(p, mode == MODE_OLDFILE ? 0 : 2);
    if (h < 0 && mode == MODE_READWRITE) h = Fcreate(p, 0);
    dbg("Open(\"%s\", %d) -> %s h=%d\n", name, mode, p, h);
    if (h < 0) { r->d[0] = 0; last_error = ERROR_OBJECT_NOT_FOUND; return; }
    struct FileHandle *fh = mem_alloc(sizeof *fh, 0x10000);
    fh->handle = h; fh->type = 0;
    r->d[0] = MKBADDR(fh);
}

void c_Close(R) {
    struct FileHandle *fh = BADDR(r->d[1]);
    if (!fh || fh->console) return;
    Fclose(fh->handle); mem_free(fh, sizeof *fh);
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
    char p[PATHMAX]; resolve(p, cur_dir(), (const char *)r->d[1]);
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
    con_in.console = con_out.console = 1; con_in.port = con_out.port = 1;

    DOSBase = make_library("dos.library", 40, 0x40);
    static const struct { int lvo; void (*f)(void); } t[] = {
        { -30, stub_Open }, { -36, stub_Close }, { -42, stub_Read }, { -48, stub_Write }, { -54, stub_Input },
        { -60, stub_Output }, { -66, stub_Seek }, { -72, stub_DeleteFile }, { -84, stub_Lock }, { -90, stub_UnLock },
        { -96, stub_DupLock }, { -102, stub_Examine }, { -108, stub_ExNext }, { -114, stub_Info }, { -126, stub_CurrentDir },
        { -132, stub_IoErr }, { -144, stub_Exit }, { -150, stub_LoadSeg }, { -156, stub_UnLoadSeg }, { -210, stub_ParentDir }, { -216, stub_IsInteractive } };
    for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++) set_lvo(DOSBase, t[i].lvo, t[i].f);
}
