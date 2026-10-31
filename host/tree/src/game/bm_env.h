/* bm_env.h - pfid1 (public-fork identity): the environment variables of the host, Burnout Mashup names first.
 *
 * BM_GETENV("MODS") reads BMASHUP_MODS and, when that is not set at all, TAKEDAWN_MODS (every TAKEDAWN_* name keeps working:
 * scripts, the tester launcher and Workbench of older releases set those). A BMASHUP_* variable that is set wins even when it is
 * empty, so "" keeps its meaning ("none", e.g. BMASHUP_PLUGIN_APPROVALS="" = no approval file).
 * Without BMASHUP_IDENTITY (the CMake option, -DBMASHUP_IDENTITY=OFF) it is getenv("TAKEDAWN_<name>") exactly as in main21. */
#ifndef BM_ENV_H
#define BM_ENV_H

#include <stdlib.h>

#ifdef BMASHUP_IDENTITY
static inline const char *bm_getenv2(const char *bm, const char *td)
{
    const char *v = getenv(bm);
    return v ? v : getenv(td);
}
#define BM_GETENV(name) bm_getenv2("BMASHUP_" name, "TAKEDAWN_" name)
#else
#define BM_GETENV(name) getenv("TAKEDAWN_" name)
#endif

#endif
