/* main21 patch 136: MIX CUSTOM MUSIC WITH EA TRAX, the marks in recomp_0003.c (soundtrack.c). */
#ifndef BO3_MIX_GEN_H
#define BO3_MIX_GEN_H
#include <stdint.h>
#ifndef BO3_HOOKREQ_ZMIX
#define BO3_HOOKREQ_ZMIX 0
#endif
void bo3_mix_gen_frame(uint32_t mgr);          /* the music manager's frame, its first line: a switch that is due */
int  bo3_mix_gen_song_end(uint32_t mgr);       /* a song ended, the next is about to be picked: 1 = the other source plays next, skip the title's */
#endif
