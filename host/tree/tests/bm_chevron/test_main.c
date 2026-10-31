/* tests/bm_chevron - capdbg T1 over the REAL generated chevron draw: sub_001AE200 + sub_0019B1B0 extracted unchanged
 * (gen_capfix1.c with the guard mark, or gen_clean1.c = the unguarded p4.4 / clean1 code), the real guard (bm_chevron.c) and
 * the real guest access checks (bm_guest.c). Stand-in guest memory; the STATIC is the shipped BM Test Loop static.dat
 * (trackbuild 0.2.0 = 0.1.6 bytes, path in argv[1]) placed at a stand-in pool base with the two pointer fields this path
 * reads relocated as the game's sub_0019B4E0 does (header +0x28, the per-unit table [+0x4C]: crash-stack word 0x82A44B04 =
 * 0x82A37000 + 0xDB04). Callees outside the path are stubs; sub_001AD050 (one model's draw) counts calls.
 * GUARDED=1: build with gen_capfix1.c + bm_chevron.c (must PASS: no OOB draw, valid sets unchanged).
 * GUARDED=0: build with gen_clean1.c (must reproduce the OOB: the garbage loop at a 0x...7000 base). */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "recomp_types.h"
#if GUARDED
#include "bm_chevron.h"
#endif

ptrdiff_t g_xbox_mem_offset;
RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp, g_ebx, g_esi, g_edi, g_ebp, g_seh_ebp;
RECOMP_TLS RecompXmm g_xmm0, g_xmm1, g_xmm2, g_xmm3, g_xmm4, g_xmm5, g_xmm6, g_xmm7;
RECOMP_TLS double g_fp_stack[8];
RECOMP_TLS int g_fp_top, g_df;
RECOMP_TLS uint16_t g_fp_cc;

#define GMEM 0x01000000u
static uint8_t *s_mem;
size_t xbox_GetMappedSize(void) { return GMEM; }
uint32_t xbox_ContiguousBlockSize(uint32_t va) { (void)va; return 0; }
#define M8(va)  (*(uint8_t *)(s_mem + (uint32_t)(va)))
#define M16(va) (*(uint16_t *)(s_mem + (uint32_t)(va)))
#define M32(va) (*(uint32_t *)(s_mem + (uint32_t)(va)))

/* the indirect call in sub_001AE200 (loc_001AE252) is not on the tested path; its runtime symbols are stand-ins */
volatile uint32_t g_icall_trace[ICALL_TRACE_SIZE];
volatile uint32_t g_icall_trace_idx;
volatile uint64_t g_icall_count;
uint32_t g_xbox_code_lo, g_xbox_code_hi;
static int s_icalls;
void recomp_icall_not_code_log(uint32_t va) { (void)va; s_icalls++; }
void recomp_icall_fail_log(uint32_t va) { (void)va; s_icalls++; }
recomp_func_t recomp_lookup_manual(uint32_t va) { (void)va; return NULL; }
recomp_func_t recomp_lookup(uint32_t va) { (void)va; return NULL; }
recomp_func_t recomp_lookup_kernel(uint32_t va) { (void)va; return NULL; }

#define OBJ    0x00200000u
#define REC    0x00210000u
#define STACK  0x00100000u
#define STPTR  0x007397B4u

static int s_draws, s_other;
static uint32_t s_first_model, s_last_model;
void sub_00017310(void) { g_eax &= 0xFFFFFF00u; g_esp += 4; }      /* "not paused": je loc_001AE26A */
void sub_00038D10(void) { s_other++; g_esp += 4; }
void sub_00039140(void) { s_other++; g_esp += 4; }                  /* tail jump target: its ret returns for sub_001AE200 */
void sub_001AD050(void)                                             /* one chevron model's draw (ret 4) */
{
    if (!s_draws)
        s_first_model = g_ebx;
    s_last_model = g_ebx;
    s_draws++;
    g_esp += 8;
}
extern void sub_001AE200(void);

static int s_pass, s_fail;
#define CHECK(c, ...) do { if (c) s_pass++; else { s_fail++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); \
    printf("\n"); } } while (0)

static uint8_t *s_file;
static long s_file_n;

/* the shipped static.dat at base, the fields this path reads relocated (header +0x28, the per-unit table at [+0x4C]) */
static void place_static(uint32_t base)
{
    uint32_t t, n, k;
    memcpy(s_mem + base, s_file, (size_t)s_file_n);
    M32(base + 0x28) += base;
    t = M32(base + 0x4C);
    n = (uint32_t)(int16_t)M16(base + 0x54);
    for (k = 0; k < n; k++)
        M32(base + t + 4 * k) += base;
    M32(base + 0x4C) += base;
}

