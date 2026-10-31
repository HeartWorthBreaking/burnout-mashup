/* main21 patch 118 (batch C3-6, zackypoo 04 a): the 32 crash / in-game camera effect values sub_00160B90 registers
 * (sub_001AEDB0, type 5 = a 3-float vector, all three set) into the camera block [0x47A134] + 0x2C30 (sub_00167220, once per
 * traffic init = per race load). var_va here is the OFFSET in that block (not an address): bm_tune.c never writes the block
 * outside the registration mark (bo3_tune_gen_cam); values set earlier apply at the next race load. Written by
 * notes\c3_scripts\gen_cam_inc.py (strings checked in the XBE; offsets: notes\C3_6_CRASHCAM_KEYS.txt, Shake = HYP until R-run). */
    {"Crash/HandyCam | Spring Coeff", "Spring Coeff", 0x00000000u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x0 (vec3, all three set) */
    {"Crash/HandyCam | Damping", "Damping", 0x00000010u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x10 (vec3, all three set) */
    {"InGame/Effect/Burnout/Position | Spring Coeff", "Spring Coeff", 0x00000030u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x30 (vec3, all three set) */
    {"InGame/Effect/Burnout/Position | Damping", "Damping", 0x00000040u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x40 (vec3, all three set) */
    {"InGame/Effect/Burnout/Position | Force", "Force", 0x00000050u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x50 (vec3, all three set) */
    {"InGame/Effect/Burnout/Angular | Spring Coeff", "Spring Coeff", 0x00000060u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x60 (vec3, all three set) */
    {"InGame/Effect/Burnout/Angular | Damping", "Damping", 0x00000070u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x70 (vec3, all three set) */
    {"InGame/Effect/Burnout/Angular | Force", "Force", 0x00000080u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x80 (vec3, all three set) */
    {"InGame/Effect/Shunt/Position | Spring Coeff", "Spring Coeff", 0x00000090u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x90 (vec3, all three set) */
    {"InGame/Effect/Shunt/Position | Damping", "Damping", 0x000000A0u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0xA0 (vec3, all three set) */
    {"InGame/Effect/Shunt/Position | Force", "Force", 0x000000B0u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0xB0 (vec3, all three set) */
    {"InGame/Effect/Shunt/Angular | Spring Coeff", "Spring Coeff", 0x000000C0u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0xC0 (vec3, all three set) */
    {"InGame/Effect/Shunt/Angular | Damping", "Damping", 0x000000D0u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0xD0 (vec3, all three set) */
    {"InGame/Effect/Shunt/Angular | Force", "Force", 0x000000E0u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0xE0 (vec3, all three set) */
    {"InGame/Effect/Shunted/Position | Spring Coeff", "Spring Coeff", 0x000000F0u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0xF0 (vec3, all three set) */
    {"InGame/Effect/Shunted/Position | Damping", "Damping", 0x00000100u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x100 (vec3, all three set) */
    {"InGame/Effect/Shunted/Position | Force", "Force", 0x00000110u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x110 (vec3, all three set) */
    {"InGame/Effect/Shunted/Angular | Spring Coeff", "Spring Coeff", 0x00000120u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x120 (vec3, all three set) */
    {"InGame/Effect/Shunted/Angular | Damping", "Damping", 0x00000130u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x130 (vec3, all three set) */
    {"InGame/Effect/Shunted/Angular | Force", "Force", 0x00000140u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x140 (vec3, all three set) */
    {"InGame/Effect/Slam/Position | Spring Coeff", "Spring Coeff", 0x00000150u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x150 (vec3, all three set) */
    {"InGame/Effect/Slam/Position | Damping", "Damping", 0x00000160u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x160 (vec3, all three set) */
    {"InGame/Effect/Slam/Position | Force", "Force", 0x00000170u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x170 (vec3, all three set) */
    {"InGame/Effect/Slam/Angular | Spring Coeff", "Spring Coeff", 0x00000180u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x180 (vec3, all three set) */
    {"InGame/Effect/Slam/Angular | Damping", "Damping", 0x00000190u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x190 (vec3, all three set) */
    {"InGame/Effect/Slam/Angular | Force", "Force", 0x000001A0u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x1A0 (vec3, all three set) */
    {"InGame/Effect/Shake/Position | Spring Coeff", "Spring Coeff", 0x000001B0u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x1B0 (vec3, all three set) */
    {"InGame/Effect/Shake/Position | Damping", "Damping", 0x000001C0u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x1C0 (vec3, all three set) */
    {"InGame/Effect/Shake/Position | Force", "Force", 0x000001D0u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x1D0 (vec3, all three set) */
    {"InGame/Effect/Shake/Angular | Spring Coeff", "Spring Coeff", 0x000001E0u, 0x003AF478u, 2u, 0x00000000u},   /* block + 0x1E0 (vec3, all three set) */
    {"InGame/Effect/Shake/Angular | Damping", "Damping", 0x000001F0u, 0x003AF448u, 2u, 0x00000000u},   /* block + 0x1F0 (vec3, all three set) */
    {"InGame/Effect/Shake/Angular | Force", "Force", 0x00000200u, 0x003AF400u, 2u, 0x00000000u},   /* block + 0x200 (vec3, all three set) */
