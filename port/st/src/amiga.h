/* Minimal AmigaOS structure layouts used by the KQ5 interpreter, plus shim-wide helpers. */
#ifndef AMIGA_H
#define AMIGA_H

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned long  u32;
typedef signed char    s8;
typedef signed short   s16;
typedef signed long    s32;

#define PACKED __attribute__((packed))
#define CHECK(s, f, o) _Static_assert(__builtin_offsetof(struct s, f) == (o), #s "." #f)

struct Node { struct Node *succ, *pred; u8 type; s8 pri; char *name; } PACKED;
struct List { struct Node *head, *tail, *tailpred; u8 type, pad; } PACKED;

struct MsgPort { struct Node node; u8 flags, sigbit; void *sigtask; struct List msglist; } PACKED;
struct Message { struct Node node; struct MsgPort *replyport; u16 length; } PACKED;
CHECK(MsgPort, msglist, 20);
CHECK(Message, length, 18);

struct Library { struct Node node; u8 flags, pad; u16 negsize, possize, version, revision;
                 char *idstring; u32 sum; u16 opencnt; } PACKED;
CHECK(Library, opencnt, 32);

struct Task {
    struct Node node; u8 flags, state; s8 idnest, tdnest;
    u32 sigalloc, sigwait, sigrecvd, sigexcept;
    u16 trapalloc, trapable; void *exceptdata, *exceptcode, *trapdata, *trapcode;
    void *spreg, *splower, *spupper; void *switchf, *launchf; struct List memlist; void *userdata;
} PACKED;
CHECK(Task, sigrecvd, 26);
CHECK(Task, userdata, 88);

struct Process {
    struct Task task; struct MsgPort msgport; u16 pad;
    u32 seglist, stacksize; void *globvec; u32 tasknum, stackbase, result2, currentdir;
    u32 cis, cos; void *consoletask, *filesystemtask; u32 cli; void *returnaddr, *pktwait, *windowptr;
} PACKED;
CHECK(Process, msgport, 0x5c);
CHECK(Process, currentdir, 0x98);
CHECK(Process, cli, 0xac);
CHECK(Process, windowptr, 0xb8);

/* Registers saved by every LVO stub: d0-d7 then a0-a6 (movem order). */
struct regs { u32 d[8]; u32 a[7]; };

/* The 54-byte message the Amiga loader sends to "SCIport" (see docs). */
struct LoaderMsg {
    struct Message msg;            /* name "heyyou" */
    u32 seglist;                   /* +$14 */
    u32 dirlock;                   /* +$18 game directory lock */
    void *splash_screen;           /* +$1c loader's screen, closed by Prog */
    void *snd_data; u32 snd_size;  /* +$20/+$24 */
    void *reserve;                 /* +$28 block Prog frees with fixed size $2f9b8 */
    void *heap; u32 heap_n;        /* +$2c/+$30 heap reservation, freed and re-allocated by Prog */
    u16 flag34;                    /* +$34 */
} PACKED;
_Static_assert(sizeof(struct LoaderMsg) == 0x36, "loader message size");
CHECK(LoaderMsg, flag34, 0x34);
CHECK(LoaderMsg, heap_n, 0x30);

/* shim.c */
void nf_print(const char *s);
void dbg(const char *fmt, ...);
__attribute__((noreturn)) void fatal(const char *fmt, ...);
void *memset(void *d, int c, unsigned long n);
void *memcpy(void *d, const void *s, unsigned long n);
int strlen(const char *s);
int strcmp(const char *a, const char *b);
int stricmp(const char *a, const char *b);
char *strcpy(char *d, const char *s);
char *strcat(char *d, const char *s);
const char *hunk_addr(u32 a);              /* "H17_1f4" style name for a Prog address */

/* memory.c */
void mem_init(void);
void *mem_alloc(u32 size, u32 flags);
void mem_free(void *p, u32 size);
u32 mem_avail(u32 flags);

/* lists */
void list_init(struct List *l);
void list_addtail(struct List *l, struct Node *n);
void list_addhead(struct List *l, struct Node *n);
void list_remove(struct Node *n);
struct Node *list_remhead(struct List *l);

extern struct LoaderMsg *loader_msg;

/* exec.c */
extern struct Library *SysBase, *DOSBase, *IntuitionBase, *GfxBase;
extern struct Process *the_process;
void exec_init(void);
void signal_task(u32 sigs);
void poll_events(void);                     /* run event sources while waiting */
struct Library *make_library(const char *name, int nslots, int possize);
void set_lvo(struct Library *lib, int lvo, void (*stub)(void));

/* display.c */
void display_init(void);
void display_poll(void);
void display_shot(void);
void display_convert(void);
void display_convert_rect(int x1, int y1, int x2, int y2);
int display_is_shown(const void *p);

/* input.c */
void input_init(void);
void input_restore(void);
void display_restore(void);
long ym_silence(void);

/* dos.c */
void dos_init(void);
u32 dos_lock_dir(const char *path);         /* BPTR lock for a directory */

/* GEMDOS / BIOS / XBIOS (gemdos.S) */
long Fopen(const char *name, int mode);
long Fcreate(const char *name, int attr);
long Fclose(int h);
long Fread(int h, long n, void *buf);
long Fwrite(int h, long n, const void *buf);
long Fseek(long off, int h, int mode);
long Fdelete(const char *name);
long Fsfirst(const char *spec, int attr);
long Fsnext(void);
void Fsetdta(void *dta);
long Dgetdrv(void);
long Dgetpath(char *buf, int drive);
long Dfree(void *info, int drive);
long Malloc(long n);
long Mfree(void *p);
void Cconws(const char *s);
long Setexc(int vec, void *handler);
long Supexec(long (*f)(void));
void Vsync(void);
long Physbase(void);
long Logbase(void);
void Setscreen(long log, long phys, int res);
void Setpalette(void *pal);
long Getrez(void);

/* glue.S */
extern char hunk0[], prog_end[];
long run_prog(void *entry, void *stack_top, long stack_size);
void nf_stderr(const char *s);
int nf_available(void);

#endif
