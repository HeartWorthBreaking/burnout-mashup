/* G8-L6a: force-included into the generated sources (BO3_GEN_OPT). The loader insertion (l6_gamedata\design) calls this
 * right after sub_0018B250 sets its section cursor, before the first section read. */
#ifndef BO3_GAMEDATA_GEN_H
#define BO3_GAMEDATA_GEN_H

#include <stdint.h>

void bo3_gd_gen_check(uint32_t loader);

#define BO3_GD_CHECK(ld) bo3_gd_gen_check((uint32_t)(ld))

#endif
