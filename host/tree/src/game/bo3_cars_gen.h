/* bo3_cars_gen.h - GP-CARS2: the calls the generated code makes for cars added by mods (bm_cars.c, bm_cars.h). Included into
 * every generated file through BO3_GEN_OPT (-include). */
#ifndef BO3_CARS_GEN_H
#define BO3_CARS_GEN_H
#include <stdint.h>
/* sub_00015F10 loc_000160EE: pveh\vlist.bin is read (0x4D2000): the declared cars are appended */
void bo3_car_gen_vlist_loaded(void);
/* sub_00132D10 / sub_000C0080: the ID whose VehiclePhysics ValueDB file is read: an added car's donor, else id itself */
uint64_t bo3_car_gen_phys_id(uint32_t lo, uint32_t hi);
/* sub_0011A810 after sub_00132D10 created a block: the declared scales of an added car (block +0xB0 = its ID) */
void bo3_car_gen_phys_block(uint32_t block_va);
/* sub_0002DDF0 on a miss (it returns 0): an added car's exact name -> the donor's entry of the same dictionary, else 0 */
uint32_t bo3_car_gen_photo(uint32_t dict_va, uint32_t name_va);
/* after sub_00158A60 (career index of lo:hi): -1 for an added car -> the donor's index; any other value unchanged */
uint32_t bo3_car_gen_sidx(uint32_t idx, uint32_t lo, uint32_t hi);
/* the game's fallback text dflt (0x4EA) for lo:hi: an added car's host text ID of kind, else dflt */
enum { BO3_CAR_TEXT_NAME = 0, BO3_CAR_TEXT_AWARD = 1 };
uint32_t bo3_car_gen_text(uint32_t dflt, uint32_t kind, uint32_t lo, uint32_t hi);
#endif
