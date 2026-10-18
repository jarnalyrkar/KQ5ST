/* exec.library stand-in: libraries with real jump tables, one process ("SCI"), ports, signals. */
#include "amiga.h"

struct Library *SysBase, *DOSBase, *IntuitionBase, *GfxBase;
struct Process *the_process;
extern char unimpl_vector[];

#define MAX_LIBS 8
static struct { struct Library *base; int nslots; } libs[MAX_LIBS];
static int nlibs;

/* ---- lists ---------------------------------------------------------------------------- */
void list_init(struct List *l) {
    l->head = (struct Node *)&l->tail; l->tail = 0; l->tailpred = (struct Node *)&l->head;
}
void list_addtail(struct List *l, struct Node *n) {
    struct Node *last = l->tailpred;
    n->succ = (struct Node *)&l->tail; n->pred = last; last->succ = n; l->tailpred = n;
}
void list_addhead(struct List *l, struct Node *n) {
    struct Node *first = l->head;
    n->succ = first; n->pred = (struct Node *)&l->head; first->pred = n; l->head = n;
}
void list_remove(struct Node *n) { n->pred->succ = n->succ; n->succ->pred = n->pred; }
struct Node *list_remhead(struct List *l) {
    struct Node *n = l->head;
    if (!n->succ) return 0;
    list_remove(n); return n;
}

/* ---- libraries -------------------------------------------------------------------------- */
struct Library *make_library(const char *name, int nslots, int possize) {
    int neg = nslots * 6;
    u8 *mem = mem_alloc(neg + possize, 0x10000);
    struct Library *lib = (struct Library *)(mem + neg);
    for (int i = 1; i <= nslots; i++) {
        u8 *slot = (u8 *)lib - 6 * i;
        slot[0] = 0x4e; slot[1] = 0xb9;                      /* jsr unimpl_vector */
        *(u32 *)(slot + 2) = (u32)unimpl_vector;
    }
    lib->node.name = (char *)name; lib->node.type = 9;       /* NT_LIBRARY */
    lib->negsize = neg; lib->possize = possize; lib->version = 34; lib->idstring = (char *)name;
    libs[nlibs].base = lib; libs[nlibs].nslots = nslots; nlibs++;
    return lib;
}

void set_lvo(struct Library *lib, int lvo, void (*stub)(void)) {
    u8 *slot = (u8 *)lib + lvo;                              /* lvo is negative */
    slot[0] = 0x4e; slot[1] = 0xf9;                          /* jmp stub */
    *(u32 *)(slot + 2) = (u32)stub;
}

void c_unimpl(u32 slotret, u32 caller) {
    u32 slot = slotret - 6;
    for (int i = 0; i < nlibs; i++) {
        u32 b = (u32)libs[i].base;
        if (slot < b && slot >= b - libs[i].nslots * 6)
            fatal("unimplemented %s LVO %d called from %H", libs[i].base->node.name, (s32)(slot - b), caller);
    }
    fatal("unimplemented vector $%x called from %H", slot, caller);
}

/* ---- signals and ports ------------------------------------------------------------------ */
#define PA_SIGNAL 0

void signal_task(u32 sigs) { the_process->task.sigrecvd |= sigs; }

static void put_msg(struct MsgPort *port, struct Message *msg) {
    msg->node.type = 5;                                      /* NT_MESSAGE */
    list_addtail(&port->msglist, &msg->node);
    if ((port->flags & 3) == PA_SIGNAL) signal_task(1UL << port->sigbit);
}

static struct List public_ports;

void poll_events(void) {
    Vsync();
    display_poll();
}

static u32 wait_sigs(u32 mask) {
    struct Task *t = &the_process->task;
    u32 spins = 0;
    while (!(t->sigrecvd & mask)) {
        poll_events();
        if (++spins == 500) dbg("Wait($%x) still blocked (received $%x)\n", mask, t->sigrecvd);
    }
    u32 got = t->sigrecvd & mask;
    t->sigrecvd &= ~got;
    return got;
}

/* ---- LVO implementations ------------------------------------------------------------------ */
#define R struct regs *r

void c_Forbid(R) { (void)r; }
void c_Permit(R) { (void)r; }
extern volatile s16 int_disable;
extern struct Interrupt *vbl_servers[8];
extern char vbl_dispatch[];
void c_Disable(R) { (void)r; int_disable++; }
void c_Enable(R) { (void)r; if (int_disable > 0) int_disable--; }

/* struct Interrupt: Node (14), is_Data (14), is_Code (18) */
struct Interrupt { struct Node node; void *data; void (*code)(void); } PACKED;
#define INTB_VERTB 5

static long install_vbl(void) {
    s16 n = *(volatile s16 *)0x454; void (**q)(void) = *(void (***)(void))0x456;
    for (int i = 0; i < n; i++) if (!q[i]) { q[i] = (void (*)(void))vbl_dispatch; return 1; }
    return 0;
}

