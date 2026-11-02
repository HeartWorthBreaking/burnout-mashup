/* bo3_rowx_gen.h - gp slice mega1: the mesh-block material ROW EXTENSION (bm_rowx.c). The generated draw code reads a unit's
 * material rows (+0x71 rows, +0x73 pass-1 rows, +0x84 s16 material per row, chunk rowsA at +0x12D / rowsB at +0x180 +
 * slot * 0xA9 + row) through these calls in sub_001AD510 / sub_001AD5E0 / sub_001AD7A0 / sub_001ADA40 / sub_001ADD60.
 * A block without the 'BMRX' header at +0xC64 (every retail block: that pad is zero) reads exactly the retail bytes.
 * Included into every generated file through BO3_GEN_OPT (-include), like the other *_gen.h. */
#ifndef BO3_ROWX_GEN_H
#define BO3_ROWX_GEN_H
#include <stdint.h>
uint32_t bo3_rowx_gen_count(uint32_t blk, uint32_t field);                      /* field 0x71 / 0x73: sign-extended s8 */
/* patch 131: the same for the 8-bit signed pre-loop guards (marks C1 / C3): an extension's count clamped to 127 */
uint32_t bo3_rowx_gen_count8(uint32_t blk, uint32_t field);
/* main21 patch 131: the C1 / C3 count8 marks (#if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZRX, after the GP-MEGA1 lines); no CMake
 * option: on. Without them (BO3_HOOKREQ_P23=0) bm_rowx.c keeps the 127-row cap, so no extension has a count the guards misread. */
#ifndef BO3_HOOKREQ_ZRX
#define BO3_HOOKREQ_ZRX 1
#endif
/* main21 patch 132: the record extension flag ("BMRC" at block + 0xC70, version 1 at + 0xC74): 1 = this block's record
 * indices (chunk heads in rowsA / rowsB / the BMRX rows, the records' +0x8C next) are u8 (0xFF = none, 0..254 records). */
uint32_t bo3_rowx_gen_recu8(uint32_t blk);
/* the four ZRC marks in sub_001AD510 / sub_001AD5E0 (#if BO3_HOOKREQ_P23 && BO3_HOOKREQ_ZRC); no CMake option: on */
#ifndef BO3_HOOKREQ_ZRC
#define BO3_HOOKREQ_ZRC 1
#endif
uint32_t bo3_rowx_gen_row(uint32_t blk, uint32_t lin, uint32_t row, uint32_t off);  /* off 0x12D (A) / 0x180 (B): u8 */
uint32_t bo3_rowx_gen_mat(uint32_t blk, uint32_t row);                          /* sign-extended s16 material index */
#endif
