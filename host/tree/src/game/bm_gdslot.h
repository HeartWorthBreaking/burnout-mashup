/* bm_gdslot.h - gp slice mega1 EXPERIMENTAL: the GAMEDATA slot expansion.
 *
 * The track loader reads a track's event (header 0x3000, record 0x800, S1, S2, S3, S4 back to back) into the GAMEDATA pool
 * buffer: descriptor idx 52 (0x003FA004, layout 1) / idx 128 (0x003FA4C4, layout 2), {state, owner layout, size +8, base +0xC},
 * 0x176000 bytes in both layouts (KB RESOURCE_LIMITS s2). A mod that needs more declares it:
 *     [bmashup.capacity]  gamedata_bytes = 0x280000     (page multiple, 0x177000 .. 0x800000)
 * The largest accepted request wins. After the game set up its memory (the same moment the STATIC pool expansion runs,
 * bo3_static_gen.h bo3_st_gen_apply) the host verifies that both descriptors are the game's (state 0, owners 1 / 2, size
 * 0x176000, one shared page-aligned base), allocates ONE contiguous region of the frozen size and points both descriptors
 * at it (size +8, base +0xC). The loader asks the descriptor for its buffer, so every later track load uses the region; the
 * GAMEDATA guard (bm_gamedata.c) reads the same descriptor, so it checks against the new size. Fail closed: a mismatch, a
 * refused allocation or an unsupported build keep the game's slot (the guard still stops a track that needs more, exit 88).
 * Nothing is ever released (process lifetime), as the STATIC pool. */
#ifndef BM_GDSLOT_H
#define BM_GDSLOT_H
#include <stdint.h>

#define BO3_GDS_GAME 0x176000u
#define BO3_GDS_MAX 0x800000u
#define BO3_GDS_PAGE 0x1000u
#define BO3_GDS_DESC_L1 0x003FA004u
#define BO3_GDS_DESC_L2 0x003FA4C4u

enum { BO3_GDS_OK = 0, BO3_GDS_OUT_OF_RANGE = 1, BO3_GDS_CLOSED = 2, BO3_GDS_MISMATCH = 3, BO3_GDS_NO_MEMORY = 4,
       BO3_GDS_UNSUPPORTED = 5 };

typedef uint8_t *(*bo3_gds_guest_fn)(uint32_t va, uint32_t size);
typedef uint32_t (*bo3_gds_alloc_fn)(uint32_t size, uint32_t align);

int bo3_gds_request(uint32_t bytes, uint32_t *merged);        /* before bo3_gds_apply; largest wins */
int bo3_gds_apply_with(bo3_gds_guest_fn guest, bo3_gds_alloc_fn alloc, int build_ok);  /* testable core */
void bo3_gds_apply(void);                                     /* game build: called from bo3_st_gen_apply */
uint32_t bo3_gds_frozen(void);
uint32_t bo3_gds_state(void);                                 /* 0 planned, 1 game's slot, 2 expanded, 3 failed */
void bo3_gds_reset_for_tests(void);
#endif
