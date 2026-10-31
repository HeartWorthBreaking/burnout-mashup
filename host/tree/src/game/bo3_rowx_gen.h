/* bo3_rowx_gen.h - gp slice mega1: the mesh-block material ROW EXTENSION (bm_rowx.c). The generated draw code reads a unit's
 * material rows (+0x71 rows, +0x73 pass-1 rows, +0x84 s16 material per row, chunk rowsA at +0x12D / rowsB at +0x180 +
 * slot * 0xA9 + row) through these calls in sub_001AD510 / sub_001AD5E0 / sub_001AD7A0 / sub_001ADA40 / sub_001ADD60.
 * A block without the 'BMRX' header at +0xC64 (every retail block: that pad is zero) reads exactly the retail bytes.
 * Included into every generated file through BO3_GEN_OPT (-include), like the other *_gen.h. */
#ifndef BO3_ROWX_GEN_H
#define BO3_ROWX_GEN_H
#include <stdint.h>
uint32_t bo3_rowx_gen_count(uint32_t blk, uint32_t field);                      /* field 0x71 / 0x73: sign-extended s8 */
uint32_t bo3_rowx_gen_row(uint32_t blk, uint32_t lin, uint32_t row, uint32_t off);  /* off 0x12D (A) / 0x180 (B): u8 */
uint32_t bo3_rowx_gen_mat(uint32_t blk, uint32_t row);                          /* sign-extended s16 material index */
#endif
