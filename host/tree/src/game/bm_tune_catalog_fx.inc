/* main21 patch 123 (batch C3-9): the spark effect's size - the "fxspark" fx table record 0 (0x418EA0, 0x7C a record, filled at start-up
 * by the static initialiser sub_00261360; name pointer + 0x68 = "fxspark" 0x3AAFC0), field + 0x58: Xbox 0.012, PS2 0.017 (the one
 * spark value the two versions differ in; notes\C3_9_PS2_SHADOWS_SPARKS.md; "size" = HYP until the PS2-look run). Zero in the XBE:
 * bm_tune.c keeps a set value and writes it at the mark after the Global.txd load (bo3_tune_gen_fx, the table is filled then) and
 * at once afterwards. */
    {"Effects/Sparks | Size", "fxspark", 0x00418EF8u, 0x003AAFC0u, 2u, 0x00000000u},