void c_AddIntServer(R) {
    struct Interrupt *is = (struct Interrupt *)r->a[1];
    dbg("AddIntServer(%d, \"%s\", code %H)\n", r->d[0], is->node.name, (u32)is->code);
    if (r->d[0] != INTB_VERTB) fatal("AddIntServer: interrupt %d not supported", r->d[0]);
    int i = 0; while (vbl_servers[i]) i++;
    int_disable++; vbl_servers[i] = is; vbl_servers[i + 1] = 0; int_disable--;
}

void c_RemIntServer(R) {
    struct Interrupt *is = (struct Interrupt *)r->a[1];
    int_disable++;
    int i = 0; while (vbl_servers[i] && vbl_servers[i] != is) i++;
    for (; vbl_servers[i]; i++) vbl_servers[i] = vbl_servers[i + 1];
    int_disable--;
}

#define CALLER(r) (*(u32 *)((u8 *)(r) + sizeof(struct regs)))     /* return address into Prog */
void c_AllocMem(R) {
    u32 n = r->d[0], f = r->d[1];
    r->d[0] = (u32)mem_alloc(n, f);
    if (n >= 16384) dbg("AllocMem(%d, $%x) from %H -> $%x\n", n, f, CALLER(r), r->d[0]);
}
void c_FreeMem(R) { mem_free((void *)r->a[1], r->d[0]); }
void c_AvailMem(R) { r->d[0] = mem_avail(r->d[1]); }

void c_FindTask(R) {
    const char *name = (const char *)r->a[1];
    r->d[0] = (!name || !strcmp(name, "SCI")) ? (u32)the_process : 0;
    if (name && strcmp(name, "SCI")) dbg("FindTask(\"%s\") -> 0\n", name);
}

void c_AllocSignal(R) {
    struct Task *t = &the_process->task; s32 want = (s8)r->d[0];
    if (want >= 0) {
        if (t->sigalloc & (1UL << want)) { r->d[0] = -1; return; }
    } else {
        for (want = 16; want < 32 && (t->sigalloc & (1UL << want)); want++) ;
        if (want == 32) { r->d[0] = -1; return; }
    }
    t->sigalloc |= 1UL << want; t->sigrecvd &= ~(1UL << want);
    r->d[0] = want;
}
void c_FreeSignal(R) { if ((s32)r->d[0] >= 0) the_process->task.sigalloc &= ~(1UL << r->d[0]); }
void c_SetSignal(R) {
    struct Task *t = &the_process->task; u32 old = t->sigrecvd;
    t->sigrecvd = (old & ~r->d[1]) | (r->d[0] & r->d[1]); r->d[0] = old;
}
void c_Signal(R) { signal_task(r->d[0]); }
void c_Wait(R) { r->d[0] = wait_sigs(r->d[0]); }

void c_AddPort(R) {
    struct MsgPort *p = (struct MsgPort *)r->a[1];
    list_init(&p->msglist);
    list_addtail(&public_ports, &p->node);
    if (p->node.name && !strcmp(p->node.name, "SCIport") && loader_msg) {
        dbg("SCIport created; sending loader message\n");
        loader_msg->msg.replyport = 0;
        put_msg(p, &loader_msg->msg);
    }
}
void c_RemPort(R) { list_remove(&((struct MsgPort *)r->a[1])->node); }
void c_FindPort(R) {
    const char *name = (const char *)r->a[1];
    for (struct Node *n = public_ports.head; n->succ; n = n->succ)
        if (n->name && !strcmp(n->name, name)) { r->d[0] = (u32)n; return; }
    r->d[0] = 0;
}
void c_PutMsg(R) { put_msg((struct MsgPort *)r->a[0], (struct Message *)r->a[1]); }
void c_GetMsg(R) { r->d[0] = (u32)list_remhead(&((struct MsgPort *)r->a[0])->msglist); }
void c_ReplyMsg(R) {
    struct Message *m = (struct Message *)r->a[1];
    if (m->replyport) put_msg(m->replyport, m); else m->node.type = 7;   /* NT_REPLYMSG */
}
void c_WaitPort(R) {
    struct MsgPort *p = (struct MsgPort *)r->a[0];
    while (!p->msglist.head->succ) wait_sigs(1UL << p->sigbit);
    r->d[0] = (u32)p->msglist.head;
}

static struct Library *find_lib(const char *name) {
    for (int i = 0; i < nlibs; i++) if (!stricmp(libs[i].base->node.name, name)) return libs[i].base;
    return 0;
}
void c_OpenLibrary(R) {
    const char *name = (const char *)r->a[1];
    struct Library *l = find_lib(name);
    dbg("OpenLibrary(\"%s\", %d) -> $%x\n", name, r->d[0], (u32)l);
    if (l) l->opencnt++;
    r->d[0] = (u32)l;
}
void c_OldOpenLibrary(R) { r->d[0] = 0; c_OpenLibrary(r); }
void c_CloseLibrary(R) { struct Library *l = (struct Library *)r->a[1]; if (l && l->opencnt) l->opencnt--; }

