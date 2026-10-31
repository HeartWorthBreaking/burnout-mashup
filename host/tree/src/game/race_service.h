/*
 * race_service.h - the "takedawn.race" service (include/takedawn_race.h,
 * docs/native-plugins.md, The race).
 */
#ifndef BO3_RACE_SERVICE_H
#define BO3_RACE_SERVICE_H

#include "takedawn_race.h"

/* Offer the service to the plugins (bo3_plugins_service), before
 * bo3_plugins_init. */
void bo3_race_init(void);
/* After each of the title's game updates (CB3Game::Update, bo3_update), on
 * the game's thread: a new snapshot, then the plugins' on_update calls. */
void bo3_race_after_update(void);
/* The service's table (for the unit test). */
const td_race_api *bo3_race_api(void);

#endif
