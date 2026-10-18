/* AllocMem/FreeMem backend: one big GEMDOS block managed as an address-ordered free list.
 * AmigaOS semantics: caller passes the size to FreeMem, blocks are 8-byte aligned,
 * MEMF_CLEAR (0x10000) zeroes the block. MEMF_CHIP/FAST/PUBLIC are ignored (ST RAM is all "chip"). */
#include "amiga.h"

#define MEMF_CLEAR   0x10000
#define MEMF_LARGEST 0x20000
#define RESERVE      (32 * 1024)   /* left to GEMDOS for TOS itself */

struct Free { struct Free *next; u32 size; };
static struct Free *free_list;
static u32 pool_size;

static u32 round8(u32 n) { return (n + 7) & ~7UL; }

void mem_init(void) {
    long avail = Malloc(-1);
    long n = (avail - RESERVE) & ~7L;
    if (n < 256 * 1024) fatal("only %d bytes free", avail);
    u8 *p = (u8 *)Malloc(n);
    if (!p) fatal("Malloc(%d) failed", n);
    u32 a = ((u32)p + 7) & ~7UL;
    free_list = (struct Free *)a;
    free_list->next = 0;
    free_list->size = pool_size = (n - (a - (u32)p)) & ~7UL;
    dbg("memory pool: %d KB at $%x\n", pool_size >> 10, a);
}

void *mem_alloc(u32 size, u32 flags) {
    if (!size) return 0;
    size = round8(size);
    struct Free **pp = &free_list, *f;
    for (; (f = *pp); pp = &f->next) {
        if (f->size < size) continue;
        if (f->size - size < sizeof(struct Free)) { *pp = f->next; size = f->size; }
        else { struct Free *rest = (struct Free *)((u8 *)f + size); rest->next = f->next; rest->size = f->size - size; *pp = rest; }
        if (flags & MEMF_CLEAR) memset(f, 0, size);
        return f;
    }
    dbg("AllocMem(%d, $%x) failed: largest free %d\n", size, flags, mem_avail(MEMF_LARGEST));
    return 0;
}

void mem_free(void *p, u32 size) {
    if (!p || !size) return;
    size = round8(size);
    struct Free *b = p, **pp = &free_list;
    while (*pp && *pp < b) pp = &(*pp)->next;
    b->next = *pp; b->size = size; *pp = b;
    if (b->next && (u8 *)b + b->size == (u8 *)b->next) { b->size += b->next->size; b->next = b->next->next; }
    if (pp != &free_list) {
        struct Free *prev = (struct Free *)((u8 *)pp - __builtin_offsetof(struct Free, next));
        if ((u8 *)prev + prev->size == (u8 *)b) { prev->size += b->size; prev->next = b->next; }
    }
}

u32 mem_avail(u32 flags) {
    u32 total = 0, largest = 0;
    for (struct Free *f = free_list; f; f = f->next) { total += f->size; if (f->size > largest) largest = f->size; }
    return (flags & MEMF_LARGEST) ? largest : total;
}