/* Other tasks are not run: the only one Prog creates is "FireTask" (IDCMP -> SCI events), whose
 * job the shim does itself (see input.c). Record them so FindTask/RemTask work. */
static struct Task *tasks[4];
void c_AddTask(R) {
    struct Task *t = (struct Task *)r->a[1];
    dbg("AddTask(\"%s\", pc %H) - not started\n", t->node.name, r->a[2]);
    for (int i = 0; i < 4; i++) if (!tasks[i]) { tasks[i] = t; break; }
    r->d[0] = (u32)t;
}
void c_RemTask(R) {
    struct Task *t = r->a[1] ? (struct Task *)r->a[1] : 0;
    for (int i = 0; i < 4; i++) if (tasks[i] == t) tasks[i] = 0;
}

void c_Alert(R) { fatal("Alert($%x)", r->d[7]); }

/* ---- set-up ----------------------------------------------------------------------------- */
extern void stub_Forbid(void), stub_Permit(void), stub_Disable(void), stub_Enable(void),
    stub_AllocMem(void), stub_FreeMem(void), stub_AvailMem(void), stub_FindTask(void),
    stub_AllocSignal(void), stub_FreeSignal(void), stub_SetSignal(void), stub_Signal(void), stub_Wait(void),
    stub_AddPort(void), stub_RemPort(void), stub_FindPort(void), stub_PutMsg(void), stub_GetMsg(void),
    stub_ReplyMsg(void), stub_WaitPort(void), stub_OpenLibrary(void), stub_OldOpenLibrary(void),
    stub_CloseLibrary(void), stub_Alert(void), stub_AddIntServer(void), stub_RemIntServer(void), stub_AddTask(void), stub_RemTask(void);

/* Workbench start-up message: Message + sm_Process, sm_Segment, sm_NumArgs, sm_ToolWindow, sm_ArgList */
struct WBStartup { struct Message msg; void *process; u32 segment; s32 numargs; char *toolwindow; void *arglist; } PACKED;
CHECK(WBStartup, arglist, 0x24);

void exec_init(void) {
    list_init(&public_ports);
    SysBase = make_library("exec.library", 100, 0x300);
    *(u16 *)((u8 *)SysBase + 0x128) = 0;                    /* AttnFlags: plain 68000 */
    *(u8 *)((u8 *)SysBase + 0x212) = 50;                    /* VBlankFrequency */
    *(u8 *)((u8 *)SysBase + 0x213) = 50;                    /* PowerSupplyFrequency */
    static const struct { int lvo; void (*f)(void); } t[] = {
        { -108, stub_Alert }, { -168, stub_AddIntServer }, { -174, stub_RemIntServer }, { -120, stub_Disable }, { -126, stub_Enable }, { -132, stub_Forbid }, { -138, stub_Permit },
        { -198, stub_AllocMem }, { -210, stub_FreeMem }, { -216, stub_AvailMem }, { -282, stub_AddTask }, { -288, stub_RemTask }, { -294, stub_FindTask },
        { -306, stub_SetSignal }, { -318, stub_Wait }, { -324, stub_Signal }, { -330, stub_AllocSignal }, { -336, stub_FreeSignal },
        { -354, stub_AddPort }, { -360, stub_RemPort }, { -366, stub_PutMsg }, { -372, stub_GetMsg }, { -378, stub_ReplyMsg },
        { -384, stub_WaitPort }, { -390, stub_FindPort }, { -408, stub_OldOpenLibrary }, { -414, stub_CloseLibrary },
        { -552, stub_OpenLibrary } };
    for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++) set_lvo(SysBase, t[i].lvo, t[i].f);

    struct Process *p = the_process = mem_alloc(sizeof *p, 0x10000);
    p->task.node.name = "SCI"; p->task.node.type = 13;      /* NT_PROCESS */
    p->task.sigalloc = 0xffff;
    p->msgport.node.type = 4; p->msgport.sigbit = 8; p->msgport.sigtask = p; /* SIGB_DOS */
    list_init(&p->msgport.msglist);
    *(u32 *)((u8 *)SysBase + 0x114) = (u32)p;               /* ThisTask */

    /* Prog runs the Workbench start-up path (pr_CLI == 0): give it the start-up message. */
    struct WBStartup *wb = mem_alloc(sizeof *wb, 0x10000);
    wb->msg.length = sizeof *wb; wb->process = &p->msgport;
    put_msg(&p->msgport, &wb->msg);
}
