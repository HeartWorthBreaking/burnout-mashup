/* main21 patch 115 (zackypoo 04 b): the seven Air Ram multipliers of the crash physics, registered ONCE by sub_0010C5F0 (group
 * "CAD Properties" 0x3AC8A4, sub_001AEEB0, record + 0 = the variable) into the traffic world's object 0x64ACE8 (= world 0x60EA00 +
 * 0x3C2E8, sub_001AA100 loc_001AA335; BSS, the same address every load: C1 [DIAG] air ram, 5 loads). Read by the crash code
 * sub_0010DAC0 / sub_0010DD20. No vdb.xml entry and no code default (the game's value = what the field holds when the
 * registration ends): shipped 0 = the BSS value at the host's start; the game's value is taken at the registration mark
 * (bo3_tune_gen_cad) and owned values are applied there. Written by hand (not gen_catalog.py: not a sub_001AEDB0 site). */
    {"CAD Properties | Air Ram Front Corner", "Air Ram Front Corner", 0x0064B264u, 0x003AC88Cu, 2u, 0x00000000u},   /* + 0x57C */
    {"CAD Properties | Air Ram Back Corner", "Air Ram Back Corner", 0x0064B268u, 0x003AC878u, 2u, 0x00000000u},     /* + 0x580 */
    {"CAD Properties | Air Ram Side", "Air Ram Side", 0x0064B26Cu, 0x003AC868u, 2u, 0x00000000u},                   /* + 0x584 */
    {"CAD Properties | Air Ram Front", "Air Ram Front", 0x0064B270u, 0x003AC858u, 2u, 0x00000000u},                 /* + 0x588 */
    {"CAD Properties | Air Ram Back", "Air Ram Back", 0x0064B274u, 0x003AC848u, 2u, 0x00000000u},                   /* + 0x58C */
    {"CAD Properties | Air Ram World", "Air Ram World", 0x0064B278u, 0x003AC838u, 2u, 0x00000000u},                 /* + 0x590 */
    {"CAD Properties | Air Ram Low Speed Multiplier", "Air Ram Low Speed Multiplier", 0x0064B27Cu, 0x003AC818u, 2u, 0x00000000u},   /* + 0x594 */
