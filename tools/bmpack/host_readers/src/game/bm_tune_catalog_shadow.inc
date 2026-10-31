/* main21 patch 129 (C3-9b, car shadow look; notes\C3_9B_SHADOW_SOFTNESS_RE.md): the 5 "virtual" car shadow rows (BM_TUNE_SH_N, right
 * before the spark row). No guest variable: bm_tune.c keeps an owned value host-side and the marks in sub_00043350 / sub_00043570 /
 * sub_00043850 (recomp_0000.c, BO3_HOOKREQ_ZSH) read it at every shadow draw (applies at once). name_va = "blobbyshadow" 0x3AAFF8 (the
 * texture name the set-up pushes at 0x43370); var_va = the game constant the row replaces (checked == shipped), 0 = a code constant.
 * shipped = the game's value: alpha test 1 (0x4338E ecx), opacity 0.7 [0x3B17D8], width / length scale 1, soft edge = the v split
 * 0.1875 [0x3B1AC0] (the other split = 1 - value = [0x3B1ABC] 0.8125). Bounds: bm_tune.c k_sh_bounds (not 16 x the game's value). */
    {"Effects/Shadow | Alpha Test", "blobbyshadow", 0x00000000u, 0x003AAFF8u, 1u, 0x00000001u},
    {"Effects/Shadow | Opacity", "blobbyshadow", 0x003B17D8u, 0x003AAFF8u, 2u, 0x3F333333u},
    {"Effects/Shadow | Width", "blobbyshadow", 0x00000000u, 0x003AAFF8u, 2u, 0x3F800000u},
    {"Effects/Shadow | Length", "blobbyshadow", 0x00000000u, 0x003AAFF8u, 2u, 0x3F800000u},
    {"Effects/Shadow | Soft Edge", "blobbyshadow", 0x003B1AC0u, 0x003AAFF8u, 2u, 0x3E400000u},
