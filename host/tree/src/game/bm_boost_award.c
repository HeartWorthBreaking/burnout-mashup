/* bm_boost_award.c - G8-E2 EXPERIMENTAL: bmashup.events version 4 BOOST_AWARD (include/bmashup_events.h) from one generated
 * line at the entry of the game's boost add sub_0017A530 (bo3_boost_award_gen.h; v5: it also returns the amount the game uses):
 *   bo3_e2_gen_boost_award(MEM32(esp) = the return address (the call site), esi = the meter, MEM32(esp + 4) = the amount bits)
 * Source = the call site only (e3_tune\analysis\boost_sources.json: the tunable each site reads before its call, SRC; the
 * perfect-lap site also runtime-verified, launches 28 / 29). An unlisted site is BM_BOOST_UNKNOWN - never guessed from the
 * amount. Recipient: the meter is the car's + 0x119C at every site seen at runtime (E6 probe, launches 28 / 29: 6 cars), so
 * the car is meter - 0x119C and the racer its index in the race's list (bm_takedown.c); else BM_EVENT_NO_RACER.
 * Reads only. MUT=n (tests) compiles one deliberate defect. */
#include "bm_boost_award.h"

#include <string.h>

#include "bm_events_service.h"
#include "bm_takedown.h"

#ifndef MUT
#define MUT 0
#endif

#define E2_METER_IN_CAR 0x119Cu

static const struct { uint32_t site; uint32_t source; } k_sites[] = {
    {0x001946DEu, BM_BOOST_PERFECT_LAP},   {0x001947F6u, BM_BOOST_BURNOUT_LAP}, {0x00195BABu, BM_BOOST_TAILGATING},
    {0x001969B4u, BM_BOOST_AIR},           {0x00196C77u, BM_BOOST_ONCOMING},    {0x00196EA7u, BM_BOOST_DRIFT},
    {0x001972BAu, BM_BOOST_GRINDING},      {0x00197A89u, BM_BOOST_PROP_HIT},    {0x00197AEFu, BM_BOOST_BOOST_START},
    {0x001988E7u, BM_BOOST_TRADING_PAINT},
};

uint32_t bo3_e2_source_of(uint32_t site, float amount)
{
#if MUT == 1
    if (amount == 120.0f)
        return BM_BOOST_PERFECT_LAP;            /* defect: a source guessed from the amount */
#else
    (void)amount;
#endif
    if (site == 0u)
        return BM_BOOST_HOST;
    for (size_t i = 0; i < sizeof k_sites / sizeof k_sites[0]; i++)
        if (k_sites[i].site == site)
            return k_sites[i].source;
    return BM_BOOST_UNKNOWN;
}

uint32_t bo3_e2_recipient_of(uint32_t meter)
{
#if MUT == 2
    return bo3_e6_racer_index(meter);          /* defect: the meter taken for the car */
#else
    return meter > E2_METER_IN_CAR ? bo3_e6_racer_index(meter - E2_METER_IN_CAR) : BM_EVENT_NO_RACER;
#endif
}

/* G8-E2M (version 5): the generated line is `MEM32(esp + 4) = bo3_e2_gen_boost_award(MEM32(esp), esi, MEM32(esp + 4));` -
 * the routine's own argument slot (it reads [esp+4] next, at loc_0017A53E, then scales it by the meter's factors and caps the
 * bar). The modifiers run first, then the observers get the final amount; the returned bits are the final amount. */
uint32_t bo3_e2_gen_boost_award(uint32_t ret, uint32_t meter, uint32_t amount_bits)
{
    float a, out;
    uint32_t recipient, source, bits;
    int modified = 0;
    memcpy(&a, &amount_bits, 4);
    recipient = bo3_e2_recipient_of(meter);
    source = bo3_e2_source_of(ret, a);
    out = bo3_bm_events_modify_boost(recipient, source, ret, a, &modified);
    bo3_bm_events_deliver_boost(recipient, source, ret, out, a, modified);
    if (!modified)
        return amount_bits;                     /* bit-identical when nothing changed it */
    memcpy(&bits, &out, 4);
    return bits;
}