/* run the real sub_001AE200 once with chevron index z, STATIC at st; -> draws */
static int run(uint32_t st, int8_t z, const char *what)
{
    uint32_t esp0;
    memset(s_mem + OBJ, 0, 0x1000);
    memset(s_mem + REC, 0, 0x100);
    M8(OBJ + 0x44) = 1;
    M32(OBJ + 0x1C8) = REC;
    M32(OBJ + 0x1C) = 0;
    M8(0x73BACAu) = 0;
    M8(0x4D61C6u) = 1;
    M8(0x752D33u) = 0;
    M8(REC + 0x7D) = (uint8_t)z;
    M32(STPTR) = st;
    s_draws = s_other = 0;
    s_first_model = s_last_model = 0;
    g_esi = OBJ;
    g_edi = 0x13579BDFu;
    g_ebx = 0x2468ACE0u;
    g_esp = STACK;
    g_esp -= 4;
    M32(g_esp) = 0xC0DE0001u;
    esp0 = g_esp;
    sub_001AE200();
    CHECK(g_esp == esp0 + 4, "%s: stack %08X, want %08X", what, g_esp, esp0 + 4);
    CHECK(g_edi == 0x13579BDFu, "%s: edi not restored (%08X)", what, g_edi);
    CHECK(s_other == (z < 0 ? 0 : 2), "%s: sub_00038D10 + sub_00039140 reached %d times (z %d: the game skips both for z < 0)", what, s_other, z);
    return s_draws;
}

int main(int argc, char **argv)
{
    FILE *f;
    int d;
    const uint32_t BASE_POS = 0x00A37000u;   /* low 16 bits of the rc_onb_1 pool 0x82A37000 */
    const uint32_t BASE_NEG = 0x00431000u;   /* low 16 bits of the game's pool 0x81431000 */
    const uint32_t SYN = 0x00C00000u;        /* a retail-like synthetic STATIC */

    if (argc < 2 || !(f = fopen(argv[1], "rb")))
        return printf("usage: test BM_TEST_LOOP_static.dat\n"), 2;
    fseek(f, 0, SEEK_END);
    s_file_n = ftell(f);
    fseek(f, 0, SEEK_SET);
    s_file = malloc((size_t)s_file_n);
    if (fread(s_file, 1, (size_t)s_file_n, f) != (size_t)s_file_n)
        return 2;
    fclose(f);
    s_mem = calloc(1, GMEM);
    g_xbox_mem_offset = (ptrdiff_t)(uintptr_t)s_mem;
    CHECK(s_file_n == 0x10000 && (int16_t)M16(0) == 0 && s_file[0x1E] == 0 && s_file[0x1F] == 0,
          "the input is not the 0x10000-byte Test Loop with 0 chevron entries");

    /* A: the crash case - shipped Test Loop, relocated to a 0x...7000 base, z = 0 */
    place_static(BASE_POS);
    d = run(BASE_POS, 0, "A");
#if GUARDED
    CHECK(d == 0, "A: guarded build drew %d chevron models from an empty set", d);
#else
    CHECK(d == 19204 && s_first_model == BASE_POS + 0xDB04u && s_last_model == BASE_POS + 0xDB04u + 0x60u * 19203u,
          "A: unguarded build did not reproduce the OOB loop: %d draws, first %08X", d, s_first_model);
#endif
    /* B: the same file at a 0x...1000 base (the game's pool): the count is negative, nothing drawn either way */
    memset(s_mem + BASE_POS, 0, 0x10000);
    place_static(BASE_NEG);
    d = run(BASE_NEG, 0, "B");
    CHECK(d == 0, "B: %d draws at the game-pool base", d);
    /* C: retail-like: 1 chevron entry {2 models}, z = 0 -> 2 draws in BOTH builds (the guard keeps valid sets) */
    memset(s_mem + SYN, 0, 0x1000);
    M16(SYN + 0x1E) = 1;
    M32(SYN + 0x28) = SYN + 0x100;
    M16(SYN + 0x100) = 2;
    M32(SYN + 0x104) = SYN + 0x200;
    M16(SYN + 0x108) = 5;                    /* entry 1 (outside the set) would draw 5 */
    M32(SYN + 0x10C) = SYN + 0x400;
    d = run(SYN, 0, "C");
    CHECK(d == 2 && s_first_model == SYN + 0x200 && s_last_model == SYN + 0x260, "C: %d draws (want 2)", d);
    /* D: z = -1 -> no chevron (the game's own check) */
    d = run(SYN, -1, "D");
    CHECK(d == 0, "D: %d draws for z = -1", d);
    /* E: z = 1 = the count (one past the set) */
    d = run(SYN, 1, "E");
#if GUARDED
    CHECK(d == 0, "E: guarded build drew %d models for z == count", d);
#else
    CHECK(d == 5, "E: unguarded build: %d (want the OOB entry's 5)", d);
#endif
    /* G: a non-empty BACKDROP set (+0x1C) must not open the empty chevron set */
    place_static(BASE_POS);
    M16(BASE_POS + 0x1C) = 3;
    d = run(BASE_POS, 0, "G");
#if GUARDED
    CHECK(d == 0, "G: guarded build drew %d (read the backdrop count?)", d);
    /* F: an unreadable STATIC header: fail closed */
    CHECK(bo3_chev_skip(0xFFFFF000u, 0) == 1, "F: an unmapped STATIC was not skipped");
    CHECK(bo3_chev_skip(SYN, 0) == 0, "F: a valid index was skipped");
    CHECK(bo3_chev_skips() >= 3, "skip counter %u", bo3_chev_skips());
#else
    CHECK(d == 19204, "G: unguarded %d", d);
#endif
    CHECK(s_icalls == 0, "the indirect-call branch was taken %d times", s_icalls);
    printf("bm_chevron (%s): %d passed, %d failed\n", GUARDED ? "capfix1 guarded" : "clean1 unguarded", s_pass, s_fail);
    return s_fail ? 1 : 0;
}
